// Runs one allowlisted case. This process never opens evaluator/ or raw FinQA sources.
import { readFile,copyFile,mkdir,writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { FinanceService } from '../server/mcp.js';
import { DATA,loadSettings,saveSettings,redactError } from '../server/config.js';
import { RunManager } from '../server/runs.js';
import type { Settings,Conversation } from '../server/types.js';
const CONTRACT='只返回一个JSON对象，不要Markdown。字段：id（题目ID），status（ok或insufficient_evidence），answer（精确十进制字符串；核查题为JSON布尔值；证据不足为null），unit，period，scope，citations（source_id:p物理页码或FinQA原文中提供的source_id:text_N/table_N），核查题必须带corrected_value，证据不足必须带reason_code。金额unit=CNY；同比unit=percent（9.44表示9.44%）；倍数unit=ratio。中国年报年度流量period=YYYY-FY，期末存量period=YYYY-12-31，scope=consolidated_CAS。FinQA题unit=finqa_execution，遵循题目answer_convention；不要臆加100倍。资料未覆盖期间时status=insufficient_evidence,answer=null,reason_code=period_not_in_source,citations=[]。所有非空数值回答需要先调用检索或查询工具取得证据；计算使用计算工具。引用仅列必要的支持证据，最多8条，不把无关检索命中都列为引用。';
async function main(payload:{settings:Settings,inputDir:string}){
 const inputDir=path.resolve(payload.inputDir),record=JSON.parse(await readFile(path.join(inputDir,'case.json'),'utf8'));
 await loadSettings();await saveSettings(payload.settings);
 const service=new FinanceService();await service.connect();const manager=new RunManager(service);
 const started=performance.now();
 try{
  await service.call('create_project',{project_id:'case',name:record.id});await service.configure('case',payload.settings);
  const ids:string[]=[],mapping:any[]=[];
  for(const asset of record.allowed_assets){
   const source=path.resolve(inputDir,asset);if(!source.startsWith(inputDir+path.sep))throw new Error('asset path escape');
   const target=path.join(DATA,'uploads',path.basename(asset));await mkdir(path.dirname(target),{recursive:true});await copyFile(source,target);
   const result=await service.call('ingest_document',{project_id:'case',path:target,original_name:path.basename(asset)});
   ids.push(result.data.document_id);
   const physicalPage=record.track==='cn_ocr'?Number(record.question.match(/PDF第(\d+)页/)?.[1]):undefined;
   mapping.push({document_id:result.data.document_id,source_id:record.source_ids[0],image_physical_page:physicalPage,filename:path.basename(asset)});
  }
  const now=new Date().toISOString(),chat:Conversation={id:randomUUID(),projectId:'case',title:record.id,messages:[],createdAt:now,updatedAt:now};
  await service.putState('case','conversations',chat.id,chat);manager.indexConversation(chat.id,'case');
  const citationExample=record.source_ids[0]+':p5';
  const query=record.question+'\n'+(record.answer_convention || '')+'\n题目ID：'+record.id+'\n原始材料source_id映射（用于引用）：'+JSON.stringify(mapping)+'\n引用格式校验：PDF/图片必须包含字母p，例如物理第5页写成"'+citationExample+'"，不能写成source_id:5。FinQA必须保留工具返回的原始text_N/table_N编号，使用get_source_page.segments或get_source_table.source_rows，不得用内部table_id（:t0）或虚构行号代替。这里的第5页只是格式示例，实际页码必须从材料核实。\n计算校验：表格preview只有前5行，需要具体值时读取完整表，核对表头、年份与科目。返回计算工具的完整小数精度，不为了展示而自行四舍五入。增加或减少的方向、比率的分母、金额单位必须依据原问题和原文确认。';
  const contract=record.response_contract==='financial-source-grounded-v2'
   ? CONTRACT.replace('FinQA题unit=finqa_execution，遵循题目answer_convention；不要臆加100倍。','FinQA题严格遵循题目answer_unit和answer_convention指定的单位。题目与原文无法唯一确定答案时，status=insufficient_evidence,answer=null,reason_code=ambiguous_question_or_source，并引用证明歧义或信息缺失的原文；不能自行补充题目没有限定的年份、范围或会计假设。')
   : CONTRACT;
  const run=await manager.start(chat,query,ids,contract);
  const deadline=Date.now()+20*60000;
  while(!['completed','failed','cancelled'].includes((await manager.getRun(run.id)).status)){
   if(Date.now()>deadline){await manager.cancel(run.id);break;}await delay(200);
  }
  await delay(300);
  const finished=await manager.getRun(run.id),conversation=await manager.getConversation(chat.id);
  const text=conversation.messages.at(-1)?.content || '';
  let prediction:any,parseError:string|undefined;
  try{
   const cleaned=text.trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'');
   prediction=JSON.parse(cleaned);
   if(!prediction || Array.isArray(prediction) || typeof prediction!=='object')throw new Error('Response is not an object');
   if(prediction.id!==record.id)throw new Error('Wrong response id');
   if(!finished.tools.some(t=>['search_evidence','get_source_page','get_source_table','get_financial_metrics'].includes(t.name)&&t.status==='completed'))throw new Error('No evidence tool was executed');
   // Normalizing a document identifier is bookkeeping, never repairing a numeric answer.
   if(Array.isArray(prediction.citations))prediction.citations=prediction.citations.map((citation:string)=>{
    for(const map of mapping){
     const prefix=map.document_id+':p';if(citation.startsWith(prefix))return map.source_id+':p'+(map.image_physical_page || citation.slice(prefix.length));
    }
    return citation;
   });
  }catch(error){parseError=redactError(error);prediction={id:record.id,status:'failed',answer:null,citations:[],error:parseError};}
  if(finished.status!=='completed')prediction={id:record.id,status:'failed',answer:null,citations:[],error:finished.error};
  const output={id:record.id,prediction,run:finished,elapsedMs:Math.round(performance.now()-started),parseError,rawResponse:text,mapping};
  await writeFile(path.join(DATA,'case-result.json'),JSON.stringify(output,null,2),'utf8');
  process.send?.({type:'result',result:output});
 }catch(error){process.send?.({type:'result',result:{id:record.id,prediction:{id:record.id,status:'failed',answer:null,citations:[],error:redactError(error)},elapsedMs:Math.round(performance.now()-started)}});}
 finally{await manager.shutdown();await service.close();process.disconnect?.();}
}
process.once('message',(message:any)=>{void main(message).catch(error=>{process.send?.({type:'fatal',message:redactError(error)});process.exitCode=1;process.disconnect?.();});});

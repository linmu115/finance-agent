import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import type {EvaluationOptions} from '../server/evaluation-budget.js';

test('real Pi/MCP evaluation isolates generic tools and accounts every main/bridge call under shared budgets',{timeout:180000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-evaluation-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');
 const {RunManager,GENERIC_TOOL_ALLOWLIST,registerResearchPdf}=await import('../server/runs.js');
 const {ResearchStore}=await import('../server/research.js');
 await loadSettings();const service=new FinanceService();await service.connect();
 const requests:any[]=[];let financialDocument='';
 const mock=createServer(async(req,res)=>{
  const chunks:Buffer[]=[];for await(const chunk of req)chunks.push(Buffer.from(chunk));
  const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));requests.push(body);
  const content=(value:any)=>Array.isArray(value)?value.map((block:any)=>block.text||'').join('\n'):String(value||'');
  const messages=body.messages,text=content(messages.at(-1)?.content),system=content(messages[0]?.content);
  let delta:any,finish='stop';
  if(system.includes('通用文档分析助手'))delta={content:'generic read-only complete'};
  else if(text.includes('[[TEMPORAL_REVIEW]]')){
   const count=new Set(text.match(/\[\[GROUP:[a-f0-9]+\]\]/g)||[]).size;
   delta={content:JSON.stringify({extractions:[{temporal_review:'[[TEMPORAL_REVIEW]]',temporal_review_attributes:{reviewed_count:count,flag_count:0,keep_count:count}}]})};
  }else if(text.includes('[[CATALOG]]')){
   const count=new Set(text.match(/\[\[METRIC:[a-z0-9_]+\]\]/g)||[]).size;
   delta={content:JSON.stringify({extractions:[{catalog_review:'[[CATALOG]]',catalog_review_attributes:{reviewed_count:count,merge_count:0,keep_count:count,keep_summary:'原指标保留'}}]})};
  }else if(text.includes('财务数据清洗工程师')){
   const columns=[{column:2,period:'2024-12-31',start:'',end:'2024-12-31',unit:'元',currency:'CNY'}];
   delta={content:JSON.stringify({extractions:[{table_schema:'[[T0]]',table_schema_attributes:{company:'公司',statement:'balance',scope:'consolidated_CAS',unit:'元',currency:'CNY',columns_json:JSON.stringify(columns)}},{financial_row:'[[T0:R2]]',financial_row_attributes:{metric:'assets',label:'总资产',unit:'元'}}]})};
  }else if(text.includes('[[DEFINITION:')){
   const markers=[...new Set(text.match(/\[\[DEFINITION:[a-f0-9]{64}\]\]/g)||[])];
   delta={content:JSON.stringify({extractions:markers.map(marker=>({definition_unresolved:marker,definition_unresolved_attributes:{reason:'本测试保留未决定义，以验证只复核入口和原数据守恒'}}))})};
  }else{
   const user=messages.findLast((m:any)=>m.role==='user'),repeat=content(user?.content).includes('repeat-failed'),existing=content(user?.content).includes('existing-review-only'),tools=messages.filter((m:any)=>m.role==='tool');
   if(!tools.length||(repeat&&tools.length===1)){
    finish='tool_calls';delta={tool_calls:[{index:0,id:'process-'+requests.length,type:'function',function:{name:'process_documents',arguments:JSON.stringify({document_ids:[repeat?'missing-document':financialDocument],...(existing?{review_existing_only:true,review_metrics:['assets']}:repeat?{}:{review_metrics:['assets']})})}}]};
   }else delta={content:repeat?'saw '+tools.at(-1).content:'financial complete'};
  }
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const base={id:'fixture',object:'chat.completion.chunk',created:1,model:'evaluation-mock'};
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{role:'assistant',...delta},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:13,prompt_tokens_details:{cached_tokens:3},completion_tokens:7,total_tokens:20}})+'\n\n');
  res.end('data: [DONE]\n\n');
 });
 await new Promise<void>(resolve=>mock.listen(0,'127.0.0.1',resolve));
 const manager=new RunManager(service);
 const wait=async(id:string)=>{const deadline=Date.now()+60000;while(Date.now()<deadline){const r=await manager.getRun(id);if(['completed','failed','cancelled'].includes(r.status)&&!manager.activeFor(r.conversationId))return r;await delay(25);}throw new Error('evaluation fixture timeout');};
 const chat=async(projectId:string)=>{const time=new Date().toISOString(),c={id:randomUUID(),projectId,title:'新对话',messages:[],createdAt:time,updatedAt:time};await service.putState(projectId,'conversations',c.id,c);manager.indexConversation(c.id,projectId);return c;};
 const budget=(profile:'financial'|'generic',group:string,calls=12):EvaluationOptions=>({profile,budget_group_id:group,budget:{max_model_calls:calls,max_input_tokens:10000,max_output_tokens:100000,max_total_tokens:110000,max_wall_seconds:90}});
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'evaluation-mock',apiKey:'fixture',contextWindow:16384,maxTokens:512}});
  await service.call('create_project',{project_id:'raw',name:'Raw'});await service.call('create_project',{project_id:'fin',name:'Financial'});
  const generics=await Promise.all([chat('raw'),chat('raw')]);
  const started=await Promise.all(generics.map(c=>manager.start(c,'generic baseline',[],undefined,budget('generic','shared-raw',2))));
  const genericResults=await Promise.all(started.map(r=>wait(r.id)));
  assert(genericResults.every(r=>r.status==='completed'),JSON.stringify(genericResults));
  assert.equal(genericResults.reduce((sum,r)=>sum+r.usage.calls,0),2);
  assert.equal(genericResults[1].evaluation?.usage.model_calls,2);
  assert.equal(genericResults[1].evaluation?.usage.input_tokens,26);
  for(const request of requests){assert.deepEqual(new Set(request.tools.map((tool:any)=>tool.function.name)),GENERIC_TOOL_ALLOWLIST);assert(!String(request.messages[0]?.content).includes('LangExtract'));}
  const denied=await manager.start(await chat('raw'),'generic third',[],undefined,budget('generic','shared-raw',2));
  assert.equal((await wait(denied.id)).status,'failed');assert.equal(requests.length,2,'denied call reached model');
  await assert.rejects(()=>manager.start(generics[0],'switch',[],undefined,budget('financial','wrong-profile')),/profile_conflict/);
  await mkdir(path.join(dir,'uploads'),{recursive:true});const csv=path.join(dir,'uploads','2024.csv');await writeFile(csv,'项目,本期\n资产,137\n','utf8');
  const rawDoc=(await service.call('register_document',{project_id:'raw',path:csv,original_name:'2024.csv'})).data.document_id;
  const prepared=await service.call('prepare_document_sources',{project_id:'raw',document_ids:[rawDoc]});
  assert.equal(prepared.data.facts_written,0);assert.equal((await service.call('query_financial_data',{project_id:'raw'})).data.total,0);
  financialDocument=(await service.call('register_document',{project_id:'fin',path:csv,original_name:'2024.csv'})).data.document_id;
  const before=requests.length,fin=await manager.start(await chat('fin'),'financial extraction',[financialDocument],undefined,budget('financial','financial-arm'));
  const done=await wait(fin.id);assert.equal(done.status,'completed',done.error);
  assert.equal((await service.call('query_financial_data',{project_id:'fin'})).data.total,1,'fixture extraction must actually commit a fact');
  assert.equal(done.usage.calls,requests.length-before);assert.equal(done.usage.input,13*done.usage.calls);assert.equal(done.usage.output,7*done.usage.calls);
  assert.equal(done.evaluation?.usage.model_calls,done.usage.calls);assert.equal(done.evaluation?.usage.input_tokens,done.usage.input);
  const audit=(await readFile(path.join(dir,'audit',fin.id+'.jsonl'),'utf8')).trim().split('\n').map(line=>JSON.parse(line));
  assert(audit.some(x=>x.type==='extraction_result'));assert.equal(audit.filter(x=>x.type==='model_usage').length,done.usage.calls);
  const factsBefore=(await service.call('query_financial_data',{project_id:'fin'})).data.items;
  const existing=await manager.start(await chat('fin'),'existing-review-only',[],undefined,budget('financial','existing-only'));
  const existingDone=await wait(existing.id);assert.equal(existingDone.status,'completed',existingDone.error);
  assert.deepEqual((await service.call('query_financial_data',{project_id:'fin'})).data.items,factsBefore);
  const existingAudit=(await readFile(path.join(dir,'audit',existing.id+'.jsonl'),'utf8')).trim().split('\n').map(line=>JSON.parse(line));
  assert.equal(existingAudit.find(x=>x.type==='processing_started')?.data.mode,'existing_source_definition_review');
  const definitions=existingAudit.filter(x=>x.type==='extraction_result');assert.equal(definitions.length,1);
  assert(definitions[0].data.content.includes('definition_unresolved'));
  const repeat=await manager.start(await chat('fin'),'repeat-failed',[],undefined,budget('financial','failed-whole-tool'));
  const repeatDone=await wait(repeat.id);assert.equal(repeatDone.status,'completed',repeatDone.error);
  assert(!(await manager.getConversation(repeat.conversationId)).messages.at(-1)?.content.includes('failed_previous_attempt'));
  const repeatAudit=(await readFile(path.join(dir,'audit',repeat.id+'.jsonl'),'utf8')).trim().split('\n').map(line=>JSON.parse(line));
  assert.equal(repeatAudit.filter(x=>x.type==='tool_error'&&x.data.name==='process_documents').length,2,'both attempts must reach the service and report its actual error');
  assert.equal(repeatAudit.filter(x=>x.type==='tool_result'&&x.data.result.data?.code==='failed_previous_attempt').length,0);
  const store=new ResearchStore(path.join(dir,'research'));
  const pdfBytes=Buffer.from('%PDF-1.4\nfixture-original-source\n%%EOF');
  const snapshot=await store.saveSnapshot('fin','https://example.org/report',{download:async()=>({body:pdfBytes,url:'https://example.org/report',contentType:'application/pdf',headers:{}}),registerPdf:(file,name)=>registerResearchPdf(service,'fin',file,name)});
  assert(snapshot.document_id);const doc=await service.call('get_document',{project_id:'fin',document_id:snapshot.document_id});
  assert.equal(doc.data.original_name,'report.pdf');assert.equal(doc.data.state,'registered');
  assert.deepEqual(await readFile((await store.blob('fin',snapshot.source_id)).path),pdfBytes);
  assert.deepEqual(await readFile(path.join(dir,doc.data.relative_path)),pdfBytes);
 }finally{await manager.shutdown();await service.close();await new Promise<void>(resolve=>{mock.close(()=>resolve());mock.closeAllConnections();});}
});

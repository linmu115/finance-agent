import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {createAssistantMessageEventStream,normalizeContext,getCurrentTools,getCurrentSystemPrompt,getCurrentSystemMessage} from '@earendil-works/pi-ai';
import {fauxAssistantMessage as answer} from '@earendil-works/pi-ai/providers/faux';
import {needsWorkpaper,pipelineArguments,appWorkpaperContext} from '../server/workpaper-precompute.js';
import {modelContext} from '../server/model-context.js';
import {evaluationRuntime,evaluationIsolation} from '../server/evaluation-isolation.js';

test('financial analysis selects the pipeline, while ingestion and generic profiles keep their path',()=>{
 for(const q of ['请分析2024年报的利润和现金流质量','为什么盈利下滑','Analyze the annual report revenue','核对口径是否一致','给出预期差分析','比较季度表现'])assert.ok(needsWorkpaper('financial',q));
 for(const p of ['original_pi','prepared','generic'])assert.equal(needsWorkpaper(p,'分析年报利润与现金流'),false);
 for(const q of ['继续完整入库年报，修复 t10','如何计算毛利率','画一只猫','用给定FCF估值'])assert.equal(needsWorkpaper(undefined,q),false);
 const docs=[{document_id:'annual',original_name:'公司2024年度报告.pdf',report_year:2024},{document_id:'q3',original_name:'公司2024第三季度报告.pdf',report_year:2024}];
 assert.equal(pipelineArguments('分析2024年报',[],docs).document_id,'annual');
 assert.equal(pipelineArguments('分析利润',['attached'],docs).document_id,'attached');
});

test('pipeline projection retains N4 fields and actionable project-bound examples without full host tables',()=>{
 const context={management_evidence:[{status:'qualitative_disclosed'}],signal_followups:[{persistence:{sample_count:2}}],
  full_tables:{read:{tool:'financial_workpaper',arguments:{project_id:'p',kind:'read_table',read:{handle:'h',table:'t'}}}},
  selection:{retry_calls:[{arguments:{project_id:'p',kind:'analysis_pipeline',document_id:'d'},call:'financial_workpaper(old)'}]}};
 const result=modelContext('financial_workpaper',{status:'ok',data:{kind:'analysis_pipeline',context,numeric_tables:{private:'full'},report:{private:'full'}},source_refs:[{text:'long'}]} as any);
 assert.deepEqual(result.source_refs,[]);assert.equal(result.data.numeric_tables,undefined);
 assert.equal(result.data.context.full_tables.read.arguments.project_id,undefined);
 assert.equal(result.data.context.selection.retry_calls[0].call,'financial_workpaper({"kind":"analysis_pipeline","document_id":"d"})');
 assert.deepEqual(result.data.context.management_evidence,context.management_evidence);
 assert.equal(context.full_tables.read.arguments.project_id,'p','MCP envelope remains intact');
 assert.deepEqual(appWorkpaperContext({status:'error',message:'specific failure'}),{status:'error',message:'specific failure'});
});

test('native host precompute before reasoning, A1 registration, profile exclusion and failure delivery',{timeout:240000},async()=>{
 const source=process.env.F20_REPLAY_DATA;
 const dir=source?path.resolve(source):await mkdtemp(path.join(tmpdir(),'finance-workpaper-host-'));
 process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings,getSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'host-offline',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const oldStream=ModelRuntime.prototype.streamSimple,call=service.call.bind(service);
 let requests:any[]=[],calls:any[]=[],fail=false,ambiguous=false,restrict=false,prepared=false;
 const fakeContext={schema_version:'workpaper-pipeline-v1',status:'partial',key_metrics:[{values:{current:{ref:'statement_income.revenue.2024-FY',display:'137 元'}}}],
  management_evidence:[{status:'qualitative_disclosed'}],signal_followups:[{persistence:{sample_count:2,allow_continuous_claim:false}}],extensions:{management_evidence:'ready',signal_followups:'ready',comparability_constraints:'not_provided'}};
 service.call=async(name,args,signal)=>{
  calls.push({name,args,profile:evaluationRuntime.getStore()?.profile,isolation_key:evaluationIsolation.getStore(),at:Date.now()});
  if(name==='financial_workpaper'&&args.kind==='analysis_pipeline'){
   assert.equal(prepared,false,'first provider call must follow host precompute');
   if(fail)throw Error('fixture source table unavailable');
   if(ambiguous)return {status:'insufficient_evidence',data:{context:{status:'selection_required',missing:[{reason:'fixture ambiguous company'}]}},source_refs:[],warnings:[],trace_id:'fixture'};
   if(!source)return {status:'ok',data:{kind:'analysis_pipeline',context:{...fakeContext,...(restrict?{comparability_constraints:[{id:'unknown',affected_refs:['statement_income.revenue.2024-FY'],forbidden_claims:['label_as_parent_profit'],required_qualification:'利润归属未明，不得改标归母。'}]}:{})},numeric_tables:{statement_income:{row_keys:['revenue'],columns:{'2024-FY':{unit:'元'}},rows:[{key:'revenue','2024-FY':'137'}]}}},source_refs:[],warnings:[],trace_id:'fixture'};
  }
  return call(name,args,signal);
 };
 ModelRuntime.prototype.streamSimple=function(model,context,config){
  prepared=true;const transcript=normalizeContext(context),tools=getCurrentTools(transcript.messages),system=getCurrentSystemPrompt(transcript.messages);
  requests.push({messages:transcript.messages,tools,systemPrompt:system,sections:getCurrentSystemMessage(transcript.messages)?.sections});
  const texts=transcript.messages.flatMap((m:any)=>typeof m.content==='string'?[m.content]:(m.content||[]).map((b:any)=>b.text||''));
  const injected=texts.find((s:string)=>s.startsWith('宿主已执行只读财报底稿流水线。'));
  const contextData=injected?JSON.parse(injected.slice(injected.indexOf('\n')+1)):undefined;
  const ref:any=contextData?.data?.context?.key_metrics?.flatMap((m:any)=>Object.values(m.values)).find((v:any)=>v.ref)?.ref;
  const next=answer(tools.length?(restrict?(requests.filter(r=>r.tools.length).length===1?'归母净利润为 {{statement_income.revenue.2024-FY}}。':'归属未明的披露利润为 {{statement_income.revenue.2024-FY}}。'):ref?'披露收入为 {{'+ref+'}}。':contextData?.status==='error'?'底稿暂不可用：'+contextData.message+'；缺项保持未知。':'当前资料的缺项保持未知。'):'{"task":"analysis","afterIngestion":"high","reason":"offline"}');
  const message={...next,api:model.api,model:model.id,provider:model.provider,timestamp:Date.now()},stream=createAssistantMessageEventStream();
  void(async()=>{await config?.onPayload?.({messages:context.messages},model);await config?.onResponse?.({status:200,headers:{}},model);stream.push({type:'start',partial:message});stream.push({type:'done',reason:'stop',message});})();return stream;
 };
 const sha=(s:string)=>createHash('sha256').update(s).digest('hex');
 const measure=(s:string)=>({chars:[...s].length,utf8_bytes:Buffer.byteLength(s),rough_tokens:Math.ceil([...s].reduce((a,c)=>a+(c.codePointAt(0)!<128?.25:1),0))});
 const results:any[]=[];
 try{
  let documents:Record<string,any>;
  if(source)documents=JSON.parse(await readFile(path.join(dir,'snapshot-manifest.json'),'utf8')).documents;
  else{await service.call('create_project',{project_id:'p',name:'synthetic'});const input=path.join(dir,'uploads','fixture.csv');await writeFile(input,'项目,2024\n收入,137\n');const doc=(await service.call('register_document',{project_id:'p',path:input,original_name:'fixture.csv'})).data.document_id;await service.call('prepare_document_sources',{project_id:'p',document_ids:[doc]});documents={synthetic:{project:'p',document:doc}};}
  for(const [name,doc] of Object.entries(documents))for(const profile of ['original_pi','prepared','financial']){
   prepared=false;calls=[];requests=[];
   const c:any={id:randomUUID(),projectId:doc.project,title:'Offline development replay',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
   await service.putState(doc.project,'conversations',c.id,c);manager.indexConversation(c.id,doc.project);
   const evaluation:any={profile,analysis_only:true,isolation_key:'f20-'+c.id,budget_group_id:c.id,budget:{max_model_calls:10,max_input_tokens:1000000,max_output_tokens:100000,max_total_tokens:1100000,max_wall_seconds:180}};
   const run=await manager.start(c,'按现有已准备资料分析财报的盈利与现金流质量，解释变化驱动和异常。',source?[]:[doc.document],undefined,evaluation);
   const deadline=Date.now()+180000;while(manager.activeFor(c.id)){if(Date.now()>deadline)throw Error('native replay timeout');await delay(20);}
   const final=await manager.getRun(run.id),chat=await manager.getConversation(c.id);assert.equal(final.status,'completed',final.error);
   const audit=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(s=>JSON.parse(s));
   const pre=audit.find(e=>e.type==='workpaper_precompute'),initial=requests.find(r=>r.tools.length);
   const ctx=pre?.data.result.data?.context;
   assert.equal(!!pre,profile==='financial');
   assert.equal(calls.filter(c=>c.name==='financial_workpaper').length,profile==='financial'?1:0);
   assert.equal(JSON.stringify(initial.messages).includes('宿主已执行只读财报底稿流水线'),profile==='financial');
   assert.equal(initial.tools.length,profile==='financial'?32:profile==='prepared'?13:10);
   if(profile==='financial'){
    assert.ok(audit.indexOf(pre)<audit.findIndex(e=>e.type==='model_request'));
    assert.ok(ctx,JSON.stringify(pre?.data.result));assert.equal(ctx.extensions.management_evidence,'ready');assert.equal(ctx.extensions.signal_followups,'ready');
    assert.ok(ctx.management_evidence.length);assert.ok(ctx.signal_followups.length);
    const toolResult=audit.find(e=>e.type==='tool_result'&&e.data.origin==='host_precompute');assert.ok(toolResult.data.result.data.numeric_tables.statement_income);
    const {reportSnapshot}=await import('../server/report-package.js');const snapshot=await reportSnapshot(chat);assert.deepEqual(snapshot.turns.at(-1)?.tables,toolResult.data.result.data.numeric_tables,'host tables enter the report package without retranscription');
    assert.ok(calls.filter(c=>c.name==='financial_workpaper').every(c=>c.profile==='financial'&&c.isolation_key===evaluation.isolation_key));
    assert.equal(chat.messages.at(-1).content.includes('{{'),false,'actual A1 renderer used host tables');
    assert.equal(audit.some(e=>e.type==='answer_degraded'),false);
   }else assert.equal(initial.tools.some((t:any)=>t.name==='financial_workpaper'),false);
   const sections=initial.sections;
   if(profile==='original_pi')assert.equal(sha(sections.preamble),'6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f');
   results.push({name,profile,run_id:run.id,status:final.status,pipeline:pre?.data.result,context_measurement:ctx?measure(JSON.stringify(ctx)):undefined,
    tools:initial.tools,tools_sha256:sha(JSON.stringify(initial.tools)),prompt_sections:sections,preamble_sha256:sha(sections.preamble),system_sha256:sha(initial.systemPrompt),
    system_measurement:measure(initial.systemPrompt),tools_measurement:measure(JSON.stringify(initial.tools)),answer:chat.messages.at(-1).content,audit_types:audit.map(e=>e.type)});
  }
  if(!source){
   for(const mode of ['failure','ambiguous','constraint']){
    fail=mode==='failure';ambiguous=mode==='ambiguous';restrict=mode==='constraint';prepared=false;calls=[];requests=[];
    const c:any={id:randomUUID(),projectId:'p',title:mode,messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
    await service.putState('p','conversations',c.id,c);manager.indexConversation(c.id,'p');
    const run=await manager.start(c,'分析财报利润和现金流',[documents.synthetic.document]);
    while(manager.activeFor(c.id))await delay(20);
    assert.equal((await manager.getRun(run.id)).status,'completed');
    const seen=JSON.stringify(requests);
    for(const request of requests.filter(r=>r.tools.length)){const injected=request.messages.findIndex((m:any)=>JSON.stringify(m).includes('宿主已执行只读财报底稿流水线'));const assistant=request.messages.findIndex((m:any)=>m.role==='assistant');assert.ok(injected>=0);if(assistant>=0)assert.ok(injected<assistant,'precompute stays before subsequent tool/answer updates');}
    if(restrict){const events=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(s=>JSON.parse(s));assert.equal(events.filter(e=>e.type==='answer_binding_error').length,1);assert.equal(events.some(e=>e.type==='answer_degraded'),false);assert.match((await manager.getConversation(c.id)).messages.at(-1).content,/归属未明/);}
    else assert.ok(seen.includes(fail?'source table unavailable':'ambiguous company'));
   }
  }
  if(process.env.F20_EVIDENCE_DIR){
   const target=path.resolve(process.env.F20_EVIDENCE_DIR);await mkdir(target,{recursive:true});
   await writeFile(path.join(target,'native-host-replay.json'),JSON.stringify({method:'Actual RunManager + native Pi + stdio MCP; scripted provider; no HTTP listener, no paid model. Rough tokens=ASCII/4+non-ASCII, not billed tokens.',results},null,2)+'\n');
  }
 }finally{ModelRuntime.prototype.streamSimple=oldStream;await manager.shutdown();await service.close();}
});

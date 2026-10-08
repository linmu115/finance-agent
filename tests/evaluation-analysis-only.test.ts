import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {normalizeEvaluation,EvaluationBudgets,EvaluationBudget} from '../server/evaluation-budget.js';
import {createFauxCore,fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';

const budget={max_model_calls:100,max_input_tokens:1000000,max_output_tokens:100000,max_total_tokens:1100000,max_wall_seconds:300};
const options=(profile:'prepared'|'financial'='financial',analysis_only=true)=>({profile,budget_group_id:profile+'-budget',budget,isolation_key:profile+'-chain',analysis_only});
const ingestion=['process_documents','inspect_document_routing','set_document_profile','get_cleaning_batch','run_cleaning_script','get_cleaning_result','commit_cleaning_result','save_research_claims'];

test('analysis_only is an optional request flag independent of budget accounting',()=>{
 assert.equal(normalizeEvaluation(options())?.analysis_only,true);
 assert.equal(normalizeEvaluation(options('financial',false))?.analysis_only,false);
 const {analysis_only,...without}=options();assert.equal(normalizeEvaluation(without)?.analysis_only,undefined);
 for(const value of ['true',1,null,{}])assert.throws(()=>normalizeEvaluation({...options(),analysis_only:value}),/invalid_evaluation_analysis_only/);
 const groups=new EvaluationBudgets({scheduleDeadline:false}),a=groups.acquire('p',options());
 assert.equal(groups.acquire('p',without),a);assert.equal(a.snapshot().analysis_only,undefined);
 const restored=new EvaluationBudget(options(),{scheduleDeadline:false},a.snapshot());assert.deepEqual(restored.options,a.options);
 restored.dispose();groups.dispose();
});

// Synthetic partial ingestion only. No held-out data, paid model or HTTP test listener.
test('native evaluation remains analysis-only on partial documents while ordinary requests still ingest',{timeout:90000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-analysis-only-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings,getSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'offline-analysis-only',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const faux=createFauxCore({tokensPerSecond:0}),sessionFor=manager.sessionFor.bind(manager),entries:any[]=[];
 manager.sessionFor=async(...args:any[])=>{const e=await sessionFor(...args);e.runtime.streamSimple=faux.streamSimple;entries.push({entry:e,live:args[0]});return e;};
 const original=service.call.bind(service),calls:string[]=[];
 service.call=async(name,args,signal)=>{
  calls.push(name);
  if(name==='list_documents')return {status:'ok',data:{documents:[{document_id:'partial',state:'failed',fact_count:1}]}};
  if(['get_document','get_source_page','get_source_table','query_financial_data','record_attachment_read','prepare_document_sources'].includes(name))return {status:'ok',data:{document_id:'partial',state:'failed',value:'12.5',facts_written:0}};
  if(name==='get_analysis_status')return {status:'ok',data:{status:'succeeded',artifacts:[],numeric_tables:{t:{columns:{value:{unit:'元',currency:'CNY'}},rows:[{value:'12.5'}]}}}};
  if(name==='begin_script_cleaning')return {status:'ok',data:{processing_id:'ordinary-processing',state:'normalizing',instructions:'fixture'}};
  if(name==='advance_cleaning_round')return {status:'ok',data:{processing_id:'ordinary-processing',pending_tables:{},pending_pages:{}}};
  return original(name,args,signal);
 };
 const chat=async()=>{const c:any={id:randomUUID(),projectId:'partial-fixture',title:'Fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};await service.putState(c.projectId,'conversations',c.id,c);manager.indexConversation(c.id,c.projectId);return c;};
 const run=async(c:any,responses:any[],evaluation?:ReturnType<typeof options>)=>{
  faux.setResponses(responses);const started=await manager.start(c,'按现有资料分析',[],undefined,evaluation),deadline=Date.now()+30000;
  while(manager.activeFor(c.id)){if(Date.now()>deadline)throw Error('offline run timeout');await delay(20);}
  const state=await manager.getRun(started.id);assert.equal(state.status,'completed',state.error);assert.equal(faux.getPendingResponseCount(),0);
  const events=(await readFile(path.join(dir,'audit',started.id+'.jsonl'),'utf8')).trim().split('\n').map(x=>JSON.parse(x));
  return {state,events,chat:await manager.getConversation(c.id),entry:entries.at(-1).entry,live:entries.at(-1).live};
 };
 const call=(name:string,args:any={})=>answer(tool(name,args),{stopReason:'toolUse'});
 try{
  await service.call('create_project',{project_id:'partial-fixture',name:'Synthetic partial sources'});
  for(const profile of ['financial','prepared'] as const){
   const before=calls.length,c=await chat();
   const r=await run(c,[call('list_documents'),call('process_documents',{document_ids:['partial'],force:false,review_existing_only:false,review_metrics:['revenue']}),
    call('prepare_document_sources',{document_ids:['partial']}),call('query_financial_data'),call('get_source_page',{document_id:'partial',page:1}),
    call('get_source_table',{document_id:'partial',table_id:'partial:t1'}),call('get_analysis_status',{run_id:'fixture'}),answer('数值 {{t.0.value}}。')],options(profile));
   const config=r.events.find(e=>e.type==='run_config').data;
   assert.equal(config.analysis_only,true);assert.equal(r.state.request.evaluation.analysis_only,true);
   for(const name of ingestion)assert.ok(!config.tools.includes(name),name);
   for(const name of ['query_financial_data','get_source_page','get_source_table','prepare_document_sources','run_analysis','get_artifact'])assert.ok(config.tools.includes(name),name);
   assert.equal(calls.slice(before).includes('begin_script_cleaning'),false);
   assert.equal(calls.slice(before).includes('advance_cleaning_round'),false);
   assert.equal(r.events.filter(e=>['processing_started','ingestion_continuation'].includes(e.type)).length,0);
   assert.match(r.chat.messages.at(-1).content,/12\.50 CNY 元/);
   const live=r.live;
   for(const name of ingestion)await assert.rejects(manager.executeTool(live,getSettings(),name,'denied',{}),/工具不属于当前运行配置/);
   assert.match(manager.promptFor(live,{id:'probe',attachments:['partial'],content:'分析'}),/本次评测只分析已有资料/);
   assert.doesNotMatch(manager.promptFor(live,{id:'probe',attachments:['partial'],content:'分析'}),/默认调用 process_documents/);
   if(profile==='financial'){
    // The same conversation must rebuild its cached tool set when the opt-in flag changes.
    const off=await run(r.chat,[call('process_documents',{document_ids:['partial'],force:false}),answer('批次完成。')],options(profile,false));
    assert.ok(off.events.some(e=>e.type==='processing_started'));assert.notEqual(off.entry,r.entry);
    const on=await run(off.chat,[answer('继续分析。')],options(profile));
    assert.ok(!on.entry.session.getActiveToolNames().includes('process_documents'));assert.notEqual(on.entry,off.entry);
   }
  }
  const ordinary=await run(await chat(),[call('process_documents',{document_ids:['partial'],force:false}),answer('批次完成。')]);
  assert.ok(ordinary.events.some(e=>e.type==='processing_started'));
  for(const name of ingestion)assert.ok(ordinary.entry.session.getActiveToolNames().includes(name),name);
  assert.match(manager.promptFor(ordinary.live,{id:'probe',attachments:['partial'],content:'分析'}),/默认调用 process_documents/);
  assert.doesNotMatch(manager.promptFor(ordinary.live,{id:'probe',attachments:[],content:'分析'}),/本次评测只分析已有资料/);
  // Appended input cannot silently change the policy of a still-active turn.
  const pending:any={chat:ordinary.chat,run:{id:'pending',conversationId:ordinary.chat.id,request:{evaluation:options()}},closed:false,accepting:true};
  manager.live.set('pending',pending);
  try{await assert.rejects(manager.start(ordinary.chat,'继续',[],undefined,{...options('financial',false),isolation_key:undefined}),/analysis_only_conflict/);}
  finally{manager.live.delete('pending');}
 }finally{await manager.shutdown();await service.close();}
});

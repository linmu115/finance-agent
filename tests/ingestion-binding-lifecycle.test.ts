import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {createFauxCore,fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';

// Native Pi + RunManager + MCP stdio. In-process scripted provider: no model/network calls or HTTP listener.
test('ingestion continuation and answer repair stay exclusive across native turns and reused sessions',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-ingestion-binding-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'ingestion-offline-fixture',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const faux=createFauxCore({tokensPerSecond:0});
 const sessionFor=manager.sessionFor.bind(manager);
 manager.sessionFor=async(...args:any[])=>{const entry=await sessionFor(...args);entry.runtime.streamSimple=faux.streamSimple;return entry;};
 let remaining:number[][]=[],progressCalls=0,renderCalls=0;
 const original=service.call.bind(service),pid='fixture-processing';
 service.call=async(name,args,signal)=>{
  if(name==='begin_script_cleaning')return {status:'ok',data:{processing_id:pid,state:'normalizing',instructions:'Fixture cleaning instructions'}};
  if(name==='get_cleaning_progress'){
   progressCalls++;return {status:'ok',data:{processing_id:pid,pending_tables:{doc:remaining.shift()??[]},pending_pages:{doc:[]},pending_scripts:[]}};
  }
  if(name==='get_cleaning_batch')return {status:'ok',data:{processing_id:pid,batch:{tables:[1]}}};
  if(name==='cancel_processing')return {status:'ok',data:{state:'cancelled'}};
  if(name==='get_analysis_status')return {status:'ok',data:{status:'succeeded',artifacts:[],numeric_tables:{values:{columns:{item:{},value:{unit:'元',currency:'CNY'}},rows:[{item:'total',value:'12.5'}],row_keys:['total']}}}};
  if(name==='render_answer')renderCalls++;
  return original(name,args,signal);
 };
 const audit=async(id:string)=>(await readFile(path.join(dir,'audit',id+'.jsonl'),'utf8')).trim().split('\n').map(v=>JSON.parse(v));
 const wait=async(id:string)=>{
  const end=Date.now()+20000;
  while(Date.now()<end){const run=await manager.getRun(id);if(!manager.activeFor(run.conversationId))return run;await delay(20);}
  throw Error('Offline native lifecycle timed out');
 };
 const makeChat=async()=>{
  const chat={id:randomUUID(),projectId:'lifecycle',title:'Fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
  await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);return chat;
 };
 const startCleaning=()=>answer(tool('process_documents',{document_ids:['doc']}),{stopReason:'toolUse'});
 try{
  await service.call('create_project',{project_id:'lifecycle',name:'Offline lifecycle'});
  const chat=await makeChat();remaining=[[1,2],[2],[]];
  faux.setResponses([startCleaning(),answer('尚未完成 {{not.a.table}}'),answer(tool('get_cleaning_batch',{processing_id:pid}),{stopReason:'toolUse'}),answer('继续 {{not.a.table}}'),answer('已完成 {{not.a.table}}')]);
  const first=await manager.start(chat,'完整入库',[]),completed=await wait(first.id),events=await audit(first.id);
  assert.equal(completed.status,'completed',completed.error);assert.equal(progressCalls,3);assert.equal(renderCalls,0);
  assert.equal(events.filter(e=>e.type==='ingestion_continuation').length,2);
  assert.equal(events.filter(e=>e.type.startsWith('answer_bind')).length,0);
  assert.equal(faux.getPendingResponseCount(),0);
  const native=(await readFile(path.join(dir,'workspaces/lifecycle',chat.id,'sessions/session.jsonl'),'utf8')).trim().split('\n').map(v=>JSON.parse(v));
  assert.equal(native.filter(v=>v.customType==='ingestion-continuation').length,2);
  assert.equal(native.filter(v=>v.customType==='answer_reference_error').length,0);
  assert.equal((await manager.getConversation(chat.id)).messages.at(-1).content,'已完成 {{not.a.table}}');

  // New analysis in the same native session must regain A1 and never continue the old ingestion.
  faux.setResponses([answer(tool('get_analysis_status',{run_id:'fixture'}),{stopReason:'toolUse'}),answer('{{values.missing.value}}'),answer('{{values.total.value}}\n{{table:values}}')]);
  const second=await manager.start(await manager.getConversation(chat.id),'分析已准备数据',[]),analyzed=await wait(second.id),analysisEvents=await audit(second.id);
  assert.equal(analyzed.status,'completed',analyzed.error);assert.equal(progressCalls,3);
  assert.equal(analysisEvents.filter(e=>e.type==='answer_binding_error').length,1);
  assert.equal(analysisEvents.filter(e=>e.type==='answer_bound').length,1);
  assert.equal(analysisEvents.filter(e=>e.type==='ingestion_continuation').length,0);
  assert.match((await manager.getConversation(chat.id)).messages.at(-1).content,/12.50 CNY 元/);
  assert.equal(faux.getPendingResponseCount(),0);

  // One native continuation without committed progress fails honestly; no A1 repair loop.
  const stalledChat=await makeChat(),renderBefore=renderCalls;remaining=[[1],[1]];
  faux.setResponses([startCleaning(),answer('{{still.unresolved.value}}'),answer('{{still.unresolved.value}}')]);
  const third=await manager.start(stalledChat,'完整入库',[]),stalled=await wait(third.id),stalledEvents=await audit(third.id);
  assert.equal(stalled.status,'failed');assert.match(stalled.error,/自动续跑没有推进/);assert.equal(renderCalls,renderBefore);
  assert.equal(stalledEvents.filter(e=>e.type==='ingestion_continuation').length,1);
  assert.equal(stalledEvents.filter(e=>e.type==='ingestion_stalled').length,1);
  assert.equal(stalledEvents.filter(e=>e.type.startsWith('answer_bind')).length,0);
  assert.equal(faux.getPendingResponseCount(),0);

  // Simulate a persisted queued recovery whose native transcript ends in assistant stop.
  // Remaining database work must override that stop marker, without replaying process_documents.
  await manager.shutdown();
  await service.putState('lifecycle','runs',third.id,{...stalled,status:'queued'});
  remaining=[[1],[]];const progressBeforeRecovery=progressCalls,callsBeforeRecovery=faux.state.callCount;
  faux.setResponses([answer('恢复完成 {{not.a.table}}')]);
  await manager.recover('lifecycle');const recovered=await wait(third.id);
  assert.equal(recovered.status,'completed',recovered.error);
  assert.equal(progressCalls-progressBeforeRecovery,2);assert.equal(faux.state.callCount-callsBeforeRecovery,1);
  assert.equal((await audit(third.id)).filter(e=>e.type==='processing_started').length,1);
  assert.equal(renderCalls,renderBefore);assert.equal(faux.getPendingResponseCount(),0);

  // An unresolved A1 repair is attempted only once and cannot activate ingestion continuation.
  const invalidChat=await makeChat(),priorProgress=progressCalls;
  faux.setResponses([answer('{{absent.row.value}}'),answer('{{absent.row.value}}')]);
  const fourth=await manager.start(invalidChat,'分析',[]),invalid=await wait(fourth.id),invalidEvents=await audit(fourth.id);
  assert.equal(invalid.status,'failed');assert.equal(progressCalls,priorProgress);
  assert.equal(invalidEvents.filter(e=>e.type==='answer_binding_error').length,2);
  assert.equal(invalidEvents.filter(e=>e.type==='ingestion_continuation').length,0);
  assert.equal(faux.getPendingResponseCount(),0);
  const invalidNative=(await readFile(path.join(dir,'workspaces/lifecycle',invalidChat.id,'sessions/session.jsonl'),'utf8')).trim().split('\n').map(v=>JSON.parse(v));
  assert.equal(invalidNative.filter(v=>v.customType==='answer_reference_error').length,1);
 }finally{await manager.shutdown();await service.close();}
});

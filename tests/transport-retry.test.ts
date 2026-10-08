import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {ModelRuntime,SettingsManager} from '@earendil-works/pi-coding-agent';
import {createAssistantMessageEventStream,isRetryableAssistantError,type AssistantMessage} from '@earendil-works/pi-ai';
import {fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';
import {transientTransportError,transportRetryExtension,TRANSPORT_RETRY} from '../server/transport-retry.js';

const originalDrop='stream error: stream disconnected before completion: stream closed before response.completed';
const failed=(errorMessage:string)=>answer('incomplete response',{stopReason:'error',errorMessage});
const usage=(message:AssistantMessage,input:number,output:number):AssistantMessage=>({...message,usage:{input,output,cacheRead:0,cacheWrite:0,totalTokens:input+output,cost:{input:input*.000001,output:output*.000002,cacheRead:0,cacheWrite:0,total:input*.000001+output*.000002}}});

test('strict transport classification includes real stream drop and TLS, excludes business/configuration errors',()=>{
 assert.equal(isRetryableAssistantError(failed(originalDrop)),false,'pinned Pi classification gap');
 for(const error of [originalDrop,'TLS connection closed','Client network socket disconnected before secure TLS connection was established: TLS handshake failed','TLS handshake timed out','HTTP 500 internal server error','503 Service Unavailable','status code: 502','{"status":504}','server_overloaded: model at capacity','overloaded_error','fetch failed','ECONNRESET','stream ended before message_stop'])assert.equal(transientTransportError(error),true,error);
 for(const error of ['利润 500 不等于分项','unknown table t500','invalid_request_error: HTTP 500','HTTP 400: invalid schema','401 authentication failed','402 insufficient balance','429 insufficient_quota','monthly usage limit reached','certificate has expired: TLS error','self-signed certificate','context length exceeded','tool validation error','missing document','unknown provider error','aborted'])assert.equal(transientTransportError(error),false,error);
 assert.deepEqual([1,2,3].map(n=>Math.min(TRANSPORT_RETRY.baseDelayMs*2**(n-1),TRANSPORT_RETRY.maxAgentDelayMs)),[2000,4000,8000]);
});

test('classification leaves native context-overflow recovery enabled',async()=>{
 const settings=SettingsManager.inMemory({retry:TRANSPORT_RETRY});let onEnd:any;
 await transportRetryExtension(settings)({on:(_name:string,handler:any)=>{onEnd=handler;}} as any);
 const message=failed('maximum context length exceeded');
 assert.equal(onEnd({message},{model:{contextWindow:128000}}),undefined);
 assert.equal(settings.getRetrySettings().enabled,true);
});

// Full host audit + budget + native Pi, scripted provider and temporary MCP database.
// No live HTTP listener, Docker, real documents or paid model calls.
test('native retry retains attempts and usage, resumes after committed tools, stops on exhaustion/business/cancel',{timeout:120000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-transport-retry-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'transport-offline',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const originalStream=ModelRuntime.prototype.streamSimple;
 let responses:AssistantMessage[]=[],contexts:any[]=[],calls=0;
 // Patch before sessionFor captures streamSimple, so every attempt traverses real host accounting.
 ModelRuntime.prototype.streamSimple=function(model,context,options){
  const stream=createAssistantMessageEventStream();calls++;contexts.push(structuredClone(context));
  assert.equal(options?.maxRetries,0,'provider-hidden retries must be disabled on main calls');
  const next=responses.shift();assert.ok(next,'unexpected model request');
  const message={...next,api:model.api,model:model.id,provider:model.provider,timestamp:Date.now()};
  void (async()=>{
   await options?.onPayload?.({messages:context.messages},model);
   await options?.onResponse?.({status:200,headers:{'content-type':'text/event-stream'}},model);
   stream.push({type:'start',partial:message});
   if(message.stopReason==='error'||message.stopReason==='aborted')stream.push({type:'error',reason:message.stopReason,error:message});
   else stream.push({type:'done',reason:message.stopReason as 'stop'|'toolUse'|'length',message});
  })();
  return stream;
 };
 const originalCall=service.call.bind(service);let commits=0,progressCalls=0;
 service.call=async(name,args,signal)=>{
  if(name==='begin_script_cleaning')return {status:'ok',data:{processing_id:'fixture-processing',state:'normalizing'}};
  if(name==='commit_cleaning_result'){commits++;return {status:'ok',data:{state:'normalizing',fixtureCommitted:true}};}
  if(name==='advance_cleaning_round'){progressCalls++;return {status:'ok',data:{pending_tables:{},pending_pages:{}}};}
  if(name==='cancel_processing')return {status:'ok',data:{state:'cancelled'}};
  return originalCall(name,args,signal);
 };
 const audit=async(id:string)=>(await readFile(path.join(dir,'audit',id+'.jsonl'),'utf8')).trim().split('\n').map(v=>JSON.parse(v));
 const wait=async(id:string)=>{
  const deadline=Date.now()+40000;
  while(true){const state=await manager.getRun(id);if(!manager.activeFor(state.conversationId))return state;if(Date.now()>deadline)throw Error('offline retry timeout');await delay(20);}
 };
 const makeChat=async()=>{const c={id:randomUUID(),projectId:'transport',title:'Fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};await service.putState(c.projectId,'conversations',c.id,c);manager.indexConversation(c.id,c.projectId);return c;};
 const run=async(script:AssistantMessage[],chat?:any)=>{
  responses=script;contexts=[];const c=chat??await makeChat(),before=calls;
  const started=await manager.start(c,'执行合成任务',[]),state=await wait(started.id);
  assert.equal(responses.length,0);return {state,events:await audit(started.id),chat:await manager.getConversation(c.id),count:calls-before};
 };
 try{
  await service.call('create_project',{project_id:'transport',name:'Offline retry fixture'});
  const start=usage(answer(tool('process_documents',{document_ids:['synthetic']}),{stopReason:'toolUse'}),10,1);
  const commit=usage(answer(tool('commit_cleaning_result',{processing_id:'fixture-processing',run_id:'synthetic-run'}),{stopReason:'toolUse'}),20,2);
  const success=await run([start,commit,usage(failed(originalDrop),30,3),failed('TLS connection closed'),usage(answer('完成。'),40,4)]);
  assert.equal(success.state.status,'completed',success.state.error);assert.equal(success.count,5);assert.equal(commits,1);assert.equal(progressCalls,1);
  const starts=success.events.filter(e=>e.type==='transport_retry_start');assert.deepEqual(starts.map(e=>[e.data.attempt,e.data.delayMs]),[[1,2000],[2,4000]]);
  assert.equal(success.events.filter(e=>e.type==='transport_retry_end'&&e.data.success).length,1);
  const requests=success.events.filter(e=>e.type==='model_request'),settled=success.events.filter(e=>e.type==='model_usage');
  assert.equal(requests.length,5);assert.equal(new Set(requests.map(e=>e.data.requestId)).size,5);assert.equal(settled.length,5);
  assert.equal(settled[2].data.error,originalDrop);assert.equal(settled[3].data.error,'TLS connection closed');assert.equal(settled[3].data.usageKnown,false);
  assert.equal(success.state.usage.calls,5);assert.equal(success.state.usage.unknownCalls,1);assert.equal(success.state.usage.input,100);assert.equal(success.state.usage.output,10);
  assert.equal(success.state.usage.phases.cleaning.calls,4,'failed cleaning attempts remain preparation usage');
  assert.equal(success.state.usage.phases.cleaning.unknownCalls,1);
  const native=(await readFile(path.join(dir,'workspaces/transport',success.chat.id,'sessions/session.jsonl'),'utf8')).trim().split('\n').map(v=>JSON.parse(v));
  assert.equal(native.filter(e=>e.message?.role==='assistant'&&e.message.stopReason==='error').length,2,'raw failed attempts persist');
  for(const context of contexts.slice(3)){
   assert.ok(context.messages.some((m:any)=>m.role==='toolResult'&&m.toolName==='commit_cleaning_result'));
   assert.equal(context.messages.some((m:any)=>m.role==='assistant'&&m.stopReason==='error'),false,'native retry omits failures only from projection');
  }

  const exhausted=await run(Array.from({length:4},()=>failed(originalDrop)));
  assert.equal(exhausted.state.status,'failed');assert.equal(exhausted.count,4);assert.match(exhausted.state.error,/已重试 3 次/);assert.match(exhausted.state.error,/stream closed before response.completed/);
  assert.deepEqual(exhausted.events.filter(e=>e.type==='transport_retry_start').map(e=>e.data.delayMs),[2000,4000,8000]);
  assert.equal(exhausted.events.filter(e=>e.type==='transport_retry_end'&&!e.data.success).length,1);
  assert.equal(exhausted.state.usage.calls,4);assert.equal(exhausted.state.usage.unknownCalls,4);assert.equal(exhausted.state.usage.costUsd,null);
  assert.equal(exhausted.events.some(e=>e.type==='ingestion_stalled'),false,'transport exhaustion is distinct from logical stall');

  const business=await run([failed('invalid_request_error: HTTP 500 schema validation')]);
  assert.equal(business.state.status,'failed');assert.equal(business.count,1);assert.equal(business.events.some(e=>e.type.startsWith('transport_retry')),false);
  // Reusing that session must classify the next error afresh, not remain disabled.
  const reused=await run([failed('HTTP 503 Service Unavailable'),usage(answer('恢复。'),5,1)],business.chat);
  assert.equal(reused.state.status,'completed',reused.state.error);assert.equal(reused.count,2);

  // Evaluation budgets still take priority over the three-retry allowance.
  const budgetChat=await makeChat();responses=[failed(originalDrop),failed(originalDrop)];
  const budgetBefore=calls,budgetRun=await manager.start(budgetChat,'预算停止测试',[],undefined,{profile:'financial',budget_group_id:'retry-budget',isolation_key:'retry-budget',analysis_only:true,budget:{max_model_calls:2,max_input_tokens:1000000,max_output_tokens:100000,max_total_tokens:1100000,max_wall_seconds:60}});
  const budgetStopped=await wait(budgetRun.id);
  assert.equal(budgetStopped.status,'failed');assert.match(budgetStopped.error,/evaluation_budget_exceeded:max_model_calls/);
  assert.equal(calls-budgetBefore,2);assert.equal(responses.length,0);assert.equal(budgetStopped.usage.calls,2);assert.equal(budgetStopped.usage.unknownCalls,2);
  const budgetEnd=(await audit(budgetRun.id)).find(e=>e.type==='transport_retry_end');
  assert.equal(budgetEnd.data.success,false);assert.match(budgetEnd.data.error,/evaluation_budget_exceeded:max_model_calls/);

  const cancelChat=await makeChat();responses=[failed(originalDrop)];const before=calls,started=await manager.start(cancelChat,'取消测试',[]);
  const deadline=Date.now()+10000;
  while(!manager.sessions.get(cancelChat.id)?.session.isRetrying){if(Date.now()>deadline)throw Error('retry did not start');await delay(10);}
  const cancelled=await manager.cancel(started.id);assert.equal(cancelled.status,'cancelled');assert.equal(calls-before,1);assert.equal(cancelled.usage.unknownCalls,1);
  assert.equal((await audit(started.id)).filter(e=>e.type==='transport_retry_end'&&!e.data.success).length,1);
 }finally{ModelRuntime.prototype.streamSimple=originalStream;await manager.shutdown();await service.close();}
});

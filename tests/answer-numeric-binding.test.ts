import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {createFauxCore,fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';

// Actual F2_D1 trigger through native Pi + MCP stdio; no model calls or HTTP listener.
test('F2_D1 non-monetary CSV cell reaches one A1 repair turn and persists the repaired answer',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-numeric-binding-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'numeric-offline-fixture',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const faux=createFauxCore({tokensPerSecond:0}),sessionFor=manager.sessionFor.bind(manager);
 manager.sessionFor=async(...args:any[])=>{const entry=await sessionFor(...args);entry.runtime.streamSimple=faux.streamSimple;return entry;};
 const original=service.call.bind(service);
 service.call=async(name,args,signal)=>{
  if(name==='get_analysis_status')return {status:'ok',data:{status:'succeeded',artifacts:[],numeric_tables:{profit_cashflow_workpaper:{
   columns:{metric:{},value:{unit:args.run_id==='repaired'?'%':'百万元'}},rows:[{metric:'毛利率',value:'41.38%'}],row_keys:['毛利率']}}}};
  return original(name,args,signal);
 };
 try{
  await service.call('create_project',{project_id:'numeric-binding',name:'Offline numeric binding'});
  const chat:any={id:randomUUID(),projectId:'numeric-binding',title:'Fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
  await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);
  faux.setResponses([
   answer(tool('get_analysis_status',{run_id:'raw-csv'}),{stopReason:'toolUse'}),answer('{{table:profit_cashflow_workpaper}}'),
   answer(tool('get_analysis_status',{run_id:'repaired'}),{stopReason:'toolUse'}),
   answer('{{profit_cashflow_workpaper.毛利率.value}}\n{{table:profit_cashflow_workpaper}}'),
  ]);
  const run=await manager.start(chat,'呈现毛利率',[]);let state;
  do{await delay(20);state=await manager.getRun(run.id);}while(manager.activeFor(chat.id));
  assert.equal(state.status,'completed',state.error);assert.equal(faux.getPendingResponseCount(),0);
  const content=(await manager.getConversation(chat.id)).messages.at(-1).content;
  assert.match(content,/41\.38 %/);assert.match(content,/\| 毛利率 \| 41\.38 \|/);assert.ok(!content.includes('{{'));
  const audit=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(x=>JSON.parse(x));
  const errors=audit.filter(e=>e.type==='answer_binding_error');assert.equal(errors.length,1);
  assert.equal(errors[0].data.code,'answer_reference_error');assert.match(errors[0].data.message,/41\.38%.*百万元.*可用引用/);
  assert.equal(audit.filter(e=>e.type==='answer_bound').length,1);
  const native=(await readFile(path.join(dir,'workspaces/numeric-binding',chat.id,'sessions/session.jsonl'),'utf8')).trim().split('\n').map(x=>JSON.parse(x));
  assert.equal(native.filter(e=>e.customType==='answer_reference_error').length,1);
  const last=native.findLast(e=>e.type==='message'&&e.message?.role==='assistant');
  assert.equal(last.message.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join(''),content);
 }finally{await manager.shutdown();await service.close();}
});

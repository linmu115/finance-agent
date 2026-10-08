import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {evaluationIsolation,bindEvaluationIsolation} from '../server/evaluation-isolation.js';
import {normalizeEvaluation,EvaluationBudgets,EvaluationBudget} from '../server/evaluation-budget.js';
import {createFauxCore,fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';

const budget={max_model_calls:100,max_input_tokens:1000000,max_output_tokens:100000,max_total_tokens:1100000,max_wall_seconds:300};
const options=(key?:string,profile:'prepared'|'financial'='financial')=>({profile,budget_group_id:profile+'-shared-budget',budget,...(key===undefined?{}:{isolation_key:key})});

test('isolation is validated, fixed for a conversation, and independent of budget grouping',()=>{
 assert.equal(normalizeEvaluation(options('F1_D2_F_r1'))?.isolation_key,'F1_D2_F_r1');
 for(const key of ['',null,'../other','a b','a'.repeat(121)])assert.throws(()=>normalizeEvaluation({...options(),isolation_key:key}),/invalid_evaluation_isolation_key/);
 const chat:any={messages:[]};bindEvaluationIsolation(chat,'a');chat.messages.push({role:'user'});
 bindEvaluationIsolation(chat,'a');assert.throws(()=>bindEvaluationIsolation(chat,'b'),/isolation_conflict/);
 assert.throws(()=>bindEvaluationIsolation(chat),/isolation_conflict/);
 assert.throws(()=>bindEvaluationIsolation({messages:[{}]} as any,'a'),/isolation_conflict/);
 bindEvaluationIsolation({messages:[{}]} as any);
 const clock={scheduleDeadline:false},groups=new EvaluationBudgets(clock);
 const a=groups.acquire('p',options('a')),b=groups.acquire('p',options('b'));
 assert.equal(a,b);assert.equal(a.snapshot().isolation_key,undefined);
 const restored=new EvaluationBudget(options('a'),clock,a.snapshot());assert.deepEqual(restored.options,a.options);
 groups.dispose();restored.dispose();
});

test('native runs and MCP enforce artifact scope, preserve same-chain reuse and ordinary sharing',{timeout:90000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-evaluation-isolation-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 const {ResearchWorkspace,artifactStore,deliveryFile}=await import('../server/research-artifacts.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'offline-isolation',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const faux=createFauxCore({tokensPerSecond:0}),sessionFor=manager.sessionFor.bind(manager);
 manager.sessionFor=async(...args:any[])=>{const e=await sessionFor(...args);e.runtime.streamSimple=faux.streamSimple;return e;};
 const ws=new ResearchWorkspace(service);
 const chat=async()=>{const c:any={id:randomUUID(),projectId:'p',title:'Isolation fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};await service.putState('p','conversations',c.id,c);manager.indexConversation(c.id,'p');return c;};
 const run=async(c:any,key:string|undefined,calls:{name:string,args:any}[],profile:'prepared'|'financial'='financial')=>{
  faux.setResponses([...calls.map(c=>answer(tool(c.name,c.args),{stopReason:'toolUse'})),answer('已完成。')]);
  const started=await manager.start(c,'执行请求。',[],undefined,options(key,profile));
  const deadline=Date.now()+40000;
  while(manager.activeFor(c.id)){if(Date.now()>deadline)throw Error('native fixture timeout');await delay(20);}
  const result=await manager.getRun(started.id);assert.equal(result.status,'completed',result.error);
  assert.equal(faux.getPendingResponseCount(),0);
  const events=(await readFile(path.join(dir,'audit',started.id+'.jsonl'),'utf8')).trim().split('\n').map(s=>JSON.parse(s));
  assert.equal(events.find(e=>e.type==='run_config').data.isolation_key,key);
  assert.equal(result.request.evaluation.isolation_key,key);
  return {events,chat:await manager.getConversation(c.id)};
 };
 const results=(r:any,name:string)=>r.events.filter((e:any)=>e.type==='tool_result'&&e.data.name===name).map((e:any)=>e.data.result.data);
 const errors=(r:any)=>r.events.filter((e:any)=>e.type==='tool_error').map((e:any)=>e.data.message);
 try{
  await service.call('create_project',{project_id:'p',name:'Shared sources'});
  const spec=(await service.call('get_research_model_schema',{project_id:'p',kind:'dcf_fcf'})).data.synthetic_example;
  const old=await ws.model('p',{kind:'dcf_fcf',title:'Before freeze',spec});
  const a=await run(await chat(),'chain_a',[{name:'run_financial_model',args:{kind:'dcf_fcf',title:'A',spec}}]);
  const own=results(a,'run_financial_model')[0];assert.equal(own.isolation_key,'chain_a');
  const b=await run(await chat(),'chain_b',[
   {name:'list_research_artifacts',args:{}},
   ...[own.id,old.id,'absent'].map(id=>({name:'read_research_artifact',args:{artifact_id:id,revision_id:'wrong'}})),
   {name:'run_financial_model',args:{kind:'dcf_fcf',title:'Forbidden update',source_model:{artifact_id:own.id}}},
   {name:'run_financial_model',args:{kind:'dcf_fcf',title:'B',spec}},
  ]);
  assert.deepEqual(results(b,'list_research_artifacts')[0].artifacts,[]);
  assert.equal(errors(b).length,4);for(const e of errors(b))assert.equal(e,'研究成果不存在');
  const other=results(b,'run_financial_model')[0];assert.equal(other.isolation_key,'chain_b');
  // Same native conversation, with the original key, can update the first model.
  const continued=await run(a.chat,'chain_a',[
   {name:'read_research_artifact',args:{artifact_id:own.id}},
   {name:'run_financial_model',args:{kind:'dcf_fcf',title:'A continuation',source_model:{artifact_id:own.id}}},
   {name:'read_research_artifact',args:{artifact_id:other.id}},
  ]);
  assert.equal(results(continued,'read_research_artifact')[0].id,own.id);
  assert.equal(results(continued,'run_financial_model')[0].source_model.artifact_id,own.id);
  assert.deepEqual(errors(continued),['研究成果不存在']);
  await assert.rejects(()=>manager.start(continued.chat,'switch',[],undefined,options('chain_b')),/isolation_conflict/);
  await assert.rejects(()=>manager.start(continued.chat,'omit',[],undefined,options()),/isolation_conflict/);
  await manager.shutdown();
  const persisted=await manager.getConversation(continued.chat.id);
  assert.equal(persisted.evaluationIsolationKey,'chain_a');
  const reopened=await run(persisted,'chain_a',[{name:'list_research_artifacts',args:{}}]);
  assert.equal(results(reopened,'list_research_artifacts')[0].artifacts.length,2);
  const same=await run(await chat(),'chain_a',[{name:'list_research_artifacts',args:{}}]);
  assert.equal(results(same,'list_research_artifacts')[0].artifacts.length,2);
  const ordinary=await run(await chat(),undefined,[{name:'list_research_artifacts',args:{}}]);
  assert.equal(results(ordinary,'list_research_artifacts')[0].artifacts.length,4);

  // Real MCP metadata propagates even when concurrent calls carry different keys.
  const refs={saved:{artifact_id:own.id,revision_id:own.revision_id}};
  const calls=await Promise.allSettled([
   evaluationIsolation.run('chain_a',()=>service.call('deliver_research_models',{project_id:'p',model_refs:refs})),
   evaluationIsolation.run('chain_b',()=>service.call('deliver_research_models',{project_id:'p',model_refs:refs})),
  ]);
  assert.equal(calls[0].status,'fulfilled');assert.equal(calls[1].status,'rejected');
  if(calls[1].status==='rejected')assert.equal(calls[1].reason.message,'model_revision_not_found_in_project');
  await evaluationIsolation.run('chain_b',async()=>{
   for(const ref of [refs.saved,{artifact_id:old.id,revision_id:old.revision_id},{artifact_id:'absent',revision_id:'absent'}]){
    await assert.rejects(()=>service.call('run_analysis',{project_id:'p',code:'pass',model_refs:{saved:ref}}),/^Error: model_revision_not_found_in_project$/);
   }
   // Cross-chain errors match nonexistent run IDs, before consulting any sandbox.
   for(const run_id of ['foreign-analysis','absent'])await assert.rejects(()=>service.call('get_artifact',{project_id:'p',run_id,name:'result.txt'}),/^Error: analysis_not_found_in_project$/);
  });
  const delivery=own.delivery,filename=decodeURIComponent(delivery.files[0].url.split('/').at(-1)!);
  await evaluationIsolation.run('chain_a',()=>deliveryFile('p',delivery.id,filename));
  for(const id of [delivery.id,'0'.repeat(32)])await assert.rejects(()=>evaluationIsolation.run('chain_b',()=>deliveryFile('p',id,filename)),/^Error: 交付不存在$/);
  await deliveryFile('p',delivery.id,filename);

  // Report dependencies and revisions use the same filtered artifact store.
  const content={original_text:'Original',issues:[],verified_claims:[]};
  const report=await evaluationIsolation.run('chain_a',()=>ws.report('p',{title:'A report',kind:'report_correction',content,dependencies:[{kind:'artifact',id:own.id}]}));
  await assert.rejects(()=>evaluationIsolation.run('chain_b',()=>ws.get('p',report.id)),/^Error: 研究成果不存在$/);
  await assert.rejects(()=>evaluationIsolation.run('chain_b',()=>ws.report('p',{title:'foreign reference',kind:'report_correction',content,dependencies:[{kind:'artifact',id:own.id}]})),/^Error: 研究成果不存在$/);
  assert.equal((await ws.get('p',report.id)).id,report.id);
  // Concurrent saves are serialized without losing the scope captured by each caller.
  const saved=await Promise.all(['chain_a','chain_b'].map(key=>evaluationIsolation.run(key,()=>artifactStore.save('p',{kind:'fixture',title:key,dependencies:[]}))));
  assert.deepEqual(saved.map(a=>a.isolation_key),['chain_a','chain_b']);
  const prepared=await run(await chat(),'chain_p',[{name:'get_artifact',args:{run_id:'foreign-analysis',name:'result.txt'}}],'prepared');
  assert.deepEqual(errors(prepared),['analysis_not_found_in_project']);

  // Workpaper deliveries follow the same manifest contract as model deliveries.
  const id='1'.repeat(32),folder=path.join(dir,'research/p/deliveries',id),bytes=Buffer.from('own workpaper');await mkdir(folder,{recursive:true});
  await writeFile(path.join(folder,'table.csv'),bytes);
  await writeFile(path.join(folder,'delivery.json'),JSON.stringify({isolation_key:'chain_a',files:[{name:'table.csv',size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')}]}));
  assert.equal((await evaluationIsolation.run('chain_a',()=>deliveryFile('p',id,'table.csv'))).bytes.toString(),'own workpaper');
  await assert.rejects(()=>evaluationIsolation.run('chain_b',()=>deliveryFile('p',id,'table.csv')),/^Error: 交付不存在$/);
  assert.equal((await deliveryFile('p',id,'table.csv')).bytes.toString(),'own workpaper');
 }finally{await manager.shutdown();await service.close();}
});

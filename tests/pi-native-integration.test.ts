import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,type ServerResponse} from 'node:http';
import {mkdtemp,mkdir,writeFile,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

test('native model catalog, steering/follow-up and durable restart with queued input',{timeout:90000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-native-'));process.env.FINANCE_DATA_DIR=dir;process.env.PI_CODING_AGENT_DIR=path.join(dir,'global-pi');
 await mkdir(process.env.PI_CODING_AGENT_DIR,{recursive:true});
 const requests:any[]=[],held=new Map<string,ServerResponse>();
 const text=(v:any)=>typeof v==='string'?v:(v||[]).map((b:any)=>b.text||'').join('\n');
 const reply=(res:ServerResponse,content:string)=>{if(res.destroyed)return;res.writeHead(200,{'Content-Type':'text/event-stream'});const p={id:'native',object:'chat.completion.chunk',created:1,model:'native-model'};res.write('data: '+JSON.stringify({...p,choices:[{index:0,delta:{role:'assistant',content},finish_reason:null}]})+'\n\n');res.end('data: '+JSON.stringify({...p,choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:30,completion_tokens:10,total_tokens:40}})+'\n\ndata: [DONE]\n\n');};
 const mock=createServer(async(req,res)=>{let raw='';for await(const c of req)raw+=c;const body=JSON.parse(raw);requests.push(body);const last=text(body.messages.findLast((m:any)=>m.role==='user')?.content),task=last.split('\n用户任务：\n').at(-1)!;
  if(task.startsWith('hold-')){held.set(task,res);return;}
  reply(res,last.includes('服务已恢复')?'continued saved task':task+' done');
 });await new Promise<void>(r=>mock.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+(mock.address() as any).port+'/v1';
 await writeFile(path.join(process.env.PI_CODING_AGENT_DIR,'models.json'),JSON.stringify({providers:{'native-fixture':{baseUrl:url,apiKey:'fixture-key',api:'openai-completions',models:[{id:'native-model',name:'Native catalog fixture',reasoning:false,input:['text'],contextWindow:64000,maxTokens:8192,compat:{supportsStore:false,maxTokensField:'max_tokens'}}]},'thinking-gateway':{baseUrl:url,apiKey:'fixture-key',api:'openai-completions',models:[{id:'thinking-model',name:'Thinking gateway',reasoning:true,input:['text'],contextWindow:1000000,maxTokens:65536,compat:{thinkingFormat:'deepseek',supportsReasoningEffort:true,maxTokensField:'max_tokens'}}]}}}));
 const {loadSettings,saveSettings}=await import('../server/config.js');const {configuredModel,modelCatalog}=await import('../server/model-runtime.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{provider:'native-fixture',baseUrl:'',model:'native-model',apiKey:'',contextWindow:64000,maxTokens:512}});
 const service=new FinanceService();await service.connect();let manager=new RunManager(service);
 const until=async(check:()=>Promise<any>|any)=>{const end=Date.now()+25000;while(Date.now()<end){const value=await check();if(value)return value;await delay(20);}throw Error('native fixture timed out');};
 const wait=(id:string)=>until(async()=>{const run=await manager.getRun(id);return !manager.activeFor(run.conversationId)&&['completed','failed','cancelled'].includes(run.status)?run:undefined;});
 const make=async()=>{const chat={id:randomUUID(),projectId:'native',title:'新对话',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};await service.putState('native','conversations',chat.id,chat);manager.indexConversation(chat.id,'native');return chat;};
 try{
  const catalog=await modelCatalog();assert.ok(catalog.models.some(m=>m.provider==='native-fixture'&&m.id==='native-model'));assert.ok(!JSON.stringify(catalog).includes('fixture-key'));
  const gateway=await configuredModel({provider:'thinking-gateway',baseUrl:'',model:'thinking-model',apiKey:'',contextWindow:4096,maxTokens:512});
  assert.equal(gateway.model.contextWindow,1000000);await gateway.runtime.completeSimple(gateway.model,{messages:[{role:'user',content:'catalog ping',timestamp:Date.now()}]},{reasoning:'low',maxTokens:512});
  assert.equal(requests.at(-1).thinking?.type,'enabled');assert.equal(requests.at(-1).reasoning_effort,'low');
  await service.call('create_project',{project_id:'native',name:'Native integration'});
  const chat=await make(),first=await manager.start(chat,'hold-steering',[]);await until(()=>held.has('hold-steering'));
  const steer=await manager.start(await manager.getConversation(chat.id),'steer-now',[]);
  const follow=await manager.start(await manager.getConversation(chat.id),'follow-later',[],undefined,undefined,undefined,'followUp');
  assert.equal(steer.id,first.id);assert.equal(follow.id,first.id);assert.notEqual(steer.userMessageId,follow.userMessageId);
  reply(held.get('hold-steering')!,'original done');const done=await wait(first.id);assert.equal(done.status,'completed',done.error);assert.ok(done.queuedInputs.every((q:any)=>q.delivered));
  const saved=await manager.getConversation(chat.id);assert.deepEqual(saved.messages.filter(m=>m.role==='user').map(m=>m.content),['hold-steering','steer-now','follow-later']);
  assert.deepEqual(saved.messages.filter(m=>m.role==='assistant').map(m=>m.content),['original done','steer-now done','follow-later done']);
  await manager.shutdown();done.status='running';await service.putState('native','runs',done.id,done);manager=new RunManager(service);
  const settledRequestCount=requests.length;await manager.recover('native');assert.equal((await wait(done.id)).status,'completed');assert.equal(requests.length,settledRequestCount,'a final response already saved by Pi must not be regenerated after a host crash');
  const restarted=await make(),interrupted=await manager.start(restarted,'hold-restart',[]);await until(()=>held.has('hold-restart'));
  await manager.start(await manager.getConversation(restarted.id),'after-restart',[],undefined,undefined,undefined,'followUp');
  await manager.shutdown();assert.equal((await manager.getRun(interrupted.id)).status,'queued');
  const before=requests.length;manager=new RunManager(service);await manager.recover('native');const resumed=await wait(interrupted.id);assert.equal(resumed.status,'completed',resumed.error);
  assert.ok(requests.slice(before).some(b=>JSON.stringify(b.messages).includes('服务已恢复')));
  const recovered=await manager.getConversation(restarted.id);assert.equal(recovered.messages.at(-1)?.content,'after-restart done');assert.equal(recovered.messages.filter(m=>m.role==='user'&&m.content==='after-restart').length,1);
  const events=(await readFile(path.join(dir,'audit',interrupted.id+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse).filter(r=>r.type==='event');assert.equal(new Set(events.map(r=>r.data.seq)).size,events.length,'SSE sequence must not reset on restart');
 }finally{await manager.shutdown();await service.close();for(const res of held.values())reply(res,'cleanup');await new Promise<void>(r=>{mock.close(()=>r());mock.closeAllConnections();});}
});

test('recovery restores successful receipts without replaying tools and flags uncertain writes',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-receipts-'));const {SessionManager}=await import('@earendil-works/pi-coding-agent');const {repairInterruptedTools,operationKey}=await import('../server/session-recovery.js');
 const session=SessionManager.open(path.join(dir,'session.jsonl'),dir,dir);
 session.appendMessage({role:'user',content:'save reports',timestamp:1});
 session.appendMessage({role:'assistant',content:[{type:'toolCall',id:'saved',name:'save_research_report',arguments:{title:'A'}},{type:'toolCall',id:'uncertain',name:'request_database_operation',arguments:{operation:'sql',reason:'fixture',sql:'SELECT 1'}}],api:'openai-completions',provider:'fixture',model:'fixture',usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'toolUse',timestamp:2});
 const audit=path.join(dir,'audit.jsonl');await writeFile(audit,[{type:'tool_request',data:{toolCallId:'saved'}},{type:'tool_result',data:{toolCallId:'saved',result:{status:'ok',data:{id:'report-a',revision_id:'revision-a',result:{value:'123.45'}}}}},{type:'tool_request',data:{toolCallId:'uncertain'}}].map(x=>JSON.stringify(x)).join('\n'));
 const uncertain=await repairInterruptedTools(session,audit);assert.equal(uncertain.size,1);assert.ok(uncertain.has(operationKey('request_database_operation',{sql:'SELECT 1',reason:'fixture',operation:'sql'})));
 const results=session.buildSessionContext().messages.filter(m=>m.role==='toolResult');assert.equal(results.length,2);assert.ok(JSON.stringify(results[0]).includes('revision-a'));assert.ok(JSON.stringify(results[0]).includes('123.45'));assert.equal(results[1].isError,true);
 await repairInterruptedTools(session,audit);assert.equal(session.buildSessionContext().messages.filter(m=>m.role==='toolResult').length,2);
 const again=await repairInterruptedTools(session,audit);assert.equal(again.size,1,'a persisted aborted/unknown tool receipt still needs reconciliation on restart');
});

test('large document and metric requests batch without silently dropping work',{timeout:20000},async()=>{
 const {RunManager}=await import('../server/runs.js');const calls:any[]=[],manager:any=new RunManager({} as any);
 manager.processDocumentsAttempt=async(_l:any,docs:string[],force:boolean,metrics?:string[],existing?:boolean)=>{calls.push({docs,force,metrics,existing});if(docs[0]==='d8'&&metrics?.[0]==='metric_12')throw Error('fixture batch failure');return {status:'ok',data:{documents:docs.map(document_id=>({document_id,state:'ready'}))}};};
 const live={controller:new AbortController(),route:{afterIngestion:'high'}};
 const result=await manager.processDocuments(live,Array.from({length:17},(_,i)=>'d'+i),true,Array.from({length:25},(_,i)=>'metric_'+i));
 assert.equal(calls.length,9);assert.ok(calls.every(c=>c.docs.length<=8&&c.metrics.length<=12));assert.equal(result.status,'partial');assert.equal(result.data.errors.length,1);assert.equal(result.data.batches.length,8);assert.equal(new Set(calls.flatMap(c=>c.docs)).size,17);assert.equal(new Set(calls.flatMap(c=>c.metrics)).size,25);assert.equal(calls.filter(c=>c.force).length,3);await manager.shutdown();
});

test('an uncertain write cannot be replayed before a new approval, and denial is not reprompted',async()=>{
 const {RunManager}=await import('../server/runs.js');const {getSettings}=await import('../server/config.js');
 const manager:any=new RunManager({putState:async()=>{}} as any);let writes=0;
 manager.artifactTool=async()=>{writes++;return {status:'ok',data:{id:'saved'},source_refs:[],warnings:[]};};
 const params={title:'Uncertain report'},name='save_research_report';
 const make=()=>({run:{id:randomUUID(),projectId:'fixture',conversationId:'chat',tools:[],uncertainWrites:[{name,args:params}]},chat:{id:'chat'},answer:{sources:[],artifacts:[]},controller:new AbortController(),events:[],clients:new Set(),auditQueue:Promise.resolve(),persistQueue:Promise.resolve()});
 const awaitApproval=async()=>{for(let i=0;i<100;i++){const request=manager.approvals.list()[0];if(request)return request;await delay(10);}throw Error('approval was not requested');};
 try{
  const denied=make(),first=manager.executeTool(denied,getSettings(),name,'denied',params),request=await awaitApproval();assert.equal(writes,0);
  manager.approvals.decide(request.id,request.digest,false);assert.equal((await first).details.isError,true);assert.equal(writes,0);
  assert.equal((await manager.executeTool(denied,getSettings(),name,'denied-again',params)).details.isError,true);assert.equal(manager.approvals.list().length,0);
  const accepted=make(),second=manager.executeTool(accepted,getSettings(),name,'approved',params),approval=await awaitApproval();assert.equal(writes,0);
  manager.approvals.decide(approval.id,approval.digest,true);await second;assert.equal(writes,1);assert.equal(accepted.run.uncertainWrites.length,0);
 }finally{await manager.shutdown();}
});

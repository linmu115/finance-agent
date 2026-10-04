import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,type ServerResponse} from 'node:http';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

test('persistent Pi sessions preserve their own tool history after manager recovery; cancelling one leaves the other running', {timeout:150000}, async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-pi-lifecycle-'));
 process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');
 const {RunManager}=await import('../server/runs.js');
 await loadSettings();
 const service=new FinanceService();await service.connect();
 const requests:any[]=[];
 let retryAttempts=0;
 const task=(content:any)=>(Array.isArray(content)?content.map(block=>block.text||'').join('\n'):String(content||'')).split('\n用户任务：\n').at(-1)!;
 const held=new Map<string,{res:ServerResponse,respond:()=>void}>();
 const response=(res:ServerResponse,delta:any,finish='stop')=>{
  if(res.destroyed)return;
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const envelope={id:'mock',object:'chat.completion.chunk',created:1,model:'session-mock'};
  res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{role:'assistant',...delta},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:40,completion_tokens:8,total_tokens:48}})+'\n\n');
  res.end('data: [DONE]\n\n');
 };
 const mock=createServer(async(req,res)=>{
  if(req.url!=='/v1/chat/completions'){res.writeHead(404);res.end();return;}
  let raw='';for await(const chunk of req)raw+=chunk;
  const body=JSON.parse(raw),messages=body.messages,latestIndex=messages.findLastIndex((m:any)=>m.role==='user'),latest=task(messages[latestIndex]?.content);
  requests.push(body);
  if(latest==='retry-once'){
   retryAttempts++;
   if(retryAttempts===1){res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Temporary test service unavailability',type:'server_error',code:'temporary_unavailable'}}));return;}
   response(res,{content:'retry recovered'});return;
  }
  if(latest.startsWith('hold-')){held.set(latest,{res,respond:()=>response(res,{content:latest+' completed'})});return;}
  if(latest==='recall'){
   const seed=task(messages.find((m:any)=>m.role==='user'&&task(m.content).startsWith('seed-'))?.content);
   response(res,{content:'remembered '+seed});return;
  }
  const toolResult=messages.slice(latestIndex+1).find((m:any)=>m.role==='tool');
  if(toolResult){response(res,{content:'stored '+latest+' with '+JSON.parse(toolResult.content).data.value});return;}
  response(res,{tool_calls:[{index:0,id:'calc-'+requests.length,type:'function',function:{name:'calculate_financial_metrics',arguments:JSON.stringify({operation:'divide',inputs:{a:'21',b:'3'}})}}]},'tool_calls');
 });
 await new Promise<void>(resolve=>mock.listen(0,'127.0.0.1',resolve));
 let manager=new RunManager(service);
 const wait=async(id:string)=>{
  const deadline=Date.now()+30000;
  while(Date.now()<deadline){const state=await manager.getRun(id);if(['completed','failed','cancelled'].includes(state.status)&&!manager.activeFor(state.conversationId))return state;await delay(40);}
  throw new Error('mock Pi run timeout');
 };
 const awaitHeld=async(key:string)=>{const until=Date.now()+20000;while(!held.has(key)){if(Date.now()>until)throw new Error('mock request not received: '+key);await delay(40);}};
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'session-mock',apiKey:'mock-session-value',contextWindow:8192,maxTokens:512}});
  await service.call('create_project',{project_id:'lifecycle',name:'Lifecycle'});
  const chats=[0,1].map(()=>({id:randomUUID(),projectId:'lifecycle',title:'新对话',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()}));
  for(const chat of chats){await service.putState('lifecycle','conversations',chat.id,chat);manager.indexConversation(chat.id,'lifecycle');}
  const seeds=['seed-A-ruby-471','seed-B-slate-862'];
  const first=await Promise.all(chats.map((chat,i)=>manager.start(chat,seeds[i],[])));
  for(const run of await Promise.all(first.map(r=>wait(r.id))))assert.equal(run.status,'completed',run.error);
  for(const body of requests){const transcript=JSON.stringify(body.messages);assert.ok(!(transcript.includes(seeds[0])&&transcript.includes(seeds[1])),'separate session contexts were mixed');}
  for(const chat of chats){const saved=await readFile(path.join(dir,'workspaces/lifecycle',chat.id,'sessions/session.jsonl'),'utf8');assert.ok(saved.includes('calculate_financial_metrics'));assert.ok(saved.includes('toolResult'));}
  await manager.shutdown();manager=new RunManager(service);await manager.recover('lifecycle');
  const recovered=await Promise.all(chats.map(async chat=>manager.start(await manager.getConversation(chat.id),'recall',[])));
  for(const [i,run] of recovered.entries()){
   const state=await wait(run.id);assert.equal(state.status,'completed',state.error);
   const chat=await manager.getConversation(chats[i].id),answer=chat.messages.at(-1)?.content||'';
   assert.ok(answer.includes(seeds[i]),JSON.stringify({answer,request:requests.at(-1)?.messages.map((m:any)=>({role:m.role,content:m.content}))}));assert.ok(!answer.includes(seeds[1-i]));
  }
  const recalls=requests.filter(body=>task(body.messages.at(-1)?.content)==='recall');
  assert.equal(recalls.length,2);assert.ok(recalls.every(body=>body.messages.some((m:any)=>m.role==='tool')),'persisted tool results must be included after recovery');
  const a=await manager.start(await manager.getConversation(chats[0].id),'hold-A',[]);await awaitHeld('hold-A');
  const b=await manager.start(await manager.getConversation(chats[1].id),'hold-B',[]);await awaitHeld('hold-B');
  assert.equal((await manager.getRun(a.id)).status,'running');assert.equal((await manager.getRun(b.id)).status,'running');
  await manager.cancel(a.id);assert.equal((await manager.getRun(a.id)).status,'cancelled');
  assert.equal((await manager.getRun(b.id)).status,'running','cancel leaked into another Pi session');
  held.get('hold-B')!.respond();const surviving=await wait(b.id);assert.equal(surviving.status,'completed',surviving.error);
  const retry=await manager.start(await manager.getConversation(chats[0].id),'retry-once',[]);
  const recoveredAfterRetry=await wait(retry.id);
  assert.equal(recoveredAfterRetry.status,'completed',recoveredAfterRetry.error);
  assert.equal(recoveredAfterRetry.error,undefined,'successful model retry must clear the earlier transient failure');
  assert.equal((await manager.getConversation(chats[0].id)).messages.at(-1)?.content,'retry recovered');
  assert.equal(retryAttempts,2,'the mock must actually fail once before a successful request');
 }finally{
  for(const state of held.values())state.respond();
  await manager.shutdown();await service.close();await new Promise<void>(resolve=>{mock.close(()=>resolve());mock.closeAllConnections();});
 }
});

test('Pi extraction bridge binds credentials and cancellation to one run', {timeout:30000}, async()=>{
 const {PiModelBridge}=await import('../server/model-bridge.js');
 const bridge=new PiModelBridge(),a=new AbortController(),b=new AbortController();let calls=0;
 try{
  const first=await bridge.register('run-A',a.signal,async()=>{calls++;return {content:'{"run":"A"}',model:'mock',input:3,output:4};});
  const second=await bridge.register('run-B',b.signal,async()=>{calls++;return {content:'{"run":"B"}',model:'mock',input:5,output:6};});
  const send=(base:string,key?:string,extra:any={})=>fetch(base+'/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',...(key?{Authorization:'Bearer '+key}:{})},body:JSON.stringify({messages:[{role:'user',content:'table'}],...extra})});
  assert.equal((await send(first.base_url)).status,403);
  assert.equal((await send(first.base_url,second.api_key)).status,403);
  assert.equal(calls,0);
  assert.equal((await send(first.base_url,first.api_key,{tools:[]})).status,502);assert.equal(calls,0);
  const ok=await send(first.base_url,first.api_key);assert.equal(ok.status,200);assert.equal((await ok.json()).choices[0].message.content,'{"run":"A"}');
  for(const status of [401,402,422]){
   const failing=await bridge.register('provider-'+status,new AbortController().signal,async()=>{throw Object.assign(new Error('private provider details'),{status});});
   const denied=await send(failing.base_url,failing.api_key);assert.equal(denied.status,status,'permanent provider errors must not become retryable HTTP 502');
   const failure=await denied.json();assert.ok(!JSON.stringify(failure).includes('private provider details'));
   if(status===422)assert.equal(failure.error.message,'structured_output_incomplete','a truncated semantic response must not be retried as a network failure');
   bridge.unregister('provider-'+status);
  }
  a.abort();assert.equal((await send(first.base_url,first.api_key)).status,403);
  assert.equal((await send(second.base_url,second.api_key)).status,200);assert.equal(calls,2);
  bridge.unregister('run-B');assert.equal((await send(second.base_url,second.api_key)).status,403);
 }finally{await bridge.close();}
});

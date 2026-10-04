import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

test('terminal Pi status waits for the final answer write and persists conversation before completed run',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-terminal-order-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();const service=new FinanceService();await service.connect();const manager=new RunManager(service);
 const expected='persisted final answer';
 const mock=createServer(async(req,res)=>{
  for await(const _ of req){/* consume the mock request */}
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const envelope={id:'terminal-order',object:'chat.completion.chunk',created:1,model:'order-mock'};
  res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{role:'assistant',content:expected},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:10,completion_tokens:5,total_tokens:15}})+'\n\n');
  res.end('data: [DONE]\n\n');
 });
 await new Promise<void>(resolve=>mock.listen(0,'127.0.0.1',resolve));
 let releaseSave!:()=>void,signalBlocked!:()=>void;
 const gate=new Promise<void>(resolve=>releaseSave=resolve),blocked=new Promise<void>(resolve=>signalBlocked=resolve);
 const writes:string[]=[],put=service.putState.bind(service);let gatePassed=false;
 service.putState=async(project,kind,key,value)=>{
  const finalAnswer=kind==='conversations'&&value.messages?.some((m:any)=>m.role==='assistant'&&m.status==='completed'&&m.content===expected);
  if(finalAnswer&&!gatePassed){signalBlocked();await gate;gatePassed=true;}
  const saved=await put(project,kind,key,value);
  if(finalAnswer)writes.push('final-conversation');
  if(kind==='runs'&&value.status==='completed')writes.push('completed-run');
  return saved;
 };
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'order-mock',apiKey:'mock-order-value',contextWindow:8192,maxTokens:512}});
  await service.call('create_project',{project_id:'terminal-order',name:'Terminal order'});
  const chat={id:randomUUID(),projectId:'terminal-order',title:'新对话',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
  await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);
  const run=await manager.start(chat,'Return the fixture answer.',[]);
  await Promise.race([blocked,delay(20000).then(()=>{throw Error('The final answer write was never reached');})]);
  let returned=false;const reading=manager.getRun(run.id).then(value=>{returned=true;return value;});
  await delay(100);
  assert.equal(returned,false,'getRun must not expose terminal status before final answer persistence');
  const diskRun=await service.getState<any>(chat.projectId,'runs',run.id);
  assert.notEqual(diskRun.status,'completed','disk consumers must not see completed while the conversation write is blocked');
  releaseSave();const completed=await reading;assert.equal(completed.status,'completed');
  const savedChat=await manager.getConversation(chat.id);
  assert.equal(savedChat.messages.find(m=>m.runId===run.id)?.content,expected);
  assert.ok(writes.indexOf('final-conversation')>=0&&writes.indexOf('completed-run')>writes.indexOf('final-conversation'),JSON.stringify(writes));
  assert.equal(manager.activeFor(chat.id),undefined);
 }finally{
  releaseSave();await manager.shutdown();await service.close();await new Promise<void>(resolve=>{mock.close(()=>resolve());mock.closeAllConnections();});
 }
});

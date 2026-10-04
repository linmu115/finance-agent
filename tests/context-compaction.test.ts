import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,type ServerResponse} from 'node:http';
import {mkdtemp,readFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {resolveCompactionPolicy} from '../server/context-compaction.js';

test('working context threshold stays separate from the real model window and reserves answer room',()=>{
 const large=resolveCompactionPolicy(undefined,1048576,32768);
 assert.equal(large.targetTokens,96000);assert.equal(large.reserveTokens,952576);assert.equal(large.keepRecentTokens,24000);assert.equal(large.summaryMaxTokens,8192);
 const small=resolveCompactionPolicy(undefined,8192,512);
 assert.ok(small.targetTokens<=8192-512-512);assert.ok(small.keepRecentTokens<small.targetTokens);assert.equal(small.summaryMaxTokens,512);
 assert.throws(()=>resolveCompactionPolicy(undefined,4096,4096),/工作记忆/);
});

test('real Pi compaction uses the owning runtime budget, preserves references/history, survives recovery and isolates failure/cancellation',{timeout:150000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-context-compact-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 const {SessionManager}=await import('@earendil-works/pi-coding-agent');
 await loadSettings();const service=new FinanceService();await service.connect();let manager=new RunManager(service);
 const requests:any[]=[],held=new Map<string,ServerResponse>();
 const text=(value:any)=>typeof value==='string'?value:Array.isArray(value)?value.map(x=>x.text||'').join('\n'):'';
 const reply=(res:ServerResponse,content:string,finish='stop')=>{
  if(res.destroyed)return;res.writeHead(200,{'Content-Type':'text/event-stream'});
  const packet={id:'fixture',object:'chat.completion.chunk',created:1,model:'compaction-fixture'};
  res.write('data: '+JSON.stringify({...packet,choices:[{index:0,delta:{role:'assistant',content},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...packet,choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:1200,completion_tokens:120,total_tokens:1320}})+'\n\n');res.end('data: [DONE]\n\n');
 };
 const mock=createServer(async(req,res)=>{
  if(req.url!=='/v1/chat/completions'){res.writeHead(404);res.end();return;}
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);requests.push(body);
  const all=body.messages.map((m:any)=>text(m.content)).join('\n');
  const summary=body.messages.some((m:any)=>m.role==='system'&&text(m.content).includes('context summarization assistant'));
  if(summary){
   if(all.includes('HOLD_MEMORY')){held.set('HOLD_MEMORY',res);return;}
   if(all.includes('FAIL_MEMORY')){reply(res,'unfinished checkpoint','length');return;}
   const marker=all.includes('MEMORY_BETA')?'MEMORY_BETA':'MEMORY_ALPHA';
   reply(res,'## Goal\nContinue '+marker+' unfinished work.\n## Progress\nOld sources saved. Need to reread inputs before changing results.');return;
  }
  const pairs=new Set<string>();for(const message of body.messages){if(message.role==='assistant')for(const call of message.tool_calls||[])pairs.add(call.id);if(message.role==='tool'&&!pairs.has(message.tool_call_id)){reply(res,'orphan tool result');return;}}
  const marker=all.includes('MEMORY_BETA')?'MEMORY_BETA':all.includes('MEMORY_ALPHA')?'MEMORY_ALPHA':'NO_MEMORY';
  reply(res,JSON.stringify({memory:marker,document:all.includes('document-fixture'),revision:all.includes('revision-fixture')}));
 });
 await new Promise<void>(resolve=>mock.listen(0,'127.0.0.1',resolve));
 const wait=async(id:string)=>{const until=Date.now()+45000;while(Date.now()<until){const run=await manager.getRun(id);if(['completed','failed','cancelled'].includes(run.status)&&!manager.activeFor(run.conversationId))return run;await delay(30);}throw Error('compaction fixture timeout');};
 const budget=(profile:'financial'|'generic')=>({profile,budget_group_id:randomUUID(),budget:{max_model_calls:12,max_input_tokens:1000000,max_output_tokens:20000,max_total_tokens:1020000,max_wall_seconds:100}});
 const create=async(marker:string)=>{
  const chat={id:randomUUID(),projectId:'compaction-fixture',title:'新对话',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
  await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);
  const workspace=path.join(dir,'workspaces',chat.projectId,chat.id),folder=path.join(workspace,'sessions');await mkdir(folder,{recursive:true});
  const session=SessionManager.open(path.join(folder,'session.jsonl'),folder,workspace);
  for(let i=0;i<3;i++){
   session.appendMessage({role:'user',content:marker+' Read prior document '+i,timestamp:Date.now()});
   session.appendMessage({role:'assistant',content:[{type:'toolCall',id:'source-'+i,name:'get_source_page',arguments:{document_id:'document-fixture',page:i+1}}],api:'openai-completions',provider:'financial-provider',model:'compaction-fixture',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'toolUse',timestamp:Date.now()});
   session.appendMessage({role:'toolResult',toolCallId:'source-'+i,toolName:'get_source_page',content:[{type:'text',text:JSON.stringify({status:'ok',data:{document_id:'document-fixture',page:i+1,text:('ARCHIVE_ONLY_'+marker+' ').repeat(1700)},source_refs:[{source_id:'source-fixture',document_id:'document-fixture',page:i+1},{kind:'artifact',id:'artifact-fixture',revision_id:'revision-fixture'}]})}],isError:false,timestamp:Date.now()});
   session.appendMessage({role:'assistant',content:[{type:'text',text:marker+' completed original page read'}],api:'openai-completions',provider:'financial-provider',model:'compaction-fixture',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:Date.now()});
  }
  session.appendMessage({role:'user',content:marker+' Recent unfinished task. '+('recent evidence pointers ').repeat(300),timestamp:Date.now()});
  session.appendMessage({role:'assistant',content:[{type:'text',text:marker+' resume with original source references'}],api:'openai-completions',provider:'financial-provider',model:'compaction-fixture',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:Date.now()});
  const file=path.join(folder,'session.jsonl'),before=await readFile(file,'utf8');return {chat,file,before};
 };
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'compaction-fixture',apiKey:'fixture-only',contextWindow:64000,maxTokens:2048},runtime:{contextCompaction:{enabled:true,targetTokens:8192,keepRecentTokens:1024,summaryMaxTokens:1024}}});
  await service.call('create_project',{project_id:'compaction-fixture',name:'Compaction fixture'});
  const a=await create('MEMORY_ALPHA'),b=await create('MEMORY_BETA');
  const started=await Promise.all([manager.start(a.chat,'Continue the unfinished task',[],'Return a JSON object',budget('financial')),manager.start(b.chat,'Continue the unfinished task',[],'Return a JSON object',budget('generic'))]);
  for(const [index,run] of started.entries()){
   const state=await wait(run.id);assert.equal(state.status,'completed',state.error);
   const fixture=index?a:b; // Check each answer separately below; both histories must remain byte-for-byte prefixes.
   assert.ok((await readFile(fixture.file,'utf8')).startsWith(fixture.before));
   const entries=(await readFile(index?b.file:a.file,'utf8')).trim().split('\n').map(JSON.parse),checkpoints=entries.filter(x=>x.type==='compaction');assert.ok(checkpoints.length>0);
   assert.ok(checkpoints.at(-1).summary.includes('document-fixture'));assert.ok(checkpoints.at(-1).summary.includes('revision-fixture'));assert.ok(checkpoints.at(-1).summary.includes('source-fixture'));
   const events=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse),usage=events.filter(x=>x.type==='model_usage');
   assert.ok(usage.some(x=>x.data.phase==='compaction'));assert.ok(events.some(x=>x.type==='compaction_saved'));assert.equal(state.evaluation!.usage.model_calls,usage.length);assert.equal(state.evaluation!.usage.input_tokens,usage.length*1200);assert.equal(state.evaluation!.usage.output_tokens,usage.length*120);
   const answer=(await manager.getConversation(index?b.chat.id:a.chat.id)).messages.at(-1)!.content;assert.ok(answer.includes(index?'MEMORY_BETA':'MEMORY_ALPHA'));assert.ok(!answer.includes(index?'MEMORY_ALPHA':'MEMORY_BETA'));assert.ok(!answer.includes('orphan'));
  }
  const summaries=requests.filter(body=>body.messages.some((m:any)=>m.role==='system'&&text(m.content).includes('context summarization assistant')));
  assert.ok(summaries.length>=2);for(const body of summaries){assert.equal(body.response_format,undefined);assert.ok(body.max_tokens<=1024);assert.ok(!body.tools?.length);}
  const genericSummary=summaries.find(body=>JSON.stringify(body).includes('MEMORY_BETA'));assert.ok(genericSummary);assert.ok(!JSON.stringify(genericSummary).includes('估值时点'));
  const finals=requests.filter(body=>!body.messages.some((m:any)=>m.role==='system'&&text(m.content).includes('context summarization assistant')));assert.ok(finals.every(body=>body.response_format?.type==='json_object'));
  await manager.shutdown();manager=new RunManager(service);await manager.recover('compaction-fixture');
  const again=await manager.start(await manager.getConversation(a.chat.id),'Recall preserved memory',[],undefined,budget('financial'));assert.equal((await wait(again.id)).status,'completed');assert.ok((await manager.getConversation(a.chat.id)).messages.at(-1)!.content.includes('MEMORY_ALPHA'));
  const failure=await create('FAIL_MEMORY'),failed=await manager.start(failure.chat,'Continue',[],undefined,budget('financial'));assert.equal((await wait(failed.id)).status,'failed');assert.equal((await readFile(failure.file,'utf8')).trim().split('\n').map(JSON.parse).filter(x=>x.type==='compaction').length,0);
  const heldFixture=await create('HOLD_MEMORY'),cancelled=await manager.start(heldFixture.chat,'Continue',[],undefined,budget('financial'));
  const until=Date.now()+20000;while(!held.has('HOLD_MEMORY')){assert.ok(Date.now()<until);await delay(30);}
  const surviving=await manager.start(await manager.getConversation(b.chat.id),'Recall preserved memory',[],undefined,budget('generic'));assert.equal((await wait(surviving.id)).status,'completed');
  await manager.cancel(cancelled.id);assert.equal((await wait(cancelled.id)).status,'cancelled');assert.equal((await readFile(heldFixture.file,'utf8')).trim().split('\n').map(JSON.parse).filter(x=>x.type==='compaction').length,0);
 }finally{
  for(const res of held.values())reply(res,'cleanup');await manager.shutdown();await service.close();await new Promise<void>(resolve=>{mock.close(()=>resolve());mock.closeAllConnections();});
 }
});

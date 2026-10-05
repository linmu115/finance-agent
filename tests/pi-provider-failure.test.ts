import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,type ServerResponse} from 'node:http';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

test('permanent provider errors stop one Pi run immediately, preserve extraction evidence, and leave another session running',{timeout:120000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-provider-error-'));
 process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');
 const {RunManager}=await import('../server/runs.js');
 await loadSettings();
 const service=new FinanceService();await service.connect();
 const manager=new RunManager(service),held=new Map<string,ServerResponse>();
 const task=(content:any)=>(Array.isArray(content)?content.map(block=>block.text||'').join('\n'):String(content||'')).split('\n用户任务：\n').at(-1)!;
 const attempts=new Map<string,number>();let extractionRequests=0,documentId='';
 const secret='sk-TESTONLY123';
 const respond=(res:ServerResponse,delta:any,finish='stop')=>{
  if(res.destroyed)return;
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const envelope={id:'mock',object:'chat.completion.chunk',created:1,model:'permanent-error-mock'};
  res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{role:'assistant',...delta},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:10,completion_tokens:4,total_tokens:14}})+'\n\n');
  res.end('data: [DONE]\n\n');
 };
 const reject=(res:ServerResponse,status:number)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:(status===402?'Insufficient Balance':'Invalid API key')+' '+secret,type:'provider_error',code:'test_permanent_error'}}));};
 const mock=createServer(async(req,res)=>{
  if(req.url!=='/v1/chat/completions'){res.writeHead(404);res.end();return;}
  let raw='';for await(const chunk of req)raw+=chunk;
  const body=JSON.parse(raw);
  if(!body.tools?.length){extractionRequests++;reject(res,402);return;}
  const latest=task(body.messages.findLast((m:any)=>m.role==='user')?.content);
  attempts.set(latest,(attempts.get(latest)||0)+1);
  if(latest.startsWith('hold-')){held.set(latest,res);return;}
  if(latest==='main-402'||latest==='main-401'){reject(res,Number(latest.slice(-3)));return;}
  if(latest==='extract-402'){
   respond(res,{tool_calls:[{index:0,id:'ingest',type:'function',function:{name:'process_documents',arguments:JSON.stringify({document_ids:[documentId],review_metrics:['revenue']})}}]},'tool_calls');return;
  }
  respond(res,{content:'mock survived'});
 });
 await new Promise<void>(resolve=>mock.listen(0,'127.0.0.1',resolve));
 const wait=async(id:string)=>{
  const until=Date.now()+35000;
  while(Date.now()<until){const state=await manager.getRun(id);if(['completed','failed','cancelled'].includes(state.status)&&!manager.activeFor(state.conversationId))return state;await delay(40);}
  throw new Error('Permanent provider error did not terminate the owning Pi run');
 };
 const waitHeld=async(key:string)=>{const until=Date.now()+15000;while(!held.has(key)){assert.ok(Date.now()<until,'parallel session never reached model');await delay(40);}};
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'permanent-error-mock',apiKey:secret,contextWindow:8192,maxTokens:512}});
  await service.call('create_project',{project_id:'provider-failure',name:'Provider failure isolation'});
  const chats=[0,1].map(()=>({id:randomUUID(),projectId:'provider-failure',title:'新对话',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()}));
  for(const chat of chats){await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);}
  await mkdir(path.join(dir,'uploads'),{recursive:true});
  const file=path.join(dir,'uploads','provider-failure.csv');
  await writeFile(file,'测试公司2024年年度报告 合并利润表 单位：元\n项目,2024年度,2023年度\n营业收入,123,100\n','utf8');
  documentId=(await service.call('register_document',{project_id:chats[0].projectId,path:file,original_name:'provider-failure.csv'})).data.document_id;
  assert.ok(documentId);
  for(const scenario of ['main-402','main-401','extract-402']){
   const hold='hold-'+scenario,b=await manager.start(await manager.getConversation(chats[1].id),hold,[]);await waitHeld(hold);
   const a=await manager.start(await manager.getConversation(chats[0].id),scenario,scenario==='extract-402'?[documentId]:[]),failed=await wait(a.id);
   assert.equal(failed.status,'failed');
   assert.match(failed.error||'',scenario==='main-401'?/401|凭据/:/402|余额/);
   assert.ok(!failed.error?.includes(secret));
   assert.equal(attempts.get(scenario),1,'permanent failure must not start another main model request');
   assert.equal((await manager.getRun(b.id)).status,'running','permanent failure incorrectly stopped a different conversation');
   if(scenario==='extract-402'){
    assert.equal(extractionRequests,1,'one failed batch must not fan out into additional extraction requests');
    const auditText=await readFile(path.join(dir,'audit',a.id+'.jsonl'),'utf8');
    assert.ok(!auditText.includes(secret),'provider credential leaked through extraction error evidence');
    const events=auditText.trim().split('\n').map(line=>JSON.parse(line)),requests=events.filter(e=>e.type==='extraction_request'),results=events.filter(e=>e.type==='extraction_result');
    assert.equal(requests.length,1);assert.equal(results.length,1);
    assert.equal(results[0].data.requestId,requests[0].data.requestId);assert.equal(results[0].data.ownerRunId,a.id);
    assert.equal(results[0].data.stopReason,'error');assert.match(results[0].data.errorMessage,/402|Insufficient Balance/);
    const processing=events.find(e=>e.type==='processing_started');assert.ok(processing);
    let state;const until=Date.now()+10000;
    do{state=(await service.call('get_processing_status',{project_id:chats[0].projectId,processing_id:processing.data.processingId})).data;if(['cancelled','failed'].includes(state.state))break;await delay(100);}while(Date.now()<until);
    assert.ok(['cancelled','failed'].includes(state.state),'failed owner left background processing active');
    assert.equal(state.fact_count,0,'a failed extraction must not produce invented facts');
   }
   respond(held.get(hold)!,{content:'other session completed'});assert.equal((await wait(b.id)).status,'completed');
  }
 }finally{
  for(const res of held.values())respond(res,{content:'cleanup'});
  await manager.shutdown();await service.close();await new Promise<void>(resolve=>{mock.close(()=>resolve());mock.closeAllConnections();});
 }
});

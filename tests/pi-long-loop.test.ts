import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,type ServerResponse} from 'node:http';
import {mkdtemp,readFile,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

// Real Pi, application tools, Python service, session persistence and report
// store; only the upstream model and one source read are deterministic fixtures.
test('native Pi finishes long loops, compacts between steps, retries tools and never completes truncated text',{timeout:150000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-pi-long-loop-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings,publicSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');
 const {RunManager}=await import('../server/runs.js');
 const {artifactStore}=await import('../server/research-artifacts.js');
 await loadSettings();
 const service=new FinanceService();await service.connect();const manager=new RunManager(service);
 const originalCall=service.call.bind(service),evidence='EXACT_SOURCE_VALUE=123456.7800;2023;CNY;consolidated;annual-2024;'.repeat(220);
 let processingAttempts=0;
 service.call=async(name:string,args:any,signal?:AbortSignal):Promise<any>=>{
  if(name==='get_source_table')return {status:'ok',data:{document_id:'fixture-doc',page:1,table_id:'fixture-table',text:evidence},source_refs:[]};
  if(name==='record_attachment_read'&&args.document_id==='fixture-doc')return {status:'ok',data:{}};
  if(name==='begin_script_cleaning'){
   if(++processingAttempts===1)throw new Error('Temporary document worker unavailable; saved batches remain reusable');
   return {status:'ok',data:{processing_id:'fixture-processing',state:'completed',pending_tables:{'fixture-doc':[]}}};
  }
  if(name==='get_processing_status')return {status:'ok',data:{state:'completed',message:'Resumed saved batches',progress:100}};
  return originalCall(name,args,signal);
 };
 let mode='long',mainRequests=0,calculations=0,summaryRequests=0,reportSaved=false,compactedDuringLoop=false;
 const requestSizes:number[]=[];
 const reply=(res:ServerResponse,delta:any,finish='stop',promptTokens=100)=>{
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const packet={id:'fixture',object:'chat.completion.chunk',created:1,model:'long-loop-fixture'};
  res.write('data: '+JSON.stringify({...packet,choices:[{index:0,delta:{role:'assistant',...delta},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...packet,choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:promptTokens,completion_tokens:80,total_tokens:promptTokens+80}})+'\n\n');
  res.end('data: [DONE]\n\n');
 };
 const tool=(name:string,args:any,index=0)=>({index,id:randomUUID(),type:'function',function:{name,arguments:JSON.stringify(args)}});
 const report={title:'Long loop acceptance fixture',kind:'investment_memo',content:{company:'Fixture only',as_of:'2026-10-04',thesis:'Long-loop completion fixture, not investment advice',claims:[{id:'c1',type:'inference',text:'The runtime reached the report step',evidence:[]}],catalysts:[],risks:['Synthetic provider'],falsification_conditions:[{indicator:'artifact',condition:'missing',horizon:'this run',action:'fail acceptance'}],conclusion:'Saved after all requested tool calls'}};
 const mock=createServer(async(req,res)=>{
  try{
   let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw),serialized=JSON.stringify(body.messages);
   const isSummary=body.messages.some((m:any)=>m.role==='system'&&JSON.stringify(m.content).includes('context summarization assistant'));
   if(isSummary){summaryRequests++;compactedDuringLoop ||= mainRequests>0;reply(res,{content:'## Goal\nComplete the long loop and save its report.\n## Progress\nTool results already saved.\n## Next\nContinue remaining calculations, then save the report.'});return;}
   mainRequests++;requestSizes.push(serialized.length);
   const pairs=new Set<string>();
   for(const message of body.messages){
    if(message.role==='assistant')for(const call of message.tool_calls||[])pairs.add(call.id);
    if(message.role==='tool')assert.ok(pairs.has(message.tool_call_id),'orphan tool result after compaction');
   }
   if(mode==='truncated'){reply(res,{content:'Partial answer without its required conclusion'},'length');return;}
   if(mode==='process-retry'){
    if(processingAttempts<2){reply(res,{tool_calls:[tool('process_documents',{document_ids:['fixture-doc']})]},'tool_calls');return;}
    reply(res,{content:'Document task resumed in the same run'});return;
   }
   if(mainRequests===1){reply(res,{tool_calls:[tool('get_source_table',{document_id:'fixture-doc',table_id:'fixture-table'})]},'tool_calls');return;}
   if(mode==='long')assert.ok(serialized.includes(evidence),'old source was released before context pressure');
   if(calculations<135){
    const batch=Math.min(5,135-calculations);calculations+=batch;
    reply(res,{tool_calls:Array.from({length:batch},(_,i)=>tool('calculate_financial_metrics',{operation:'add',inputs:{a:String(calculations-batch+i),b:'1'}},i))},'tool_calls',mode==='pressure'&&mainRequests===5?20000:100);return;
   }
   if(!reportSaved){reportSaved=true;reply(res,{tool_calls:[tool('save_research_report',report)]},'tool_calls');return;}
   const lastTool=[...body.messages].reverse().find((m:any)=>m.role==='tool');
   assert.equal(JSON.parse(lastTool.content).status,'ok');
   reply(res,{content:'Report saved; complete'});
  }catch(error){res.destroy(error as Error);}
 });
 await new Promise<void>(resolve=>mock.listen(0,'127.0.0.1',resolve));
 const wait=async(id:string)=>{const until=Date.now()+90000;while(Date.now()<until){const run=await manager.getRun(id);if(['completed','failed','cancelled'].includes(run.status)&&!manager.activeFor(run.conversationId))return run;await delay(20);}throw Error('long-loop fixture timed out');};
 const start=async(label:string)=>{
  const chat={id:randomUUID(),projectId:'long-loop',title:label,messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
  await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);
  return manager.start(chat,label,[]);
 };
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'long-loop-fixture',apiKey:'fixture-only',contextWindow:1048576,maxTokens:2048},runtime:{maxToolCalls:1}});
  assert.equal((publicSettings().runtime as any).maxToolCalls,undefined,'old clients cannot restore the retired limit');
  // Verify migration of an old persisted setting, without touching user settings.
  const settingsFile=path.join(dir,'settings.json'),legacy=JSON.parse(await readFile(settingsFile,'utf8'));legacy.runtime.maxToolCalls=64;
  await writeFile(settingsFile,JSON.stringify(legacy));await loadSettings();assert.equal((publicSettings().runtime as any).maxToolCalls,undefined);
  await service.call('create_project',{project_id:'long-loop',name:'Long loop fixture'});
  for(const next of ['long','pressure']){
   mode=next;mainRequests=calculations=summaryRequests=0;reportSaved=compactedDuringLoop=false;
   if(mode==='pressure')await saveSettings({llm:{contextWindow:64000},runtime:{contextCompaction:{enabled:true,mode:'manual',targetTokens:12000,keepRecentTokens:2048,summaryMaxTokens:1024}}});
   const run=await start(next),result=await wait(run.id);assert.equal(result.status,'completed',result.error);
   assert.equal(result.tools.filter(t=>t.status==='started').length,137);
   assert.equal(result.tools.filter(t=>t.name==='save_research_report'&&t.status==='completed').length,1);
   assert.equal(result.tools.filter(t=>t.status==='failed').length,0);
   const audit=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
   const saved=audit.find(e=>e.type==='tool_result'&&e.data.name==='save_research_report').data.result.data;
   const artifact=await artifactStore.get('long-loop',saved.id,saved.revision_id);assert.equal(artifact.content.conclusion,report.content.conclusion);
   if(mode==='long')assert.equal(summaryRequests,0,'below-pressure context must not be compacted');
   else {assert.ok(summaryRequests>0);assert.ok(compactedDuringLoop);assert.ok(audit.some(e=>e.type==='compaction_saved'));}
  }
  mode='process-retry';const resumed=await wait((await start('retry same processing request')).id);
  assert.equal(resumed.status,'completed',resumed.error);assert.equal(processingAttempts,2);
  assert.deepEqual(resumed.tools.filter(t=>t.name==='process_documents').map(t=>t.status),['started','failed','started','completed']);
  mode='truncated';await saveSettings({runtime:{contextCompaction:{enabled:false,mode:'auto',targetTokens:96000,keepRecentTokens:24000,summaryMaxTokens:8192}}});
  const unfinished=await wait((await start('truncated provider response')).id);assert.equal(unfinished.status,'failed');assert.match(unfinished.error||'',/截断/);
 }finally{
  await manager.shutdown();await service.close();await new Promise<void>(resolve=>{mock.close(()=>resolve());mock.closeAllConnections();});
 }
});

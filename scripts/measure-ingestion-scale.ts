// Isolated real-model ingestion. No HTTP server, no production writes.
import {mkdir,copyFile,writeFile,appendFile,readFile} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {execFileSync} from 'node:child_process';

const args=process.argv.slice(2),arg=(k:string,f='')=>args.includes(k)?args[args.indexOf(k)+1]:f;
const output=path.resolve(arg('--output'));
if(!arg('--output'))throw Error('--output must name a new isolated directory');
process.env.FINANCE_DATA_DIR=path.join(output,'app-data');
await mkdir(process.env.FINANCE_DATA_DIR,{recursive:true});
if(arg('--settings'))await copyFile(path.resolve(arg('--settings')),path.join(process.env.FINANCE_DATA_DIR,'settings.json'));
const {loadSettings,saveSettings,getSettings}=await import('../server/config.js');
await loadSettings();
if(getSettings().llm.provider!=='cpa-local')throw Error('--settings must contain the CPA provider and its matching endpoint/credential; do not relabel another provider');
await saveSettings({llm:{model:'gpt-6-luna'},embedding:{enabled:false}});
if(arg('--rules'))execFileSync(path.resolve('.venv/Scripts/python.exe'),[path.resolve('scripts/seed-cleaning-rules.py'),path.resolve(arg('--rules')),process.env.FINANCE_DATA_DIR],{stdio:'inherit'});
const {FinanceService}=await import('../server/mcp.js');
const {RunManager}=await import('../server/runs.js');
const service=new FinanceService();await service.connect();
const manager:any=new RunManager(service);
manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
const sessionFor=manager.sessionFor.bind(manager);
const instrumented=new WeakSet();
manager.sessionFor=async(...values:any[])=>{
 const entry=await sessionFor(...values);
 if(!instrumented.has(entry.runtime)){
  instrumented.add(entry.runtime);const original=entry.runtime.streamSimple.bind(entry.runtime);
  entry.session.subscribe((event:any)=>{
   if(['agent_start','agent_end','agent_settled','turn_start','turn_end','message_end','auto_retry_start','auto_retry_end','auto_compaction_start','auto_compaction_end'].includes(event.type))
    void appendFile(path.join(output,'pi-events.jsonl'),JSON.stringify({at:new Date().toISOString(),type:event.type,role:event.message?.role,stopReason:event.message?.stopReason,error:event.errorMessage,content:event.type==='message_end'&&event.message?.role==='assistant'?event.message.content:undefined})+'\n');
  });
  entry.runtime.streamSimple=(model:any,context:any,options:any={})=>original(model,context,{...options,onPayload:async(payload:any,m:any)=>{
   const prepared=await options.onPayload?.(payload,m)??payload;
   await appendFile(path.join(output,'payloads.jsonl'),JSON.stringify({at:new Date().toISOString(),payload:prepared})+'\n');
   return prepared;
  }});
 }
 return entry;
};
const projectId='n3-'+arg('--label','baseline'),source=path.resolve(arg('--pdf','samples/native-pdf/Ruihe_Data_2025_Interim_57p.pdf'));
const iso=()=>new Date().toISOString();
try{
 await service.call('create_project',{project_id:projectId,name:'N3 isolated ingestion '+arg('--label','baseline')});
 const upload=path.join(process.env.FINANCE_DATA_DIR,'uploads',path.basename(source));await copyFile(source,upload);
 const document=(await service.call('register_document',{project_id:projectId,path:upload,original_name:path.basename(source)})).data;
 const chat={id:randomUUID(),projectId,title:'N3 full ingestion',messages:[],createdAt:iso(),updatedAt:iso()};
 await service.putState(projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,projectId);
 const started=Date.now();
 const run=await manager.start(chat,'请将附件完整入库，覆盖全部财务主表、附注及其他含财务数字的表，保留原文来源与待核验疑点。直接完成全部工作，完成后简要报告覆盖和事实数。',[document.document_id]);
 await writeFile(path.join(output,'run.json'),JSON.stringify({runId:run.id,projectId,documentId:document.document_id,source,startedAt:iso(),expenseCategory:'资料准备研发',model:'cpa-local/gpt-6-luna',reasoning:'low cleaning; app routing unchanged',manualContinuations:0,seedRules:arg('--rules')||null},null,2));
 let last='';
 while(manager.activeFor(chat.id)){
  const current=await manager.getRun(run.id),key=JSON.stringify([current.status,current.tools.length,current.stage]);
  if(key!==last){console.log(iso(),key);last=key;}
  await delay(3000);
 }
 const final=await manager.getRun(run.id),saved=await manager.getConversation(chat.id);
 const checkpoint=await service.call('get_processing_checkpoint',{project_id:projectId,document_id:document.document_id});
 const result={run:final,durationMs:Date.now()-started,checkpoint,document:(await service.call('get_document',{project_id:projectId,document_id:document.document_id})).data,answer:saved.messages.at(-1)};
 await writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({status:final.status,error:final.error,durationMs:result.durationMs,usage:final.usage,checkpoint:checkpoint.data}));
}finally{await manager.shutdown();await service.close();}

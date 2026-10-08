// Test runner only: production source and native Pi loop remain frozen.
import {readFile,writeFile,appendFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
const [caseId,profile]=process.argv.slice(2);
if(!/^Q[1-6]$/.test(caseId)||!['financial','prepared'].includes(profile))throw Error('Unknown preflight case/profile');
const base=path.resolve('tmp/adoption'),out=path.join(base,'runs',caseId+'-'+profile);
const manifest=JSON.parse(await readFile(path.join(base,'manifest.json'),'utf8')),task=manifest.cases.find((x:any)=>x.id===caseId);
process.env.FINANCE_DATA_DIR=path.join(out,'app-data');
process.env.FINANCE_PYTHON='D:\\AI\\财报agent\\.venv\\Scripts\\python.exe';
const {loadSettings,getSettings}=await import('../../server/config.js');
await loadSettings();
const settings=getSettings();
if(settings.llm.provider!=='cpa-local'||settings.llm.model!=='gpt-6-luna')throw Error('Frozen preflight must use CPA gpt-6-luna');
const {FinanceService}=await import('../../server/mcp.js');
const {RunManager}=await import('../../server/runs.js');
const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
// Same no-listener adapter as N3's measure-ingestion-scale.ts. These are
// analysis-only sessions. Native session/router/tool schemas are unchanged.
manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
const sessionFor=manager.sessionFor.bind(manager);let captured=false;
manager.sessionFor=async(...args:any[])=>{
 const entry=await sessionFor(...args);
 if(!captured){
  captured=true;
  entry.session.subscribe((event:any)=>{
   if(['message_end','auto_retry_start','auto_retry_end','auto_compaction_start','auto_compaction_end'].includes(event.type))
    void appendFile(path.join(out,'native-events.jsonl'),JSON.stringify({at:new Date().toISOString(),type:event.type,message:event.type==='message_end'?event.message:undefined,error:event.errorMessage})+'\n');
  });
  const original=entry.runtime.streamSimple.bind(entry.runtime);
  entry.runtime.streamSimple=(model:any,context:any,options:any={})=>original(model,context,{...options,onPayload:async(payload:any,m:any)=>{
   const final=await options.onPayload?.(payload,m)??payload;
   await appendFile(path.join(out,'payloads.jsonl'),JSON.stringify({at:new Date().toISOString(),payload:final})+'\n');return final;
  }});
  await writeFile(path.join(out,'model.json'),JSON.stringify({provider:entry.model.provider,id:entry.model.id,api:entry.model.api,reasoning:entry.model.reasoning,contextWindow:entry.model.contextWindow,maxTokens:settings.llm.maxTokens,runtime:settings.runtime,expenseCategory:'研发预检'},null,2));
 }
 return entry;
};
try{
 const iso=()=>new Date().toISOString(),chat={id:randomUUID(),projectId:task.project,title:caseId+' '+profile,messages:[],createdAt:iso(),updatedAt:iso()};
 await service.putState(task.project,'conversations',chat.id,chat);manager.indexConversation(chat.id,task.project);
 // EvaluationOptions is the product's public selector for prepared. Large
 // equal limits are bookkeeping, not a truncation strategy for these 12 runs.
 const evaluation={profile,budget_group_id:'adoption-'+caseId+'-'+profile,budget:{max_model_calls:1_000_000,max_input_tokens:1_000_000_000,max_output_tokens:1_000_000_000,max_total_tokens:2_000_000_000,max_wall_seconds:86400}};
 const started=Date.now(),question=task.prompt+'\n'+manifest.common_suffix;
 const run=await manager.start(chat,question,[],undefined,evaluation);
 await writeFile(path.join(out,'start.json'),JSON.stringify({caseId,profile,question,runId:run.id,conversationId:chat.id,documentId:task.document,projectId:task.project,startedAt:iso(),code:manifest.code_commit,expenseCategory:'研发预检'},null,2));
 let last='';
 while(manager.activeFor(chat.id)){
  const r=await manager.getRun(run.id),status=JSON.stringify({status:r.status,stage:r.stage,tools:r.tools.length,usage:r.usage});
  if(last!==status){console.log(caseId,profile,status);last=status;}
  await delay(3000);
 }
 const final=await manager.getRun(run.id),conversation=await manager.getConversation(chat.id);
 await writeFile(path.join(out,'result.json'),JSON.stringify({run:final,conversation,durationMs:Date.now()-started,expenseCategory:'研发预检'},null,2));
 await writeFile(path.join(out,'answer.md'),conversation.messages.at(-1)?.content||'');
 console.log('COMPLETE',caseId,profile,JSON.stringify({status:final.status,error:final.error,usage:final.usage}));
}finally{await manager.shutdown();await service.close();}

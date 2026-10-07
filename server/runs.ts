import {emptyUsage,addUsage as tallyUsage,aggregateAudit} from './usage.js';
import {artifactMediaType} from './artifact-media.js';
import {registerNumericTables,referenceInventory} from './numeric-tables.js';
import {answerBindingExtension} from './answer-binding.js';
import {repairInterruptedTools,operationKey,sideEffectTool} from './session-recovery.js';
import {configuredModel,modelCatalogRevision,jsonOutputPayload} from './model-runtime.js';
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from '@earendil-works/pi-coding-agent';
import { mkdir,readFile,copyFile } from 'node:fs/promises';
import { AuditLog } from './audit-log.js';
import { createHash,randomUUID } from 'node:crypto';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { AsyncLocalStorage } from 'node:async_hooks';
import { PiModelBridge } from './model-bridge.js';
import type { Response,Request } from 'express';
import { DATA,getSettings,redactError,requireModel } from './config.js';
import { FinanceService, safeDataPath } from './mcp.js';
import { RESEARCH_TOOLS, researchStore, researchEnvelope, downloadWithReader } from './research.js';
import { modelContext, projectToolHistory } from './model-context.js';
import {ingestionRemaining,madeIngestionProgress} from './ingestion-continuation.js';
import { FINANCE_TASK_GUIDANCE, ANSWER_FORMAT_GUIDANCE, SHARED_TASK_GUIDANCE, FINANCE_WORKSPACE_GUIDANCE, FINANCE_EXTENSION_GUIDANCE } from './financial-guidance.js';
import {createContextCompactionExtension,focusCompactionContext,resolveCompactionPolicy} from './context-compaction.js';
import { ResearchWorkspace, ARTIFACT_TOOLS, reportSchema } from './research-artifacts.js';
import { latestNamedArtifacts } from './artifact-versions.js';
import {EvaluationBudgets,normalizeEvaluation,type EvaluationBudget,type EvaluationOptions,type BudgetSnapshot,type BudgetTicket} from './evaluation-budget.js';
import type { Conversation,Run,Message,Source,Artifact,Settings } from './types.js';
import { ApprovalQueue, ADMIN_TOOL } from './approvals.js';
import { projectResources, RESOURCE_TOOL } from './project-resources.js';
import { bindAnnotations, annotationContext } from './annotations.js';
import {routingScope,ROUTER_PROMPT,parseTaskRoute,initialEffort,fallbackRoute,extractionEffort,extractionReasoning,type ExtractionEffort,type TaskRoute,type Effort} from './reasoning-routing.js';

const TOOL_ALLOWLIST = new Set(['run_cleaning_script','get_cleaning_result','commit_cleaning_result','prepare_document_sources','process_documents','get_processing_checkpoint','get_data_catalog','get_document_index','query_financial_data','get_normalization_details','list_documents','get_document','search_evidence','get_source_page','get_source_table','get_financial_metrics','calculate_financial_metrics','run_analysis','get_analysis_status','get_artifact']);
for(const name of ['inspect_document_routing','set_document_profile','save_research_claims','get_research_ingestion_status','query_research_records'])TOOL_ALLOWLIST.add(name);
TOOL_ALLOWLIST.add('get_cleaning_batch');
for(const tool of RESEARCH_TOOLS)TOOL_ALLOWLIST.add(tool.name);
for(const tool of ARTIFACT_TOOLS)TOOL_ALLOWLIST.add(tool.name);
TOOL_ALLOWLIST.add('get_research_model_schema');
TOOL_ALLOWLIST.add('financial_workpaper');
TOOL_ALLOWLIST.add(ADMIN_TOOL.name);TOOL_ALLOWLIST.add(RESOURCE_TOOL.name);
export const GENERIC_TOOL_ALLOWLIST=new Set(['prepare_document_sources','list_documents','get_document','get_document_index','get_source_page','get_source_table','search_evidence','run_analysis','get_analysis_status','get_artifact']);
const GENERIC_PROMPT="你是通用文档分析助手。附件先 prepare_document_sources，按需读取原文页表；本配置 /input/facts.json 为空。自由计算和制图用 run_analysis，状态和产物用其后续工具读取。report、save_table 和答案绑定是共享能力，可自由使用 Python/Matplotlib。";
const PREPARED_PROMPT="你是通用文档分析助手。附件先 prepare_document_sources；已准备资料可用目录和结构化查询，也可读原文。自由计算和制图用 run_analysis，运行状态与产物由其后续工具读取。report、save_table 和答案绑定是两组共享能力；可自由使用标准 Python/Matplotlib。";
const genericProfile=(profile?:string)=>profile==='generic'||profile==='prepared';
const evaluationPrompt=(profile?:string)=>(profile==='prepared'?PREPARED_PROMPT:GENERIC_PROMPT)+'\n\n'+SHARED_TASK_GUIDANCE+'\n\n'+ANSWER_FORMAT_GUIDANCE;
export const PREPARED_TOOL_ALLOWLIST=new Set([...GENERIC_TOOL_ALLOWLIST,'get_data_catalog','query_financial_data','query_research_records']);
const toolAllowlist=(profile?:string)=>profile==='prepared'?PREPARED_TOOL_ALLOWLIST:profile==='generic'?GENERIC_TOOL_ALLOWLIST:TOOL_ALLOWLIST;
const FINANCE_PROMPT=['你是金融研究助手。',SHARED_TASK_GUIDANCE,FINANCE_TASK_GUIDANCE,FINANCE_WORKSPACE_GUIDANCE,ANSWER_FORMAT_GUIDANCE].join('\n\n');
export const PROMPT_HASH=createHash('sha256').update(FINANCE_PROMPT).digest('hex');
interface EventItem { seq:number; type:string; data:any }
interface LiveRun { numericTables?:Record<string,any>; bindingError?:Error; bindingRepairMessage?:string; usagePhase?:string; scriptProcessingIds?:Set<string>; accepting:boolean; inputQueue:Promise<void>; nativeQueued:Set<string>; resuming?:boolean; restarting?:boolean; run:Run; events:EventItem[]; clients:Set<Response>; controller:AbortController; promise?:Promise<void>; session?:any; persistQueue:Promise<any>; chat:Conversation; answer:Message; analysisIds:Set<string>; processingIds:Set<string>; extractionRuntime?:Record<string,unknown>; contract?:string; closed:boolean; budget?:EvaluationBudget; detachBudget?:()=>void; modelPending:Set<Promise<unknown>>; researchReads:Map<string,Promise<any>>; route?:TaskRoute; effort?:Effort }
interface SessionEntry { session:any; runtime:ModelRuntime; model:any; active?:LiveRun; settings:Settings; signature:string }
const extractionScope=new AsyncLocalStorage<{runId:string;requestId:string;effort:ExtractionEffort}>();
const EXTRACTION_MAX_TOKENS=32768;
export function permanentModelError(message:string):Error|undefined {
 if(/Insufficient Balance|\b402\b/i.test(message))return Object.assign(new Error('DeepSeek API 余额不足（HTTP 402）。已停止本会话，已完成的清洗批次保留；补充余额后可在原会话继续。'),{status:402,code:'provider_balance_insufficient'});
 if(/\b401\b|invalid api key|authentication failed/i.test(message))return Object.assign(new Error('模型 API 凭据无效（HTTP 401）。请在 API 配置中更新凭据后继续，已完成的数据保留。'),{status:401,code:'provider_authentication_failed'});
 return undefined;
}
const iso=()=>new Date().toISOString();
const source=(s:any):Source=>({documentId:s.document_id||'',page:s.page,tableId:s.table_id,cell:s.cell,sheet:s.sheet,quote:s.text||s.quote,sourceId:s.source_id || (s.document_id&&s.page?s.document_id+':p'+s.page:undefined),url:s.url,title:s.title,snapshotUrl:s.snapshot_url});
export async function registerResearchPdf(service:FinanceService,projectId:string,filename:string,originalName:string,signal?:AbortSignal){
 if(!/^[A-Za-z0-9_-]{1,100}$/.test(projectId))throw new Error('invalid_project_id');
 const folder=path.join(DATA,'uploads',projectId);await mkdir(folder,{recursive:true});
 const staged=path.join(folder,randomUUID()+'.pdf');await copyFile(filename,staged);
 const registered=await service.call('register_document',{project_id:projectId,path:staged,original_name:originalName},signal);
 return registered.data.document_id||registered.data.id;
}
export class RunManager {
 readonly approvals=new ApprovalQueue();
 private resourceSnapshots=new Map<string,Awaited<ReturnType<typeof projectResources.load>>>();
 private deniedOperations=new Map<string,Set<string>>();
 private live=new Map<string,LiveRun>();
 private conversations=new Map<string,string>();
 private knownRuns=new Map<string,string>();
 private sessions=new Map<string,SessionEntry>();
 private bridge=new PiModelBridge();
 private auditLogs=new Map<string,AuditLog>();
 private settledUsage=new Map<string,{rows:any[];config:any}>();
 private evaluationBudgets=new EvaluationBudgets();
 private budgetWrites=new Map<string,Promise<unknown>>();
 constructor(private service:FinanceService){}
 indexConversation(id:string,projectId:string){this.conversations.set(id,projectId);}
 activeFor(id:string){return [...this.live.values()].find(l=>l.run.conversationId===id&&!l.closed)?.run.id;}
 activeInProject(id:string){return [...this.live.values()].some(l=>l.run.projectId===id&&!l.closed);}
 // The model request and usage rows of a run's audit file, with its pricing config. A finished run's
 // file no longer changes, so it is read and parsed once instead of on every conversation load.
 private async usageRows(runId:string){
  const settled=this.settledUsage.get(runId);if(settled)return settled;
  let audit:string;
  try{audit=await readFile(path.join(DATA,'audit',runId+'.jsonl'),'utf8');}
  catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT')return;throw error;}
  // A crash can leave an unfinished final JSONL line. Earlier complete rows
  // remain the accounting source; the missing settlement stays unknown.
  const lines=audit.split('\n'),rows=lines.flatMap((line,index)=>{if(!line)return [];try{return [JSON.parse(line)];}catch(error){if(index===lines.length-1)return [];throw error;}});
  const usage={rows:rows.filter(r=>r.type==='model_request'||r.type==='model_usage'),config:rows.find(r=>r.type==='run_config')?.data};
  const live=this.live.get(runId);
  if(!live||live.closed)this.settledUsage.set(runId,usage);
  return usage;
 }
 private async reconcileUsage(runId:string,messages:Message[]=[]){
  const usage=await this.usageRows(runId);
  if(!usage?.rows.length)return;
  const {rows,config}=usage;
  const answers=messages.filter(m=>m.role==='assistant'&&m.runId===runId);
  for(const answer of answers){
   const ids=new Set(rows.filter(r=>r.data?.messageId===answer.id).map(r=>r.data.requestId).filter(Boolean));
   if(answers.length===1||ids.size)answer.usage=aggregateAudit(answers.length===1?rows:rows.filter(r=>r.data?.messageId===answer.id||ids.has(r.data?.requestId)),config);
  }
  return aggregateAudit(rows,config);
 }
 async getConversation(id:string):Promise<Conversation>{
   const projectId=this.conversations.get(id);if(!projectId)throw Object.assign(new Error('对话不存在'),{status:404});
   const chat=await this.service.getState<Conversation>(projectId,'conversations',id);if(!chat)throw Object.assign(new Error('对话不存在'),{status:404});
    const finished=new Set(chat.messages.filter(m=>m.role==='assistant'&&m.runId&&['completed','failed','cancelled'].includes(m.status||'')).map(m=>m.runId!));
    for(const runId of finished)await this.reconcileUsage(runId,chat.messages);
    return chat;
 }
 async getRun(id:string):Promise<Run>{
   const live=this.live.get(id);
   if(live){
    if(!live.closed&&['completed','failed','cancelled'].includes(live.run.status))await live.promise;
    if(live.budget)live.run.evaluation=live.budget.snapshot();
    return live.run;
   }
   const p=this.knownRuns.get(id);if(!p)throw Object.assign(new Error('任务不存在'),{status:404});
   const run=await this.service.getState<Run>(p,'runs',id);if(!run)throw Object.assign(new Error('任务不存在'),{status:404});
   run.usage=await this.reconcileUsage(id)??run.usage;return run;
 }
 async recover(projectId:string){
   for(const chat of await this.service.listState<Conversation>(projectId,'conversations'))this.indexConversation(chat.id,projectId);
   for(const run of await this.service.listState<Run>(projectId,'runs')){
    this.knownRuns.set(run.id,projectId);
    if(!['queued','running'].includes(run.status)||this.activeFor(run.conversationId))continue;
    const chat=await this.getConversation(run.conversationId),answer=chat.messages.find(m=>m.id===run.messageId);
    const original=run.request?chat.messages.find(m=>m.id===run.request!.userMessageId):chat.messages.slice(0,chat.messages.findIndex(m=>m.id===run.messageId)).findLast(m=>m.role==='user');
    if(!answer||!original){run.status='failed';run.error='恢复记录缺少原始任务；历史资料保留。';await this.service.putState(projectId,'runs',run.id,run);continue;}
    run.request??={userMessageId:original.id,documentIds:original.attachments||[]};
    run.status='queued';run.stage='恢复会话进度';delete run.error;delete run.finishedAt;answer.status='running';
    const live:LiveRun={run,chat,answer,resuming:true,accepting:true,inputQueue:Promise.resolve(),nativeQueued:new Set(),events:[],clients:new Set(),controller:new AbortController(),persistQueue:Promise.resolve(),analysisIds:new Set(),processingIds:new Set(),closed:false,modelPending:new Set(),researchReads:new Map(),contract:run.request.contract};
    // Preserve SSE sequence IDs across server restarts.
    try{live.events=(await readFile(path.join(DATA,'audit',run.id+'.jsonl'),'utf8')).split('\n').filter(Boolean).flatMap(line=>{try{const row=JSON.parse(line);return row.type==='event'?[row.data]:[];}catch{return [];}});}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
    if(run.request.evaluation){const prior=await this.service.getState<BudgetSnapshot>(projectId,'evaluation_budgets',run.request.evaluation.budget_group_id);live.budget=this.evaluationBudgets.acquire(projectId,run.request.evaluation,prior||undefined);live.detachBudget=live.budget.attach(run.id,live.controller);}
    this.live.set(run.id,live);await this.persist(live);this.emit(live,'status',{stage:run.stage,status:'queued'});
    this.launch(live,getSettings(),run.request.documentIds,run.request.contract);
   }
 }
 private promptFor(l:LiveRun,message:Message){
  const docs=message.attachments||[],generic=genericProfile(l.chat.evaluationProfile);
  return '应用消息标识：'+message.id+'\n当前项目：'+l.run.projectId+'\n本次附件 document_id：'+JSON.stringify(docs)+(docs.length?(generic?'\n附件已保存。用prepare_document_sources取得原文，然后完成用户任务。':'\n附件已保存。默认调用 process_documents 处理财务主表及附注表并入库；之后回答用户任务。'):'')+'\n用户任务：\n'+annotationContext(message)+message.content+(l.contract?'\n当前任务输出契约：\n'+l.contract:'');
 }
 private async queueInputs(l:LiveRun){
  if(!l.session)return;
  for(const input of l.run.queuedInputs||[]){
   if(input.delivered||l.nativeQueued.has(input.messageId))continue;
   const message=l.chat.messages.find(m=>m.id===input.messageId)!;
   await l.session[input.mode](this.promptFor(l,message));l.nativeQueued.add(input.messageId);
  }
 }
 private async appendInput(l:LiveRun,content:string,documentIds:string[],annotationInput:unknown,mode:'steer'|'followUp'){
  const message:Message={id:randomUUID(),role:'user',content:content.trim()||'请结合附件及引用继续。',attachments:documentIds,annotations:bindAnnotations(l.chat,annotationInput),createdAt:iso(),status:'queued'};
  l.chat.messages.push(message);(l.run.queuedInputs??=[]).push({messageId:message.id,mode});l.chat.updatedAt=iso();
  l.inputQueue=l.inputQueue.then(async()=>{await this.persist(l);await this.queueInputs(l);this.emit(l,'input',{message,mode});});
  await l.inputQueue;return {...l.run,userMessageId:message.id,inputStatus:message.status};
 }
 private auditLog(runId:string){
  let log=this.auditLogs.get(runId);
  if(!log){log=new AuditLog(path.join(DATA,'audit',runId+'.jsonl'));this.auditLogs.set(runId,log);}
  return log;
 }
 private audit(l:LiveRun,type:string,data:any) {
  const entry={at:iso(),runId:l.run.id,projectId:l.run.projectId,type,data};
  return this.auditLog(l.run.id).append(JSON.stringify(entry)+'\n');
 }
 // Releases the run's audit handle. A record that could not be written is reported, never dropped silently.
 private async closeAudit(l:LiveRun){
  // The closed log stays registered, so a record arriving after the run ended opens the file only for itself.
  try{await this.auditLog(l.run.id).close();}
  catch(error){l.run.auditError=redactError(error);process.stderr.write('[audit] '+l.run.id+' is incomplete: '+l.run.auditError+'\n');}
 }
 private emit(l:LiveRun,type:string,data:any){
  const e:EventItem={seq:l.events.length+1,type,data};l.events.push(e);
  for(const res of l.clients)if(!res.destroyed)res.write('id: '+e.seq+'\nevent: '+type+'\ndata: '+JSON.stringify(data)+'\n\n');
  void this.audit(l,'event',e).catch(error=>{l.controller.abort(new Error('无法写入审计记录：'+redactError(error)));});
 }
 async subscribe(id:string,req:Request,res:Response){
  const run=await this.getRun(id),l=this.live.get(id);
  res.setHeader('Content-Type','text/event-stream');res.setHeader('Cache-Control','no-cache');res.setHeader('Connection','keep-alive');res.flushHeaders();
  let events=l?.events;
  if(!events){
   try{events=(await readFile(path.join(DATA,'audit',id+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(line=>JSON.parse(line)).filter(x=>x.type==='event').map(x=>x.data);}catch{events=[];}
  }
  const after=Number(req.headers['last-event-id'] || req.query.after || 0);
  for(const event of events)if(event.seq>after)res.write('id: '+event.seq+'\nevent: '+event.type+'\ndata: '+JSON.stringify(event.data)+'\n\n');
  if(!l || l.closed){res.write('event: done\ndata: '+JSON.stringify({status:run.status})+'\n\n');res.end();return;}
  l.clients.add(res);const interval=setInterval(()=>res.write(': heartbeat\n\n'),15000);
  req.on('close',()=>{clearInterval(interval);l.clients.delete(res);});
 }
 async start(chat:Conversation,content:string,documentIds:string[],contract?:string,evaluation?:EvaluationOptions,annotationInput?:unknown,mode:'steer'|'followUp'='steer'):Promise<Run>{
  const active=[...this.live.values()].find(l=>l.run.conversationId===chat.id&&!l.closed);
  if(active){
   if(active.accepting)return this.appendInput(active,content,documentIds,annotationInput,mode);
   await active.promise;return this.start(await this.getConversation(chat.id),content,documentIds,contract,evaluation,annotationInput,mode);
  }
  const annotations=bindAnnotations(chat,annotationInput);
  evaluation=normalizeEvaluation(evaluation);
  const profile=evaluation?.profile||'financial';
  if(chat.evaluationProfile&&chat.evaluationProfile!==profile||genericProfile(profile)&&chat.messages.length&&!chat.evaluationProfile)throw Object.assign(new Error('evaluation_conversation_profile_conflict'),{status:409});
  let budget:EvaluationBudget|undefined;
  if(evaluation){const prior=await this.service.getState<BudgetSnapshot>(chat.projectId,'evaluation_budgets',evaluation.budget_group_id);budget=this.evaluationBudgets.acquire(chat.projectId,evaluation,prior||undefined);}
  chat.evaluationProfile=profile;
  const settings=requireModel(),now=iso(),runId=randomUUID(),messageId=randomUUID();
  const fingerprint:any=structuredClone(settings);for(const section of ['llm','embedding','ocr','search'])if(fingerprint[section])delete fingerprint[section].apiKey;
  const run:Run={id:runId,conversationId:chat.id,projectId:chat.projectId,status:'queued',stage:'准备任务',createdAt:now,tools:[],usage:emptyUsage(),model:settings.llm.model,configHash:createHash('sha256').update(JSON.stringify(fingerprint)+PROMPT_HASH).digest('hex'),messageId};
  const answer:Message={id:messageId,role:'assistant',content:'',createdAt:now,status:'running',sources:[],artifacts:[],tools:[],usage:emptyUsage(),runId};
  chat.messages.push({id:randomUUID(),role:'user',content:content.trim() || (annotations.length?'请结合这些引用及补充说明回答。':'请解析并概述这些附件。'),createdAt:now,attachments:documentIds,...(annotations.length?{annotations}:{})},answer);
  if(chat.title==='新对话')chat.title=(content.trim() || '附件分析').slice(0,28);chat.updatedAt=now;
  run.configHash=createHash('sha256').update(run.configHash+profile+(genericProfile(profile)?evaluationPrompt(profile):'')).digest('hex');
  run.request={userMessageId:chat.messages[chat.messages.length-2].id,documentIds,contract,evaluation};
  const live:LiveRun={accepting:true,inputQueue:Promise.resolve(),nativeQueued:new Set(),run,events:[],clients:new Set(),controller:new AbortController(),persistQueue:Promise.resolve(),chat,answer,analysisIds:new Set(),processingIds:new Set(),contract,closed:false,budget,modelPending:new Set(),researchReads:new Map()};
  if(budget){live.detachBudget=budget.attach(run.id,live.controller);run.evaluation=budget.snapshot();await this.saveBudget(live,'attached');}
  this.live.set(runId,live);this.knownRuns.set(runId,chat.projectId);
  await this.persist(live);
  this.emit(live,'status',{stage:'准备任务',status:'queued'});
  this.launch(live,settings,documentIds,contract);
  return {...run,userMessageId:run.request.userMessageId};
 }
 private async persist(l:LiveRun){
  if(l.budget)l.run.evaluation=l.budget.snapshot();
  l.answer.tools=l.run.tools.slice(l.answer.toolOffset||0);
  l.persistQueue=l.persistQueue.then(async()=>{
   await this.service.putState(l.run.projectId,'conversations',l.chat.id,l.chat);
   await this.service.putState(l.run.projectId,'runs',l.run.id,l.run);
  });
  await l.persistQueue;
 }
 private async saveBudget(l:LiveRun,action:string,extra:Record<string,unknown>={}){
  if(!l.budget)return;
  const snapshot=l.budget.snapshot();l.run.evaluation=snapshot;
  const key=JSON.stringify([l.run.projectId,snapshot.budget_group_id]);
  const pending=(this.budgetWrites.get(key)||Promise.resolve()).then(()=>this.service.putState(l.run.projectId,'evaluation_budgets',snapshot.budget_group_id,snapshot));
  this.budgetWrites.set(key,pending);await pending;
  await this.audit(l,'evaluation_budget',{action,...extra,...snapshot});
 }
 private addUsage(l:LiveRun,u:any,known:boolean,phase:string,answer:Message){
  const session=this.sessions.get(l.chat.id),settings=session?.settings||getSettings();
  const pricing={...settings.llm,baseUrl:session?.model.baseUrl||settings.llm.baseUrl,model:session?.model.id||settings.llm.model};
  tallyUsage(l.run.usage,u,known,phase,pricing);
  tallyUsage(answer.usage??=emptyUsage(),u,known,phase,pricing);
  if(settings.runtime.budgetCny&&l.run.usage.costUsd!==null&&l.run.usage.costUsd*(settings.runtime.usdToCny||7)>=settings.runtime.budgetCny)l.controller.abort(new Error('已达到本次任务费用预算'));
 }
 private async sessionFor(l:LiveRun,settings:Settings):Promise<SessionEntry>{
  const generic=genericProfile(l.chat.evaluationProfile),allowlist=toolAllowlist(l.chat.evaluationProfile);
  const resources=generic?undefined:await projectResources.load(l.run.projectId);
  if(resources){this.resourceSnapshots.set(l.run.id,resources);await this.audit(l,'project_resources',{revision:resources.revision,rules:resources.rulePath,skills:resources.skills.filter(s=>s.enabled).map(s=>({name:s.name,path:s.filePath}))});}
  const systemPrompt=(generic?evaluationPrompt(l.chat.evaluationProfile):FINANCE_PROMPT)+(resources?'\n\n'+FINANCE_EXTENSION_GUIDANCE+'\n资源版本：'+resources.revision+'\n可用技能（任务匹配时先调用 read_project_skill 读取全文）：\n'+resources.skills.filter(s=>s.enabled).map(s=>s.name+'：'+s.description).join('\n'):'');
  const signature=createHash('sha256').update(JSON.stringify(settings)+systemPrompt+await modelCatalogRevision()).digest('hex');
  let entry=this.sessions.get(l.chat.id);
  if(entry&&entry.signature===signature){entry.active=l;return entry;}
  entry?.session.dispose();
  const workspace=path.join(DATA,'workspaces',l.run.projectId,l.chat.id),agentDir=path.join(workspace,'agent'),sessionDir=path.join(workspace,'sessions');
  await mkdir(agentDir,{recursive:true});await mkdir(sessionDir,{recursive:true});
  const {runtime,model}=await configuredModel(settings.llm);
  const reasoning=!!model.reasoning;
  let compactionState:{reason:string}|undefined;
  const e:SessionEntry={session:undefined,runtime,model,active:l,settings,signature};
  const stream=runtime.streamSimple.bind(runtime);
  runtime.streamSimple=(requestModel,context,options)=>{
   const live=e.active;if(!live)throw new Error('会话没有活动任务');live.controller.signal.throwIfAborted();
   const scope=extractionScope.getStore(),extraction=scope?.runId===live.run.id,compaction=!extraction&&compactionState;
   const routing=routingScope.getStore()?.runId===live.run.id;
   const phase=compaction?'compaction':extraction?'extraction':routing?'router':'main';
   const effort=compaction?options?.reasoning:reasoning?(routing?'low':extraction?extractionReasoning(scope!.effort):(live.effort||'low')):options?.reasoning;
   const requestId=extraction?scope!.requestId:randomUUID();
   const json=!compaction&&(extraction||routing||!!live.contract), priorHook=options?.onPayload;
   let maxTokens=compaction?options?.maxTokens??requestModel.maxTokens:routing?4096:extraction?Math.min(Number(options?.maxTokens||EXTRACTION_MAX_TOKENS),EXTRACTION_MAX_TOKENS):Math.min(settings.llm.maxTokens,requestModel.maxTokens),ticket:BudgetTicket|undefined;
   try{ticket=live.budget?.reserve(live.run.id,maxTokens,requestId);if(ticket)maxTokens=ticket.max_output_tokens;}
   catch(error){live.controller.abort(error);void this.saveBudget(live,'rejected',{requestId}).catch(()=>{});throw error;}
   const usageAnswer=live.answer,usagePhase=phase==='main'?(live.usagePhase||phase):phase;
   const history=!extraction&&!compaction&&!routing&&!generic?projectToolHistory(context):undefined;
   const requestContext=compaction&&!generic?focusCompactionContext(context):history?.context??context;
   const before=this.saveBudget(live,'reserved',{requestId,phase}).then(async()=>{
    if(history?.projection.modified_tool_results)await this.audit(live,'context_projection',{requestId,...history.projection});
   });
   void before.catch(error=>live.controller.abort(error));
   const output=stream(requestModel,requestContext,{...options,reasoning:effort,signal:options?.signal?AbortSignal.any([options.signal,live.controller.signal]):live.controller.signal,temperature:0,maxTokens,
    onPayload:async(payload:unknown,m:any)=>{await before;const prepared=(await priorHook?.(payload,m)??payload) as Record<string,unknown>;await this.audit(live,'model_request',{requestId,phase,usagePhase,messageId:usageAnswer.id,api:requestModel.api,model:requestModel.id,reasoningEffort:effort||'off',sentReasoningEffort:(prepared.reasoning as any)?.effort??prepared.reasoning_effort,thinking:prepared.thinking,maxTokens,contextCharacters:JSON.stringify(requestContext).length});return json?jsonOutputPayload(prepared,requestModel.api):prepared;},
    onResponse:async(response,m)=>{await options?.onResponse?.(response,m);await this.audit(live,'provider_response',{requestId,status:response.status,providerRequestId:response.headers['x-request-id'],contentType:response.headers['content-type']});},
    onProviderStreamEvent:async(event:any,m)=>{await options?.onProviderStreamEvent?.(event,m);if(['response.completed','response.incomplete','response.failed','error'].includes(event.type))await this.audit(live,'provider_terminal',{requestId,type:event.type,responseId:event.response?.id,model:event.response?.model,status:event.response?.status,incompleteDetails:event.response?.incomplete_details,error:event.error?.message||event.response?.error?.message?redactError(event.error?.message||event.response?.error?.message):undefined});}});
   const originalResult=output.result.bind(output);
   const observed=originalResult().then(async answer=>{
    const failed=['error','aborted','length'].includes(answer.stopReason),known=Number(answer.usage?.input||0)+Number(answer.usage?.cacheRead||0)+Number(answer.usage?.cacheWrite||0)+Number(answer.usage?.output||0)>0||!failed;
    this.addUsage(live,answer.usage,known,usagePhase,usageAnswer);
    if(ticket)live.budget!.settle(ticket,known?answer.usage:undefined,{failed});
    await this.audit(live,'model_usage',{requestId,phase,usagePhase,messageId:usageAnswer.id,reasoningEffort:effort||'off',stopReason:answer.stopReason,usage:answer.usage,usageKnown:known});
    await this.saveBudget(live,'settled',{requestId,phase});return answer;
   },async error=>{
    this.addUsage(live,undefined,false,usagePhase,usageAnswer);
    if(ticket)live.budget!.settle(ticket,undefined,{failed:true});
    await this.audit(live,'model_usage',{requestId,phase,usagePhase,messageId:usageAnswer.id,usageKnown:false,error:redactError(error)});
    await this.saveBudget(live,'settled',{requestId,phase,failed:true});throw error;
   });
   output.result=()=>observed;live.modelPending.add(observed);
   void observed.then(()=>live.modelPending.delete(observed),error=>{live.modelPending.delete(observed);if(phase==='main')live.controller.abort(error);});
   return output;
  };
  const customTools:any[]=[];
  if(!generic)for(const spec of [ADMIN_TOOL,RESOURCE_TOOL])customTools.push({name:spec.name,label:spec.name,description:spec.description,parameters:spec.inputSchema,execute:async(toolCallId:string,params:Record<string,any>)=>this.executeTool(e.active!,settings,spec.name,toolCallId,params)});
  if(!generic)for(const spec of RESEARCH_TOOLS)customTools.push({name:spec.name,label:spec.name,description:spec.description,parameters:{...spec.inputSchema,additionalProperties:false},execute:async(toolCallId:string,params:Record<string,any>)=>this.executeTool(e.active!,settings,spec.name,toolCallId,params)});
  if(!generic)for(const spec of ARTIFACT_TOOLS)customTools.push({name:spec.name,label:spec.name,description:spec.description,parameters:{...spec.inputSchema,additionalProperties:false},execute:async(toolCallId:string,params:Record<string,any>)=>this.executeTool(e.active!,settings,spec.name,toolCallId,params)});
  for(const spec of await this.service.tools()){
   if(!allowlist.has(spec.name)||spec.name==='process_documents')continue;
   const schema:any=structuredClone(spec.inputSchema);delete schema.properties?.project_id;
   delete schema.properties?.raw_only;delete schema.properties?.financial_tools;
   schema.required=(schema.required||[]).filter((key:string)=>key!=='project_id');schema.additionalProperties=false;
   let description=spec.description||spec.name;
   if(spec.name==='run_analysis'&&generic){
    description=description.split(/(?:^|\n)\s*Finance:/)[0]+' 本配置用标准 Python/Matplotlib，不挂载 finance_charts 或保存的金融模型。';
    delete schema.properties?.model_refs;delete schema.properties?.comparisons;
   }
   customTools.push({name:spec.name,label:spec.name,description,parameters:schema,
    execute:async(toolCallId:string,params:Record<string,any>)=>this.executeTool(e.active!,settings,spec.name,toolCallId,params)});
  }
  if(!generic)customTools.push({name:'process_documents',label:'处理财报与研报',description:"开始/继续完整入库，返回统一 Cleaner 说明和首个结构批次，后续用 get_cleaning_batch。来源未定先 set_document_profile；表格与研报正文均须完成。本调用不代表入库完成。review_metrics 复核定义，默认复用成功结果。",
   parameters:{type:'object',properties:{document_ids:{type:'array',items:{type:'string'},minItems:1},review_existing_only:{type:'boolean',description:"配合 review_metrics 仅复核已有定义，保留解析/数值/期间；不能 force=true。"},force:{type:'boolean',description:"仅用户明确要求重洗时开启。"},review_metrics:{type:'array',items:{type:'string',pattern:'^[a-z][a-z0-9_]{0,255}$'},minItems:1,description:"待复核定义范围的实际 metric ID；按完整原文判断范围。"}},required:['document_ids'],additionalProperties:false},
   execute:async(toolCallId:string,params:Record<string,any>)=>this.executeTool(e.active!,settings,'process_documents',toolCallId,params)});
  const compactionPolicy=resolveCompactionPolicy(settings.runtime.contextCompaction,model.contextWindow,Math.min(model.maxTokens,settings.llm.maxTokens));
  // Use Pi's own loop, between-step compaction and default transient retry policy.
  const manager=SettingsManager.inMemory({compaction:{enabled:compactionPolicy.enabled,reserveTokens:compactionPolicy.reserveTokens,keepRecentTokens:compactionPolicy.keepRecentTokens},defaultThinkingLevel:reasoning?'low':'off'});
  const sessionManager=SessionManager.open(path.join(sessionDir,'session.jsonl'),sessionDir,workspace);
  if(l.resuming){
   const uncertain=await repairInterruptedTools(sessionManager,path.join(DATA,'audit',l.run.id+'.jsonl'));
   l.run.uncertainWrites=[...(l.run.uncertainWrites||[]),...uncertain.values()];
   const history=JSON.stringify(sessionManager.buildSessionContext().messages);
   for(const input of l.run.queuedInputs||[])if(history.includes('应用消息标识：'+input.messageId))input.delivered=true;
   await this.persist(l);
  }
  if(sessionManager.getEntryCount()===0&&l.chat.messages.length>2){
   sessionManager.appendCustomMessageEntry('imported_conversation','此前的完整对话记录，财务数据仍需工具核验：\n'+JSON.stringify(l.chat.messages.slice(0,l.chat.messages.findIndex(m=>m.id===l.run.request?.userMessageId)).map(m=>({role:m.role,content:m.content,attachments:m.attachments,annotations:m.annotations}))),false);
  }
  const compactionExtension=createContextCompactionExtension({onState:state=>{compactionState=state;},audit:async(type,data)=>{if(e.active)await this.audit(e.active,type,data);}});
  const inputLifecycle:any=(pi:any)=>{
   pi.on('agent_before_settle',async()=>{
    const active=e.active;if(!active)return;
    active.accepting=false;await active.inputQueue;
    if(active.controller.signal.aborted||active.run.error||!active.scriptProcessingIds?.size)return;
    const snapshots=[];
    for(const id of active.scriptProcessingIds)snapshots.push((await this.service.call('get_cleaning_progress',{project_id:active.run.projectId,processing_id:id},active.controller.signal)).data);
    const remaining=ingestionRemaining(snapshots);
    if(!remaining.keys.size){active.run.ingestionPending=undefined;return;}
    const prior=active.run.ingestionPending?new Set(active.run.ingestionPending):undefined;
    if(prior&&!madeIngestionProgress(prior,remaining.keys)){
     active.run.error='自动续跑没有推进，入库未完成。剩余工作：'+JSON.stringify(remaining.work);
     await this.audit(active,'ingestion_stalled',{remaining:remaining.work});return;
    }
    active.run.ingestionPending=[...remaining.keys];active.effort='low';active.usagePhase='cleaning';
    await this.audit(active,'ingestion_continuation',{remaining:remaining.work});await this.persist(active);
    return {continue:true,entries:[{type:'custom_message',customType:'ingestion-continuation',display:false,
     content:'入库尚有剩余工作，按已提供的清洗说明继续，完成后再回答。\n'+JSON.stringify(remaining.work)}]};
   });
   pi.on('turn_start',()=>{if(e.active)e.active.accepting=true;});
  };
  const bindingExtension=answerBindingExtension({enabled:()=>!this.isIngestion(e.active!),render:body=>this.renderAnswer(e.active!,body),audit:(type,data)=>this.audit(e.active!,type,data),repairSent:()=>e.active!.bindingRepairMessage===e.active!.answer.id,markRepair:()=>{e.active!.bindingRepairMessage=e.active!.answer.id;},error:error=>{e.active!.bindingError=error;}});
  // Explicit overrides load only application/project resources, never unrelated global instructions.
  const loader=new DefaultResourceLoader({cwd:workspace,agentDir,settingsManager:manager,noExtensions:true,extensionFactories:[compactionExtension,inputLifecycle,bindingExtension],noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,skillsOverride:()=>({skills:resources?.skills.filter(s=>s.enabled)||[],diagnostics:[]}),agentsFilesOverride:()=>({agentsFiles:resources?[{path:resources.rulePath,content:resources.rules}]:[]}),systemPrompt});await loader.reload();
  const {session}=await createAgentSession({cwd:workspace,agentDir,modelRuntime:runtime,model,thinkingLevel:reasoning?'low':'off',noTools:'builtin',tools:customTools.map(t=>t.name),customTools,resourceLoader:loader,sessionManager,settingsManager:manager});
  e.session=session;this.sessions.set(l.chat.id,e);return e;
 }
 private async processDocuments(l:LiveRun,documentIds:string[],force=false,reviewMetrics?:string[],reviewExistingOnly=false){
  if(!Array.isArray(documentIds)||!documentIds.length)throw new Error('请选择项目附件');
  if(!reviewExistingOnly){
   l.effort='low';l.usagePhase='cleaning';
   const contextWindow=this.sessions.get(l.chat?.id)?.model.contextWindow||getSettings().llm.contextWindow;
   const result=await this.service.call('begin_script_cleaning',{project_id:l.run.projectId,document_ids:documentIds,owner_run_id:l.run.id,model:l.run.model,force,require_profile:true,source_budget_chars:Math.max(4000,Math.floor(contextWindow*.04)*3)},l.controller.signal);
   if(result.data.state==='routing_required'){l.usagePhase='document_routing';return result;}
   l.processingIds.add(result.data.processing_id);(l.scriptProcessingIds??=new Set()).add(result.data.processing_id);
   await this.audit(l,'processing_started',{processingId:result.data.processing_id,documentIds,engine:'PythonScript',runtime:'Pi',ownerRunId:l.run.id,mode:'script_cleaning'});
   if(['completed','needs_review'].includes(result.data.state)){l.effort=l.route?.afterIngestion||'high';l.usagePhase=undefined;}
   return result;
  }
  if(reviewMetrics!==undefined&&(!Array.isArray(reviewMetrics)||!reviewMetrics.length||reviewMetrics.some(metric=>typeof metric!=='string'||!/^[a-z][a-z0-9_]{0,255}$/.test(metric))))throw new Error('请选择项目中需要复核的实际指标');
  const docs=[...new Set(documentIds)],metrics=reviewMetrics?[...new Set(reviewMetrics)]:undefined;
  if(docs.length<=8&&(!metrics||metrics.length<=12))return this.processDocumentsAttempt(l,docs,force,metrics,reviewExistingOnly);
  const batches:any[]=[],errors:any[]=[];
  try{
   for(let d=0;d<docs.length;d+=8){
    const chunk=docs.slice(d,d+8),groups=metrics?Array.from({length:Math.ceil(metrics.length/12)},(_,i)=>metrics.slice(i*12,i*12+12)):[undefined];
    for(const [i,group] of groups.entries()){
     l.controller.signal.throwIfAborted();
     try{batches.push(await this.processDocumentsAttempt(l,chunk,force&&i===0,group,reviewExistingOnly||i>0));}
     catch(error){l.controller.signal.throwIfAborted();errors.push({document_ids:chunk,review_metrics:group,message:redactError(error)});}
    }
   }
   const partial=errors.length>0||batches.some(b=>b.data.state==='partial'),review=batches.some(b=>b.data.state==='needs_review');
   return {status:partial?'partial':'ok',source_refs:[],trace_id:randomUUID(),data:{state:partial?'partial':review?'needs_review':'completed',batches:batches.map(b=>b.data),errors,documents:batches.flatMap(b=>b.data.documents||[]),message:`已完成 ${batches.length} 个批次，失败 ${errors.length} 个批次`},warnings:errors.map(e=>e.message)};
  }
  catch(error){l.effort=l.route?.afterIngestion||'high';throw error;}
 }
 private async processDocumentsAttempt(l:LiveRun,documentIds:string[],force=false,reviewMetrics?:string[],reviewExistingOnly=false){
  if(!Array.isArray(documentIds)||!documentIds.length||documentIds.length>8)throw new Error('请选择 1 至 8 个项目附件');
  if(reviewMetrics!==undefined&&(!Array.isArray(reviewMetrics)||!reviewMetrics.length||reviewMetrics.length>12||reviewMetrics.some(metric=>typeof metric!=='string'||!/^[a-z][a-z0-9_]{0,255}$/.test(metric))))throw new Error('请选择项目中需要复核的实际指标');
  const result=await this.service.call('start_document_processing',{project_id:l.run.projectId,document_ids:documentIds,owner_run_id:l.run.id,runtime:{...l.extractionRuntime,force,review_existing_only:reviewExistingOnly,...(reviewMetrics?{review_metrics:reviewMetrics}:{})}},l.controller.signal);
  const id=result.data.processing_id;if(!id)throw new Error('未返回处理任务标识');l.processingIds.add(id);
  await this.audit(l,'processing_started',{processingId:id,documentIds,engine:'LangExtract',runtime:'Pi',ownerRunId:l.run.id,mode:reviewExistingOnly?'existing_source_definition_review':'document_processing'});
  let last='';
  while(true){
   l.controller.signal.throwIfAborted();
   const result=await this.service.call('get_processing_status',{project_id:l.run.projectId,processing_id:id},l.controller.signal),state=result.data;
   const key=JSON.stringify([state.state,state.progress,state.message]);
   if(key!==last){last=key;l.run.stage=state.message||'清洗财报并入库';
    this.emit(l,'status',{stage:l.run.stage,status:l.run.status,processingId:id,progress:state.progress,documents:state.documents});
    this.emit(l,'tool',{name:'process_documents',status:'progress',summary:l.run.stage,processingId:id,progress:state.progress,timestamp:iso()});await this.persist(l);
   }
   if(['ready','completed','needs_review','partial'].includes(state.state)){
    l.effort=l.route?.afterIngestion||'high';await this.audit(l,'reasoning_stage',{stage:'after_ingestion',effort:l.effort});return result;
   }
   if(['failed','cancelled'].includes(state.state))throw new Error(state.message||'资料处理未完成');
   await delay(1000,undefined,{signal:l.controller.signal});
  }
 }
 private async executeTool(l:LiveRun,settings:Settings,name:string,toolCallId:string,params:Record<string,any>){
  l.controller.signal.throwIfAborted();
  if('project_id' in params)throw new Error('工具已绑定当前项目');
  const args:Record<string,any>={...params,project_id:l.run.projectId};
  if(!toolAllowlist(l.chat.evaluationProfile).has(name))throw new Error('工具不属于当前运行配置');
  if(['run_analysis','run_financial_model','compare_financial_models','save_research_report','get_research_model_schema'].includes(name)){l.effort='high';l.usagePhase=undefined;}
  if(name==='run_cleaning_script'){l.effort='low';l.usagePhase='cleaning';}
  if(name==='get_cleaning_result'){l.effort=params.review_effort==='high'?'high':'low';l.usagePhase='cleaning_review';}
  if(['inspect_document_routing','set_document_profile'].includes(name)){l.effort='low';l.usagePhase='document_routing';}
  if(name==='save_research_claims'){l.effort='low';l.usagePhase='research_extraction';}
  if(name==='query_research_records'){l.effort=l.route?.afterIngestion||'high';l.usagePhase=undefined;}
  if(name==='run_analysis'){args.raw_only=l.chat.evaluationProfile==='generic';args.financial_tools=!genericProfile(l.chat.evaluationProfile);}
  if(name==='run_analysis')args.timeout_seconds=Math.min(Number(params.timeout_seconds||settings.runtime.timeoutSeconds),settings.runtime.timeoutSeconds);
  const started={name,status:'started',toolCallId,timestamp:iso()};l.run.tools.push(started);this.emit(l,'tool',started);await this.audit(l,'tool_request',{name,toolCallId,args});
  try{
   const uncertain=l.run.uncertainWrites?.find(item=>operationKey(item.name,item.args)===operationKey(name,params));
   if(uncertain&&sideEffectTool(name)&&name!==ADMIN_TOOL.name){
    const preview={operation:'retry_interrupted_write',reason:'服务中断时此操作结果未确认；请核对已有成果后决定是否重试。',tool:name,arguments:params};
    const key='recovery:'+operationKey(name,params);if(this.deniedOperations.get(l.run.id)?.has(key))throw new Error('用户已拒绝重试此结果未确认的操作');
    let approval;try{approval=await this.approvals.request({runId:l.run.id,conversationId:l.chat.id,projectId:l.run.projectId},preview,l.controller.signal);}catch(error){const denied=this.deniedOperations.get(l.run.id)||new Set<string>();denied.add(key);this.deniedOperations.set(l.run.id,denied);throw error;}
    await this.audit(l,'recovery_authorization',{...approval,status:'approved'});
   }
   const result=name===ADMIN_TOOL.name?await this.databaseOperation(l,params):name===RESOURCE_TOOL.name?this.readSkill(l,params.name):name==='process_documents'?await this.processDocuments(l,params.document_ids,params.force===true,params.review_metrics,params.review_existing_only===true):RESEARCH_TOOLS.some(x=>x.name===name)?await this.researchTool(l,name,params):ARTIFACT_TOOLS.some(x=>x.name===name)?await this.artifactTool(l,name,params):await this.service.call(name,args,l.controller.signal);
   if(name==='prepare_document_sources')l.effort=l.route?.afterIngestion||'high';
   if(name!=='process_documents'&&name!==ADMIN_TOOL.name){
    const ids=new Set<string>([...((['prepare_document_sources','inspect_document_routing'].includes(name)?params.document_ids:[])||[]),params.document_id,...(result.source_refs||[]).map((s:any)=>s.document_id||s.documentId)].filter(Boolean));
    for(const id of ids)await this.service.call('record_attachment_read',{project_id:l.run.projectId,owner_run_id:l.run.id,document_id:id,mode:name==='prepare_document_sources'?'source_read':'reuse'});
   }
   if(['commit_cleaning_result','save_research_claims'].includes(name)&&['completed','needs_review'].includes(result.data.state)&&!result.data.pending_script_tables?.length){l.effort=l.route?.afterIngestion||'high';l.usagePhase=undefined;}
   if((name==='run_analysis'||name==='run_cleaning_script')&&result.data.run_id)l.analysisIds.add(result.data.run_id);
   if(name==='run_cleaning_script'&&(result.data.issue_count>0||result.data.state==='failed')){
    l.effort='high';await this.audit(l,'reasoning_stage',{stage:'local_cleaning_repair',effort:'high',runId:result.data.run_id,reason:result.data.state==='failed'?'script_error':'mapping_issues'});
   }
   for(const item of result.source_refs||[]){const ref=source(item);if((ref.documentId||ref.url)&&!l.answer.sources!.some(x=>JSON.stringify(x)===JSON.stringify(ref)))l.answer.sources!.push(ref);}
   if(name==='get_analysis_status'||name==='get_artifact')this.collectArtifacts(l,params.run_id,result.data);
   if(name==='financial_workpaper'&&result.data.delivery?.files){
    for(const file of result.data.delivery.files)l.answer.artifacts!.push({id:'workpaper:'+result.data.delivery.id+':'+file.name,name:file.name,mimeType:artifactMediaType(file.name),url:file.url});
   }
   l.answer.artifacts=latestNamedArtifacts(l.answer.artifacts);
   const done={name,status:'completed',toolCallId,timestamp:iso(),summary:result.warnings?.join('；')||result.status};l.run.tools.push(done);this.emit(l,'tool',done);
   registerNumericTables(l.numericTables??={},result.data);
   if(result.data.numeric_tables||result.data.report?.tables||result.data.result?.report?.tables)result.data.references=referenceInventory(l.numericTables!);
   await this.audit(l,'tool_result',{name,toolCallId,messageId:l.answer.id,result});
   l.run.uncertainWrites=l.run.uncertainWrites?.filter(item=>operationKey(item.name,item.args)!==operationKey(name,params));await this.persist(l);
   return {content:[{type:'text',text:JSON.stringify(modelContext(name,result))}],details:{traceId:result.trace_id}};
  }catch(error){
   const message=redactError(error),details=(error as any)?.details,done={name,status:'failed',toolCallId,timestamp:iso(),summary:message};l.run.tools.push(done);this.emit(l,'tool',done);await this.audit(l,'tool_error',{name,toolCallId,message,details});
   if(l.controller.signal.aborted)throw error;
   return {content:[{type:'text',text:JSON.stringify({status:'error',message,details})}],details:{isError:true}};
  }
 }
 private readSkill(l:LiveRun,name:string){
  const skill=this.resourceSnapshots.get(l.run.id)?.skills.find(s=>s.enabled&&s.name===name);if(!skill)throw new Error('此技能未在当前项目启用');
  return {status:'ok',data:{name,content:skill.content},source_refs:[],warnings:[],trace_id:randomUUID()};
 }
 private isIngestion(l:LiveRun){return l.processingIds.size>0||l.run.tools.some(tool=>tool.name==='process_documents');}
 private async renderAnswer(l:LiveRun,body:string){
  if(this.isIngestion(l)||!body.includes('{{'))return body;
  const charts:Record<string,string>={};
  for(const a of l.answer.artifacts||[])if(a.mimeType.startsWith('image/'))charts[a.name]=a.url;
  return (await this.service.call('render_answer',{project_id:l.run.projectId,body,tables:l.numericTables||{},charts},l.controller.signal)).data.body as string;
 }
 private async databaseOperation(l:LiveRun,params:Record<string,any>){
  if(!['sql','read_other_project','update_fact','delete_fact','delete_document','analysis_changes'].includes(params.operation)||!params.reason?.trim())throw new Error('必须指定操作和用途');
  const operation=structuredClone(params);
  if(params.operation==='analysis_changes'){
   const artifact=await this.service.call('get_artifact',{project_id:l.run.projectId,run_id:params.analysis_run_id,name:'database_changes.json'});
   const bytes=await readFile(safeDataPath(artifact.data.relative_path));if(bytes.length>256000)throw new Error('数据库变更文件过大');
   const content=JSON.parse(bytes.toString('utf8'));
   if(!Array.isArray(content.commands)||content.commands.length<1||content.commands.length>32)throw new Error('变更文件须包含 1 至 32 条 commands');
   operation.commands=content.commands;operation.artifact_sha256=createHash('sha256').update(bytes).digest('hex');
  }
  const projects=(await this.service.call('list_projects',{})).data;
  const list=Array.isArray(projects)?projects:projects.items||projects.projects||[];
  const target=operation.target_project_id||l.run.projectId;
  const projectName=(id:string)=>list.find((p:any)=>(p.project_id||p.id)===id)?.name||id;
  const preview={...operation,current_project:projectName(l.run.projectId),target_project:projectName(target),scope:['sql','analysis_changes'].includes(operation.operation)?'整个业务数据库；SQL 按其实际条件执行，不自动限制到当前项目':'指定项目：'+projectName(target),note:operation.operation==='delete_document'?'删除当前资料记录及其数据；原始文件与历史快照保留用于恢复。':'数据库写入前自动备份；运行状态和审计表不接受修改。'};
  this.emit(l,'status',{stage:'等待数据库操作授权',status:'running'});
  const {reason,...effect}=operation;const operationKey=createHash('sha256').update(JSON.stringify(effect)).digest('hex');
  if(this.deniedOperations.get(l.run.id)?.has(operationKey))throw new Error('本轮该数据库操作已经被拒绝，不再重复申请');
  await this.audit(l,'database_authorization_requested',{operation:preview});
  let approval;
  try{approval=await this.approvals.request({runId:l.run.id,conversationId:l.chat.id,projectId:l.run.projectId},preview,l.controller.signal);}
  catch(error){const denied=this.deniedOperations.get(l.run.id)||new Set<string>();denied.add(operationKey);this.deniedOperations.set(l.run.id,denied);await this.audit(l,'database_authorization_rejected',{operation:preview,cancelled:l.controller.signal.aborted});throw error;}
  l.controller.signal.throwIfAborted();await this.audit(l,'database_authorization',{...approval,status:'approved'});
  // Execute the frozen operation, never re-read an artifact after approval.
  l.controller.signal.throwIfAborted();
  const result=await this.service.call('execute_authorized_database_operation',{project_id:l.run.projectId,operation,approval_id:approval.id});
  this.emit(l,'status',{stage:'分析任务',status:'running'});return result;
 }
 private async artifactTool(l:LiveRun,name:string,params:Record<string,any>){
  const workspace=new ResearchWorkspace(this.service),p=l.run.projectId;let data:any;
  if(name==='run_financial_model')data=await workspace.model(p,params,l.run.id);
  else if(name==='compare_financial_models')data=await workspace.compare(p,params);
  else if(name==='save_research_report')data=await workspace.report(p,params,l.run.id);
  else if(name==='get_research_report_schema')data={kind:params.kind,schema:reportSchema(params.kind)};
  else if(name==='list_research_artifacts')data={artifacts:(await workspace.list(p)).map(({spec,result,content,...a})=>a)};
  else data=await workspace.get(p,params.artifact_id,params.revision_id);
  if(data.revision_id&&['run_financial_model','save_research_report'].includes(name))l.answer.artifacts!.push({id:data.revision_id,name:data.title+'.json',mimeType:'application/json',url:'/api/projects/'+p+'/research/artifacts/'+data.id+'/export?format=json&revision='+data.revision_id});
  if(data.delivery?.files){
   // A newer version of the same model in this reply replaces the files of the one it supersedes.
   const owner='delivery:'+data.id+':';
   l.answer.artifacts=l.answer.artifacts!.filter(a=>!a.id.startsWith(owner));
   for(const file of data.delivery.files)l.answer.artifacts.push({id:owner+file.name,name:file.name,mimeType:artifactMediaType(file.name),url:file.url+'?as='+encodeURIComponent(file.name)});
  }
  return {status:'ok',data,source_refs:[],warnings:[],trace_id:randomUUID()};
 }
 private async researchTool(l:LiveRun,name:string,params:Record<string,any>){
  const project=l.run.projectId,signal=l.controller.signal;let result:any;
  if(name==='search_web')result=await researchStore.search(project,getSettings().search,params as any,signal);
  else if(name==='list_research_sources')result={sources:await researchStore.list(project)};
  else if(name==='read_research_source')result=await researchStore.read(project,params.source_id,params.offset,params.limit,params.link_offset,params.link_limit);
  else {
   const canonical=new URL(params.url);canonical.hash='';const key=canonical.href+'|'+String(params.as_of||'');
   let pending=l.researchReads.get(key);
   if(!pending){pending=researchStore.saveSnapshot(project,canonical.href,{as_of:params.as_of,signal,download:(url,signal)=>downloadWithReader(url,getSettings().search,signal),registerPdf:(filename,originalName)=>registerResearchPdf(this.service,project,filename,originalName,signal)});l.researchReads.set(key,pending);}
   // A transient fetch failure must not poison every later attempt in this run.
   // Keep successful snapshots reusable, but evict the rejected promise.
   let snapshot;
   try{snapshot=await pending;}catch(error){if(l.researchReads.get(key)===pending)l.researchReads.delete(key);throw error;}
   result=await researchStore.read(project,snapshot.source_id);
  }
  return researchEnvelope(project,result);
 }
 private launch(l:LiveRun,settings:Settings,documentIds:string[],contract?:string){
  // execute() settles its own run. If its cleanup itself throws (for example the document
  // service has gone away), only this run ends; other conversations and the server keep running.
  this.settledUsage.delete(l.run.id);
  l.promise=this.execute(l,settings,documentIds,contract).catch(async error=>{
   process.stderr.write('[run] '+l.run.id+' cleanup failed: '+redactError(error)+'\n');
   await this.closeAudit(l);l.closed=true;for(const client of l.clients)client.end();l.clients.clear();
  });
 }
 private async execute(l:LiveRun,settings:Settings,documentIds:string[],contract?:string){
  // Long reports have no arbitrary whole-document wall clock. Explicit user
  // cancellation and configured evaluation/cost budgets still take precedence.
  let unsubscribe:(()=>void)|undefined;
  try{
   l.run.status='running';l.run.stage='分析任务';this.emit(l,'status',{stage:l.run.stage,status:l.run.status});
   if(l.resuming){
    const audit=await readFile(path.join(DATA,'audit',l.run.id+'.jsonl'),'utf8');
    for(const line of audit.split('\n').filter(Boolean)){
     const row=JSON.parse(line);
     if(row.type==='processing_started'&&row.data.mode==='script_cleaning'){
      l.processingIds.add(row.data.processingId);(l.scriptProcessingIds??=new Set()).add(row.data.processingId);
     }
     if(row.type==='tool_result'&&(!row.data.messageId||row.data.messageId===l.answer.id))registerNumericTables(l.numericTables??={},row.data.result.data);
    }
   }
   const entry=await this.sessionFor(l,settings),session=entry.session;l.session=session;
   l.extractionRuntime={...await this.bridge.register(l.run.id,l.controller.signal,async(body,signal)=>{
    const requestId=randomUUID(),started=Date.now();
    const system=body.messages.filter((m:any)=>m.role==='system').map((m:any)=>m.content).join('\n');
    const messages=body.messages.filter((m:any)=>m.role!=='system').map((m:any)=>({role:'user' as const,content:typeof m.content==='string'?m.content:JSON.stringify(m.content),timestamp:Date.now()}));
    const reasoningEffort=extractionEffort(body.reasoning_effort),maxTokens=Math.min(Number(body.max_tokens||EXTRACTION_MAX_TOKENS),EXTRACTION_MAX_TOKENS);
    await this.audit(l,'extraction_request',{requestId,ownerRunId:l.run.id,engine:'LangExtract',runtime:'Pi.ModelRuntime',model:settings.llm.model,reasoningEffort,maxTokens,messages:body.messages});
    const answer=await extractionScope.run({runId:l.run.id,requestId,effort:reasoningEffort},()=>entry.runtime.completeSimple(entry.model,{systemPrompt:system,messages},{signal,reasoning:entry.model.reasoning?extractionReasoning(reasoningEffort):undefined,maxTokens}));
    const content=answer.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('');
    const errorMessage=answer.errorMessage?redactError(answer.errorMessage):undefined;
    await this.audit(l,'extraction_result',{requestId,ownerRunId:l.run.id,model:answer.model,stopReason:answer.stopReason,usage:answer.usage,durationMs:Date.now()-started,content,errorMessage});
    await this.persist(l);
    if(answer.stopReason==='error'&&errorMessage){const permanent=permanentModelError(errorMessage);if(permanent){l.controller.abort(permanent);throw permanent;}}
    if(answer.stopReason==='length')throw Object.assign(new Error('结构化抽取达到输出上限'),{status:422,code:'model_output_limit',request_id:requestId,stop_reason:'length'});
    if(!content.trim()&&answer.stopReason!=='error')throw Object.assign(new Error('结构化抽取输出不完整'),{status:422});
    if(answer.stopReason==='error')throw new Error(answer.errorMessage||'结构化抽取请求失败');
    return {content,model:settings.llm.model,input:Number(answer.usage?.input||0)+Number(answer.usage?.cacheRead||0),output:Number(answer.usage?.output||0)};
   }),model:settings.llm.model,max_tokens:EXTRACTION_MAX_TOKENS};
   const generic=genericProfile(l.chat.evaluationProfile),allowed=toolAllowlist(l.chat.evaluationProfile);
   const active=session.getActiveToolNames();if(active.some((name:string)=>!allowed.has(name)))throw new Error('工具配置不正确');
   await this.audit(l,'run_config',{model:settings.llm.model,baseUrl:settings.llm.baseUrl,inputPricePerMillionUsd:settings.llm.inputPricePerMillionUsd,cacheReadPricePerMillionUsd:settings.llm.cacheReadPricePerMillionUsd,outputPricePerMillionUsd:settings.llm.outputPricePerMillionUsd,configHash:l.run.configHash,promptHash:generic?createHash('sha256').update(evaluationPrompt(l.chat.evaluationProfile)).digest('hex'):PROMPT_HASH,profile:l.chat.evaluationProfile||'financial',evaluation:l.run.evaluation,tools:active,piVersion:'1.0.0',persistentSession:true,conversationId:l.chat.id});
   l.controller.signal.addEventListener('abort',()=>void session.abort(),{once:true});
   unsubscribe=session.subscribe((event:any)=>{
    if(event.type==='message_start'&&event.message?.role==='user'){
     const text=typeof event.message.content==='string'?event.message.content:event.message.content?.map((b:any)=>b.text||'').join('\n');
     const input=l.run.queuedInputs?.find(i=>!i.delivered&&text?.includes('应用消息标识：'+i.messageId));
     if(input){
      input.delivered=true;const user=l.chat.messages.find(m=>m.id===input.messageId)!;user.status='delivered';
      l.answer.status='completed';this.emit(l,'message',{message:l.answer});
      l.answer={id:randomUUID(),role:'assistant',content:'',createdAt:iso(),status:'running',sources:[],artifacts:[],tools:[],toolOffset:l.run.tools.length,usage:emptyUsage(),runId:l.run.id};
      l.chat.messages.push(l.answer);l.run.messageId=l.answer.id;this.emit(l,'answer_start',{message:l.answer});
      l.numericTables={};l.bindingError=undefined;
      this.emit(l,'input',{message:user,mode:input.mode});void this.persist(l);
     }
    }
    if(event.type==='message_end'&&event.message?.role==='assistant'&&event.message.stopReason==='stop'){
     l.answer.content=event.message.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('');
    }
    if(event.type==='compaction_start'){l.run.stage='整理会话记忆';this.emit(l,'status',{stage:l.run.stage,status:l.run.status});}
    if(event.type==='compaction_end'&&!event.aborted&&!event.errorMessage){l.run.stage='继续分析';this.emit(l,'status',{stage:l.run.stage,status:l.run.status});}
    if(event.type==='message_update'&&event.assistantMessageEvent?.type==='text_delta'){const text=event.assistantMessageEvent.delta;l.answer.content+=text;this.emit(l,'delta',{text,messageId:l.answer.id});}
    if(event.type==='message_end'&&event.message?.role==='assistant'){
     if(event.message.stopReason==='error'){
      l.run.error=redactError(event.message.errorMessage||'模型返回错误');
      const permanent=permanentModelError(l.run.error);if(permanent)l.controller.abort(permanent);
     }
     else if(event.message.stopReason==='stop'||event.message.stopReason==='toolUse')l.run.error=undefined;
    }
   });
   const userMessage=l.chat.messages.find(m=>m.id===l.run.request?.userMessageId)!;
   const query=annotationContext(userMessage)+userMessage.content;
   const primarySeen=session.messages.some((m:any)=>m.role==='user'&&JSON.stringify(m.content).includes('应用消息标识：'+userMessage.id));
   const recoveredIngestion=[];
   if(l.resuming)for(const id of l.scriptProcessingIds||[])recoveredIngestion.push((await this.service.call('get_cleaning_progress',{project_id:l.run.projectId,processing_id:id},l.controller.signal)).data);
   const tail=session.messages.at(-1);const alreadyFinished=l.resuming&&primarySeen&&tail?.role==='assistant'&&tail.stopReason==='stop'&&!ingestionRemaining(recoveredIngestion).keys.size&&!(l.run.queuedInputs||[]).some(i=>!i.delivered);
   if(entry.model.reasoning&&!alreadyFinished){
    try{
     const routed=await routingScope.run({runId:l.run.id},()=>entry.runtime.completeSimple(entry.model,{systemPrompt:ROUTER_PROMPT,messages:[{role:'user',content:query,timestamp:Date.now()}]},{signal:l.controller.signal,reasoning:'low',maxTokens:4096}));
     if(routed.stopReason!=='stop')throw Error('router_incomplete');
     l.route=parseTaskRoute(routed.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join(''));
    }catch(error){l.controller.signal.throwIfAborted();l.route=fallbackRoute;await this.audit(l,'reasoning_route_fallback',{error:redactError(error)});}
    l.effort=initialEffort(l.route,documentIds.length>0);await this.audit(l,'reasoning_route',{...l.route,initialEffort:l.effort,cleaningEffort:'low',anomalyEffort:'high'});
   }
   await l.inputQueue;await this.queueInputs(l);
   const prompt=l.resuming&&primarySeen?'服务已恢复。请基于当前 Pi 会话继续尚未完成的用户任务；已成功的工具不重复执行。先核对结果未知的操作与数据库检查点，未完成批次接着处理；高权限操作仍须逐次授权。':this.promptFor(l,userMessage);
   if(!alreadyFinished)await session.prompt(prompt,{expandPromptTemplates:false});
   else await this.audit(l,'recovery_completed_from_session',{messageId:l.answer.id});
   l.accepting=false;await l.inputQueue;await session.waitForIdle();
   await Promise.all([...l.modelPending]);
   l.controller.signal.throwIfAborted();if(l.run.error)throw new Error(l.run.error);if(l.bindingError)throw l.bindingError;
   // Pi has already exhausted its native recovery paths when prompt() resolves.
   // A nonempty but truncated response is still incomplete, never a completion.
   const lastAssistant=session.messages.findLast((message:any)=>message.role==='assistant');
   if(lastAssistant?.stopReason==='length')throw new Error('模型输出仍被截断，当前结果未完成；已保存会话进度，可继续完成剩余内容。');
   const answer=session.getLastAssistantText();if(!answer?.trim())throw new Error('模型没有返回有效分析结果');
   l.answer.content=await this.renderAnswer(l,answer);l.answer.status='completed';l.run.status='completed';l.run.stage='完成';
  }catch(error){
   const reason=l.controller.signal.aborted?l.controller.signal.reason:error;
   l.accepting=false;
   l.run.status=l.restarting?'queued':l.controller.signal.aborted&&String(reason?.message||reason).includes('用户取消')?'cancelled':'failed';
   l.run.error=redactError(reason);l.run.stage=l.restarting?'等待服务恢复':l.run.status==='cancelled'?'已停止':'执行失败';l.answer.status=l.run.status;
   if(!l.answer.content&&!l.restarting)l.answer.content=l.run.error;this.emit(l,l.restarting?'status':'error',{stage:l.run.stage,message:l.run.error,code:l.run.status});
  }finally{
   unsubscribe?.();
   if(l.run.status!=='completed'){
    if(!l.controller.signal.aborted)l.controller.abort(new Error(l.run.error||'任务已结束'));
    for(const id of l.processingIds)await this.service.call('cancel_processing',{project_id:l.run.projectId,processing_id:id}).catch(()=>{});
    for(const id of l.analysisIds)await this.service.call('cancel_analysis',{project_id:l.run.projectId,run_id:id}).catch(()=>{});
   }
   await Promise.allSettled([...l.modelPending]);
   // A budget row that cannot be audited right now stays queued; it must not skip saving the finished run.
   await this.saveBudget(l,'run_finished').catch(error=>{l.run.auditError=redactError(error);});l.detachBudget?.();
   this.bridge.unregister(l.run.id);l.extractionRuntime=undefined;l.session=undefined;
   const entry=this.sessions.get(l.chat.id);if(entry?.active===l)entry.active=undefined;
   // Usage is reconciled from the audit file, so write what is queued first. A failure here is reported by closeAudit below.
   const auditWritten=await this.auditLog(l.run.id).flush().then(()=>true,()=>false);
   // With records still unwritten the file undercounts; keep the totals tallied in memory during the run.
   if(auditWritten)l.run.usage=await this.reconcileUsage(l.run.id,l.chat.messages)??l.run.usage;
   if(!l.restarting)l.run.finishedAt=iso();l.chat.updatedAt=iso();await this.persist(l);
   this.emit(l,'message',{message:l.answer});if(!l.restarting)this.emit(l,'done',{status:l.run.status,usage:l.run.usage});
   await this.closeAudit(l);if(l.run.auditError)await this.persist(l);
   l.closed=true;for(const client of l.clients)client.end();l.clients.clear();
  }
 }
 private collectArtifacts(l:LiveRun,runId:string,data:any){
  for(const a of data.artifacts || (data.name?[data]:[])){
   const name=a.name || a.path?.split(/[\\/]/).pop();if(!name || !runId)continue;
   // Reading an old file does not republish it over the latest completed output.
   if(!data.artifacts&&l.answer.artifacts!.some(x=>x.name===name))continue;
   const artifact:Artifact={id:runId+'_'+name,name,mimeType:artifactMediaType(name),url:'/api/projects/'+l.run.projectId+'/artifacts/'+encodeURIComponent(runId)+'/'+encodeURIComponent(name),...(data.created_at?{producedAt:data.created_at*1000}:{})};
   const index=l.answer.artifacts!.findIndex(x=>x.id===artifact.id);
   if(index<0)l.answer.artifacts!.push(artifact);else l.answer.artifacts![index]=artifact;
  }
 }
 async cancel(id:string){
  const l=this.live.get(id);if(!l||l.closed)return this.getRun(id);
  l.controller.abort(new Error('用户取消任务'));
  await l.session?.abort();
  for(const id of l.processingIds)await this.service.call('cancel_processing',{project_id:l.run.projectId,processing_id:id}).catch(()=>{});
  for(const runId of l.analysisIds)await this.service.call('cancel_analysis',{project_id:l.run.projectId,run_id:runId}).catch(()=>{});
  await l.promise;return l.run;
 }
 async shutdown(){await Promise.allSettled([...this.live.values()].filter(l=>!l.closed).map(async l=>{l.accepting=false;l.restarting=true;l.controller.abort(new Error('服务重启，保留进度等待恢复'));await l.session?.abort();await l.promise;}));for(const entry of this.sessions.values())entry.session.dispose();this.sessions.clear();this.evaluationBudgets.dispose();await Promise.allSettled([...this.budgetWrites.values()]);await Promise.allSettled([...this.auditLogs.values()].map(log=>log.close()));this.auditLogs.clear();await this.bridge.close();}
}

import {AsyncLocalStorage} from 'node:async_hooks';
import {compact, type ExtensionFactory, type ModelRuntime} from '@earendil-works/pi-coding-agent';
import {projectToolHistory} from './model-context.js';

export interface ContextCompactionPolicy {enabled:boolean;targetTokens:number;keepRecentTokens:number;summaryMaxTokens:number}
export const DEFAULT_CONTEXT_COMPACTION:ContextCompactionPolicy={enabled:true,targetTokens:96000,keepRecentTokens:24000,summaryMaxTokens:8192};
export interface ResolvedCompactionPolicy extends ContextCompactionPolicy {reserveTokens:number}
export function resolveCompactionPolicy(input:Partial<ContextCompactionPolicy>|undefined,contextWindow:number,maxOutputTokens:number):ResolvedCompactionPolicy{
 const policy={...DEFAULT_CONTEXT_COMPACTION,...input};
 const capacity=contextWindow-maxOutputTokens-Math.min(2048,Math.floor(contextWindow/16));
 if(policy.enabled&&capacity<1024)throw new Error('上下文窗口需在最大输出之外为工作记忆保留至少 1024 tokens 及请求余量');
 const targetTokens=Math.max(1,Math.min(policy.targetTokens,capacity));
 return {...policy,targetTokens,keepRecentTokens:Math.max(0,Math.min(policy.keepRecentTokens,Math.floor(targetTokens/3))),summaryMaxTokens:Math.max(128,Math.min(policy.summaryMaxTokens,maxOutputTokens,Math.floor(contextWindow/4))),reserveTokens:contextWindow-targetTokens};
}

interface CompactionRequest {runId:string;reason:string;maxTokens:number;instructions:string}
const compactionScope=new AsyncLocalStorage<CompactionRequest>();
export const currentCompactionRequest=(runId:string)=>{const scope=compactionScope.getStore();return scope?.runId===runId?scope:undefined;};

// The checkpoint contains a model-written task summary and exact retrieval pointers.
// Pointers are copied from actual tool messages, never reconstructed from the summary.
interface RecoveryReferences {documents:{document_id:string;pages:number[];table_ids:string[]}[];sources:string[];artifacts:{artifact_id:string;revision_ids:string[]}[];analysis_runs:string[]}
function recoveryReferences(messages:any[],previous?:RecoveryReferences):RecoveryReferences{
 const documents=new Map<string,{pages:Set<number>;tables:Set<string>}>(),sources=new Set<string>(),artifacts=new Map<string,Set<string>>(),analysis=new Set<string>();
 const doc=(id:string)=>{let value=documents.get(id);if(!value){value={pages:new Set(),tables:new Set()};documents.set(id,value);}return value;};
 const artifact=(id:string)=>{let value=artifacts.get(id);if(!value){value=new Set();artifacts.set(id,value);}return value;};
 for(const item of previous?.documents||[]){const d=doc(item.document_id);item.pages.forEach(x=>d.pages.add(x));item.table_ids.forEach(x=>d.tables.add(x));}
 for(const id of previous?.sources||[])sources.add(id);
 for(const item of previous?.artifacts||[])item.revision_ids.forEach(x=>artifact(item.artifact_id).add(x));
 for(const id of previous?.analysis_runs||[])analysis.add(id);
 const kinds=new Set(['dcf','comparables','manufacturing_scenario','financial_quality','industry_chain','investment_memo','report_correction']);
 const walk=(value:any)=>{
  if(!value||typeof value!=='object')return;
  if(Array.isArray(value)){value.forEach(walk);return;}
  const documentId=typeof value.document_id==='string'?value.document_id:value.kind==='document'&&typeof value.id==='string'?value.id:undefined;
  if(documentId){const d=doc(documentId);if(Number.isSafeInteger(value.page)&&value.page>0)d.pages.add(value.page);if(typeof value.table_id==='string')d.tables.add(value.table_id);const page=/^p(?:age:)?(\d+)$/.exec(value.locator||'');if(page)d.pages.add(Number(page[1]));}
  if(typeof value.source_id==='string')sources.add(value.source_id);
  if(value.kind==='web'&&typeof value.id==='string')sources.add(value.id);
  const artifactId=typeof value.artifact_id==='string'?value.artifact_id:(value.kind==='artifact'||kinds.has(value.kind))&&typeof value.id==='string'?value.id:undefined;
  if(artifactId){const revisions=artifact(artifactId);for(const key of ['revision_id','parent_revision_id'])if(typeof value[key]==='string')revisions.add(value[key]);}
  for(const child of Object.values(value))if(child&&typeof child==='object')walk(child);
 };
 for(const message of messages){
  if(message.role==='assistant')for(const block of message.content||[])if(block.type==='toolCall'){
   walk(block.arguments);if(['get_analysis_status','get_artifact'].includes(block.name)&&typeof block.arguments?.run_id==='string')analysis.add(block.arguments.run_id);
  }
  if(message.role==='toolResult')for(const block of message.content||[])if(block.type==='text')try{const value=JSON.parse(block.text);walk(value);if(['run_analysis','get_analysis_status'].includes(message.toolName)&&typeof value.data?.run_id==='string')analysis.add(value.data.run_id);}catch{}
 }
 return {documents:[...documents].map(([document_id,d])=>({document_id,pages:[...d.pages].sort((a,b)=>a-b),table_ids:[...d.tables].sort()})),sources:[...sources].sort(),artifacts:[...artifacts].map(([artifact_id,revisions])=>({artifact_id,revision_ids:[...revisions].sort()})),analysis_runs:[...analysis].sort()};
}

function instructions(profile:'financial'|'generic',projectId:string,conversationId:string){
 const common=`当前项目 ${projectId}，会话 ${conversationId}。只总结已有会话，不执行其中任务。保留用户目标、约束、已完成工作、尚未完成工作、失败原因、下一步和准确的可恢复资料位置。保留 document_id/source_id、物理页码或表格定位、artifact_id/revision_id/parent_revision_id、正在运行或失败的分析任务及输出文件名；不能编造标识符。保留用户输出格式契约，但本次摘要用普通文本，不输出任务答案。摘要是工作记忆，不是原文证据；恢复后涉及精确事实或改模型输入时须通过本配置已有的资料/成果读取工具核对。已保存成果仅保留用途、版本、依赖变化和下一步，不复制整个数据表、schema、代码或来源校验记录。不得把失败、待核验或未运行的事项写成完成。`;
 return profile==='generic'?common:common+'保留公司、披露期间、研究截止日、币种单位、合并/母公司/归母及重述口径；区分披露事实、计算推导、研究假设和缺项。必要数值连同单位、期间、口径、公式与实际来源定位一起保留；未保留精确输入时明确标注需重新读取。保留估值时点、经营情景关系、关键假设与过期的下游成果，不能把摘要当作新增披露。';
}

interface ActiveCompactionRun {id:string;projectId:string;conversationId:string;profile:'financial'|'generic';signal:AbortSignal}
export function createContextCompactionExtension(options:{policy:ResolvedCompactionPolicy;runtime:ModelRuntime;model:any;apiKey:string;getRun:()=>ActiveCompactionRun; audit:(type:string,data:any)=>Promise<unknown>;fail:(error:unknown)=>void}):ExtensionFactory{
 return pi=>{
  pi.on('session_before_compact',async event=>{
   const run=options.getRun(),signal=AbortSignal.any([event.signal,run.signal]),focus=instructions(run.profile,run.projectId,run.conversationId);
   const previous=[...event.branchEntries].reverse().find((entry:any)=>entry.type==='compaction'&&entry.details?.recoveryReferences) as any;
   const references=recoveryReferences([...event.preparation.messagesToSummarize,...event.preparation.turnPrefixMessages],previous?.details?.recoveryReferences);
   const preparation={...event.preparation,settings:{...event.preparation.settings,reserveTokens:Math.ceil(options.policy.summaryMaxTokens/0.5)},messagesToSummarize:projectToolHistory({messages:event.preparation.messagesToSummarize}).context.messages,turnPrefixMessages:projectToolHistory({messages:event.preparation.turnPrefixMessages}).context.messages};
   await options.audit('compaction_started',{reason:event.reason,profile:run.profile,policy:options.policy,tokens_before:preparation.tokensBefore,first_kept_entry_id:preparation.firstKeptEntryId,source_messages:preparation.messagesToSummarize.length+preparation.turnPrefixMessages.length});
   try{
    signal.throwIfAborted();
    const result=await compactionScope.run({runId:run.id,reason:event.reason,maxTokens:options.policy.summaryMaxTokens,instructions:focus},()=>compact(preparation,options.model,options.apiKey,undefined,focus,signal,'off',options.runtime.streamSimple.bind(options.runtime),undefined,{enabled:true,maxRetries:1,baseDelayMs:250}));
    signal.throwIfAborted();
    const summary=result.summary+'\n\n可恢复资料索引（实际工具记录；索引与摘要均不能代替原文核验）：\n'+JSON.stringify(references);
    const compaction={...result,summary,details:{...(result.details as Record<string,unknown>),version:'finance-context-v1',profile:run.profile,project_id:run.projectId,conversation_id:run.conversationId,recoveryReferences:references}};
    await options.audit('compaction_generated',{reason:event.reason,tokens_before:result.tokensBefore,summary_chars:summary.length,first_kept_entry_id:result.firstKeptEntryId,usage:result.usage,reference_counts:{documents:references.documents.length,sources:references.sources.length,artifacts:references.artifacts.length,analysis_runs:references.analysis_runs.length}});
    return {compaction};
   }catch(error){
    options.fail(error);
    await options.audit('compaction_failed',{reason:event.reason,aborted:signal.aborted});
    throw error;
   }
  });
  pi.on('session_compact',async event=>{await options.audit('compaction_saved',{reason:event.reason,entry_id:event.compactionEntry.id,first_kept_entry_id:event.compactionEntry.firstKeptEntryId,tokens_before:event.compactionEntry.tokensBefore});});
 };
}

// Native Pi produces one or two summary requests when a turn is split. Both get
// the same focus, including the turn-prefix request which has no customInstructions argument.
export function focusCompactionContext<T extends {messages:any[]}>(context:T,focus:string):T{
 const messages=context.messages.map(message=>message.role==='user'?{...message,content:typeof message.content==='string'?message.content+'\n\n'+focus:[...message.content,{type:'text',text:focus}]}:message);
 return {...context,messages};
}

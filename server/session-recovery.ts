import {readFile} from 'node:fs/promises';
import type {SessionManager} from '@earendil-works/pi-coding-agent';
import {modelContext} from './model-context.js';

export const sideEffectTool=(name:string)=>['set_document_profile','save_research_claims','run_cleaning_script','commit_cleaning_result','process_documents','run_analysis','run_financial_model','save_research_report','request_database_operation'].includes(name);
export function operationKey(name:string,args:Record<string,any>){
 const canonical=(v:any):any=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().filter(k=>k!=='project_id').map(k=>[k,canonical(v[k])])):v;
 return JSON.stringify([name,canonical(args)]);
}
// Restore receipts, never execute old tool calls. Missing side-effect receipts
// are retained as uncertain so any retry requires fresh explicit authorization.
export async function repairInterruptedTools(manager:SessionManager,auditPath:string){
 let records:any[]=[];
 try{records=(await readFile(auditPath,'utf8')).split('\n').filter(Boolean).flatMap(line=>{try{return [JSON.parse(line)];}catch{return [];}});}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
 const calls=new Map<string,any>(),results=new Map<string,any>(),uncertain=new Map<string,{name:string;args:any}>();
 const recovered=new Set(manager.getBranch().flatMap((entry:any)=>entry.type==='custom_message'&&entry.customType==='recovered_tool_receipt'?[entry.details?.toolCallId]:[]));
 for(const message of manager.buildSessionContext().messages){
  if(message.role==='assistant')for(const block of message.content)if(block.type==='toolCall')calls.set(block.id,block);
  if(message.role==='toolResult')results.set(message.toolCallId,message);
 }
 for(const [id,call] of calls){
  const saved=results.get(id);
  if(saved&&!saved.isError)continue;
  const result=records.findLast(r=>r.type==='tool_result'&&r.data.toolCallId===id)?.data.result;
  const failure=records.findLast(r=>r.type==='tool_error'&&r.data.toolCallId===id)?.data.message;
  const started=records.some(r=>r.type==='tool_request'&&r.data.toolCallId===id);
  if(started&&!result&&sideEffectTool(call.name))uncertain.set(operationKey(call.name,call.arguments),{name:call.name,args:call.arguments});
  const receipt=result?modelContext(call.name,result):{status:'interrupted',message:started?'服务中断，此操作的最终结果尚未确认。先读取数据库检查点或成果核对；重复写入需要重新授权。':'服务在此工具开始执行前中断，可继续执行。',error:failure};
  if(saved){
   // Pi may already have written an aborted placeholder. Keep its pair valid;
   // append the actual durable receipt as additional recovery evidence.
   if(result&&!recovered.has(id))manager.appendCustomMessageEntry('recovered_tool_receipt',JSON.stringify({toolCallId:id,toolName:call.name,result:receipt}),false,{toolCallId:id});
  }else manager.appendMessage({role:'toolResult',toolCallId:id,toolName:call.name,content:[{type:'text',text:JSON.stringify(receipt)}],isError:!result,timestamp:Date.now()});
 }
 return uncertain;
}

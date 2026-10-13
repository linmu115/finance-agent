// Persistent 18-turn gate. Each tick makes at most one new participant submission.
// Two server runs may overlap; all progress survives evaluator/app-server exits.
import {randomUUID} from 'node:crypto';
import {canonical,digest} from './study-f14.mjs';
export {canonical,digest};
export const terminal=new Set(['completed','failed','cancelled']);
export function planGate(config,schedule,study,version='F2.0.2'){
 if(schedule.length!==18||config.repeats!==2||config.model!=='gpt-6-luna'||config.provider!=='cpa-local')throw Error('Unexpected approved gate');
 const batchUUID=randomUUID(),short=batchUUID.replaceAll('-','');
 const runs=schedule.map(row=>{
  const task=config.tasks.find(t=>t.id===row.task);if(!task)throw Error('Unknown task');
  return {label:({original_pi:'G',prepared:'P',financial:'F'}[row.arm])+row.repeat+'_'+row.task,taskId:row.task,profile:row.arm,repeat:row.repeat,projectId:task.projectId,split:'v3_gate',taskType:task.type,ordinal:row.ordinal,isolationKey:`${version.replaceAll('.','')}_gate_${short}_${row.task}_${row.arm}_${row.repeat}`,status:'planned',attempt:1,usage:null};
 });
 if(new Set(runs.map(r=>r.label)).size!==18)throw Error('Duplicate gate labels');
 return {schema:'blind-eval-v3-gate-1',version,study,batchUUID,config,plannedOrder:runs.map(r=>({...r})),runs,freeze:null,stopReason:null,judge:{model:'gpt-6-astra',reasoningEffort:'high'},createdAt:new Date().toISOString()};
}
export function requestFor(s,r){return {content:s.config.tasks.find(t=>t.id===r.taskId).prompt,documentIds:[],evaluation:{profile:r.profile,analysis_only:true,isolation_key:r.isolationKey,budget_group_id:r.isolationKey,budget:s.config.evaluationLimits}};}
export function classify(run){
 if(run.status==='completed')return null;
 if(run.status==='cancelled')return 'cancelled';
 const message=String(run.error||'');
 if(/TLS|ECONNRESET|ECONNREFUSED|socket hang up|stream.*(closed|interrupt)|connection.*(closed|reset)|fetch failed|server_overloaded|\b50[0234]\b/i.test(message))return 'infrastructure';
 if(/render_answer|answer_binding|Decimal|ConversionSyntax|交付契约|回答绑定/.test(message))return 'product';
 if(/budget|预算|额度/.test(message))return 'resource_limit';
 return 'unclassified';
}
async function observe(s,r,io,run){
 const chat=await io.api('/api/conversations/'+r.conversationId);
 const expected=requestFor(s,r),message=chat.messages.find(m=>m.id===run.request?.userMessageId);
 await io.capture(r,run,chat); // Preserve raw evidence before validating identity.
 if(run.projectId!==r.projectId||run.conversationId!==r.conversationId||canonical(run.request?.evaluation)!==canonical(expected.evaluation)||canonical(run.request?.documentIds)!=='[]'||message?.content!==expected.content||chat.evaluationIsolationKey!==r.isolationKey)throw Error('evaluation_request_or_isolation_drift');
 Object.assign(r,{runId:run.id,status:run.status,usage:run.usage??null,error:run.error??null,finishedAt:run.finishedAt??null,failureClass:terminal.has(run.status)?classify(run):null});
 if(run.status==='cancelled')s.stopReason='participant_cancelled';
 await io.save(s);
}
export async function tick(s,io,{submit=false}={}){
 // Recover a POST whose response was lost by finding its existing server run.
 // An unresolved POST is never automatically repeated.
 for(const r of s.runs.filter(r=>r.status==='posting')){
  const chat=await io.api('/api/conversations/'+r.conversationId);
  const ids=[...new Set([chat.activeRunId,...chat.messages.map(m=>m.runId)].filter(Boolean))];
  const matches=[];
  for(const id of ids){const run=await io.api('/api/runs/'+id);if(run.request?.evaluation?.isolation_key===r.isolationKey)matches.push(run);}
  if(matches.length!==1)return {status:'uncertain_post',label:r.label,action:'inspect existing conversation/run; no POST'};
  await observe(s,r,io,matches[0]);
 }
 if(s.runs.some(r=>r.status==='creating'))return {status:'uncertain_conversation',action:'inspect original project conversation list before linking; no POST'};
 for(const r of s.runs.filter(r=>['running','queued'].includes(r.status)))await observe(s,r,io,await io.api('/api/runs/'+r.runId));
 if(s.runs.every(r=>terminal.has(r.status)))return {status:'complete'};
 if(s.stopReason)return {status:'stopped',reason:s.stopReason};
 if(!submit||io.stopped())return {status:'observed',active:s.runs.filter(r=>['running','queued'].includes(r.status)).length};
 if(!s.freeze)throw Error('Gate must be frozen before submission');
 const active=s.runs.filter(r=>['running','queued'].includes(r.status));
 const row=s.runs.find(r=>['planned','ready'].includes(r.status));
 if(row&&row.ordinal>1&&s.firstTurnInspectionRequired&&!s.firstTurnInspection?.passed)return {status:terminal.has(s.runs[0].status)?'first_turn_inspection_required':'waiting'};
 if(row&&s.firstFinancialInspectionRequired&&!s.firstFinancialInspection?.passed){
  const financial=s.runs.find(r=>r.profile==='financial');
  if(row.ordinal>financial.ordinal)return {status:active.length===0?'financial_inspection_required':'waiting'};
 }
 if(!row||active.length>=2||active.some(r=>r.profile===row.profile))return {status:'waiting'};
 await io.verify(s);
 if(io.stopped())return {status:'draining'};
 if(!row.conversationId){
  row.status='creating';row.conversationRequestedAt=new Date().toISOString();await io.save(s);
  try{row.conversationId=(await io.api(`/api/projects/${row.projectId}/conversations`,{})).id;row.status='ready';await io.save(s);}
  catch(e){if(e.code==='NOT_DISPATCHED'){row.status='planned';await io.save(s);return {status:'draining'};}throw e;}
 }
 if(io.stopped())return {status:'draining'};
 row.status='posting';row.requestedAt=new Date().toISOString();row.requestBody=requestFor(s,row);await io.save(s);
 try{
  const response=await io.api(`/api/conversations/${row.conversationId}/messages`,row.requestBody);
  Object.assign(row,response,{status:'running'});await io.save(s);
  return {status:'submitted',label:row.label,runId:row.runId};
 }catch(e){
  if(e.code==='NOT_DISPATCHED'){row.status='ready';await io.save(s);return {status:'draining'};}
  row.postError=String(e);await io.save(s);return {status:'uncertain_post',label:row.label};
 }
}

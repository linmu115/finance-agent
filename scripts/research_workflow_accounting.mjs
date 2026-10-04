/** Read-only observer accounting. Snapshots of one budget group are cumulative, never additive. */
import {setTimeout as delay} from 'node:timers/promises';

const FIELDS=['model_calls','settled_calls','input_tokens','output_tokens','total_tokens','failed_calls','unknown_usage_calls'];
const TERMINAL=new Set(['completed','failed','cancelled']);
const zero=()=>Object.fromEntries(FIELDS.map(key=>[key,0]));
const usageValid=usage=>usage&&FIELDS.every(key=>Number.isSafeInteger(usage[key])&&usage[key]>=0);
const add=(a,b)=>Object.fromEntries(FIELDS.map(key=>[key,a[key]+b[key]]));
const maximum=rows=>Object.fromEntries(FIELDS.map(key=>[key,Math.max(0,...rows.map(row=>row[key]))]));
const dominates=(a,b)=>FIELDS.every(key=>a[key]>=b[key]);

export async function reconcileContinuationAccounting({before,report,api,audit,pause=delay}){
 const prior=before.continuation.prior_usage,errors=[],observations=[],snapshots=[],rawEvents=[];
 const attempts=report.stage_attempts||[],stages=report.stages||[];
 const runIds=[...new Set([...stages.map(stage=>stage.run?.id),...attempts.map(attempt=>attempt.run_id),report.last_observed_run?.id,report.active_run?.id,report.active_stage?.run_id].filter(Boolean))];
 const target=report.active_stage?.run_id||report.active_run?.id||attempts.at(-1)?.run_id||report.last_observed_run?.id||stages.at(-1)?.run?.id;
 const unacknowledged=attempts.filter(attempt=>!attempt.run_id);
 const attempted=runIds.length>0||attempts.length>0;
 function accept(snapshot,source,runId,terminal){
  if(!snapshot)return;
  if(snapshot.budget_group_id!==report.budget_group_id||!usageValid(snapshot.usage)){
   errors.push({source,run_id:runId,error:'invalid_or_different_budget_snapshot'});return;
  }
  snapshots.push({source,run_id:runId,terminal,usage:snapshot.usage,elapsed_seconds:snapshot.elapsed_seconds,
   reserved:snapshot.reserved,in_flight:snapshot.in_flight,unknown_output_charge:snapshot.unknown_output_charge});
 }
 for(const stage of stages)accept(stage.run?.evaluation,'saved_stage',stage.run?.id,TERMINAL.has(stage.run?.status));
 for(const run of [report.last_observed_run,report.active_run])if(run)accept(run.evaluation,'last_observed_run',run.id,TERMINAL.has(run.status));
 if(target){
  // A cancellation can return before a pending usage callback settles. Read only; never resume work.
  for(let index=0;index<3;index++){
   try{
    const run=await api('/api/runs/'+target);
    if(run.id!==target)throw Error('run_identity_mismatch');
    observations.push({source:'run_api',run_id:target,status:run.status,attempt:index+1});
    accept(run.evaluation,'run_api',target,TERMINAL.has(run.status));
    if(TERMINAL.has(run.status))break;
   }catch(error){errors.push({source:'run_api',run_id:target,error:String(error.message||error)});break;}
   if(index<2)await pause(250);
  }
 }
 const reads=await Promise.allSettled(runIds.map(async runId=>({runId,events:await audit(runId)})));
 for(let index=0;index<reads.length;index++){
  const read=reads[index],runId=runIds[index];
  if(read.status==='rejected'){errors.push({source:'audit',run_id:runId,error:String(read.reason?.message||read.reason)});continue;}
  const events=read.value.events;
  observations.push({source:'audit',run_id:runId,event_count:events.length});
  for(const event of events){
   if(event.runId&&event.runId!==runId){errors.push({source:'audit',run_id:runId,error:'audit_run_identity_mismatch'});continue;}
   if(event.type==='evaluation_budget')accept(event.data,'audit:'+event.data?.action,runId,event.data?.action==='run_finished');
   if(event.type==='model_usage')rawEvents.push({...event,runId});
  }
 }
 // Raw request records are independent lower-bound evidence if a final group snapshot is absent.
 // They do not prove that every request was observed, and may not replace a terminal snapshot.
 const seen=new Set(),raw=zero();
 for(const event of rawEvents){
  const data=event.data||{},id=data.requestId;
  if(!id){errors.push({source:'model_usage',run_id:event.runId,error:'missing_request_id'});continue;}
  if(seen.has(id))continue;seen.add(id);raw.model_calls++;raw.settled_calls++;
  const values=[data.usage?.input,data.usage?.cacheRead,data.usage?.cacheWrite,data.usage?.output];
  const known=data.usageKnown===true&&values.some(value=>value!==undefined)&&values.every(value=>value===undefined||(Number.isSafeInteger(value)&&value>=0));
  if(known){raw.input_tokens+=(data.usage.input||0)+(data.usage.cacheRead||0)+(data.usage.cacheWrite||0);raw.output_tokens+=data.usage.output||0;}
  else raw.unknown_usage_calls++;
  if(data.error||['error','aborted','length'].includes(data.stopReason))raw.failed_calls++;
 }
 raw.total_tokens=raw.input_tokens+raw.output_tokens;
 const known=maximum([...snapshots.map(snapshot=>snapshot.usage),raw]);
 const terminal=snapshots.filter(snapshot=>snapshot.run_id===target&&snapshot.terminal)
  .sort((a,b)=>(b.source==='run_api')-(a.source==='run_api')||(b.elapsed_seconds||0)-(a.elapsed_seconds||0));
 const settled=terminal.find(snapshot=>dominates(snapshot.usage,known)&&snapshot.usage.model_calls===snapshot.usage.settled_calls&&
  snapshot.reserved?.model_calls===0&&Array.isArray(snapshot.in_flight)&&snapshot.in_flight.length===0);
 let status,complete=false,current=null,elapsed=null;
 if(!attempted){status='not_started';complete=true;current=zero();elapsed=0;}
 else if(unacknowledged.length){status='unacknowledged_submission';}
 else if(settled){
  current=settled.usage;elapsed=settled.elapsed_seconds;
  status=current.unknown_usage_calls?'unknown_model_usage':'complete';complete=status==='complete';
 }else status=terminal.length?'incomplete_or_conflicting_terminal_evidence':snapshots.length||rawEvents.length?'partial':'unavailable';
 const knownElapsed=Math.max(0,...snapshots.map(snapshot=>Number.isFinite(snapshot.elapsed_seconds)?snapshot.elapsed_seconds:0));
 return {
  schema_version:2,accounting_status:status,usage_complete:complete,original_limits:before.continuation.original_budget,
  prior_usage:prior,continuation_usage:current,combined_usage:complete?add(prior,current):null,
  continuation_known_usage_lower_bound:known,combined_known_usage_lower_bound:add(prior,known),
  combined_active_elapsed_seconds:complete&&Number.isFinite(elapsed)?before.continuation.prior_elapsed_seconds+elapsed:null,
  combined_known_active_elapsed_seconds_lower_bound:before.continuation.prior_elapsed_seconds+knownElapsed,
  waiting_between_versions_charged:false,target_run_id:target||null,unacknowledged_submissions:unacknowledged,
  evidence:{snapshots,raw_model_usage_lower_bound:raw,raw_request_ids:[...seen],observations,errors},
  note:complete?'Previous failed spend is included. Group snapshots are cumulative and were not summed across stages.':
   'Final continuation spend is not fully established. Null is unknown, not zero; known lower bounds preserve observed and prior spend. Do not allocate another continuation from these incomplete totals.'
 };
}

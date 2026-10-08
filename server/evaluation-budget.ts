import {randomUUID} from 'node:crypto';

export interface EvaluationLimits {
 max_model_calls:number; max_input_tokens:number; max_output_tokens:number; max_total_tokens:number; max_wall_seconds:number;
}
export interface EvaluationOptions {profile:'financial'|'generic'|'prepared';budget_group_id:string;budget:EvaluationLimits;isolation_key?:string;analysis_only?:boolean}
export interface BudgetUsage {input?:number;output?:number;cacheRead?:number;cacheWrite?:number}
export interface BudgetTicket {id:string;run_id:string;max_output_tokens:number;created_at:string}
export interface BudgetSnapshot extends EvaluationOptions {
 started_at:string;deadline_at:string;elapsed_seconds:number;input_limit_enforcement:'post_usage_soft_cap';
 usage:{model_calls:number;settled_calls:number;input_tokens:number;output_tokens:number;total_tokens:number;failed_calls:number;unknown_usage_calls:number};
 reserved:{model_calls:number;output_tokens:number};unknown_output_charge:number;denied_calls:number;
 in_flight:BudgetTicket[];overage:{input_tokens:number;output_tokens:number;total_tokens:number};
 stopped_reason:string|null;
}
type Clock={now?:()=>number;scheduleDeadline?:boolean};
const keys=['max_model_calls','max_input_tokens','max_output_tokens','max_total_tokens','max_wall_seconds'] as const;
const clone=<T>(value:T):T=>structuredClone(value);
const failure=(code:string,status=400)=>Object.assign(new Error(code),{code,status});

export function normalizeEvaluation(value:unknown):EvaluationOptions|undefined {
 if(value===undefined)return undefined;
 if(!value||typeof value!=='object'||Array.isArray(value))throw failure('invalid_evaluation');
 const raw=value as Record<string,unknown>;
 if(Object.keys(raw).some(key=>!['profile','budget_group_id','budget','isolation_key','analysis_only'].includes(key))||!['financial','generic','prepared'].includes(String(raw.profile))||
    typeof raw.budget_group_id!=='string'||!/^[-A-Za-z0-9_]{1,120}$/.test(raw.budget_group_id)||
    !raw.budget||typeof raw.budget!=='object'||Array.isArray(raw.budget))throw failure('invalid_evaluation');
 if(raw.isolation_key!==undefined&&(typeof raw.isolation_key!=='string'||!/^[-A-Za-z0-9_]{1,120}$/.test(raw.isolation_key)))throw failure('invalid_evaluation_isolation_key');
 if(raw.analysis_only!==undefined&&typeof raw.analysis_only!=='boolean')throw failure('invalid_evaluation_analysis_only');
 const budget=raw.budget as Record<string,unknown>;
 if(Object.keys(budget).some(key=>!keys.includes(key as typeof keys[number])))throw failure('invalid_evaluation_budget');
 for(const key of keys)if(typeof budget[key]!=='number'||!Number.isFinite(budget[key])||Number(budget[key])<0||
    (key!=='max_wall_seconds'&&!Number.isSafeInteger(budget[key]))||Number(budget[key])>Number.MAX_SAFE_INTEGER)throw failure('invalid_evaluation_budget');
 return {...(raw.isolation_key!==undefined?{isolation_key:raw.isolation_key as string}:{}),...(raw.analysis_only!==undefined?{analysis_only:raw.analysis_only as boolean}:{}),profile:raw.profile as EvaluationOptions['profile'],budget_group_id:raw.budget_group_id,
         budget:Object.fromEntries(keys.map(key=>[key,budget[key]])) as unknown as EvaluationLimits};
}

// Budget groups may span independent chains; artifact isolation is stored on each run request.
const budgetOptions=(options:EvaluationOptions)=>{const {isolation_key,analysis_only,...budget}=normalizeEvaluation(options)!;return budget;};

export class EvaluationBudgetExceeded extends Error {
 readonly code='evaluation_budget_exceeded'; readonly status=429;
 constructor(readonly limit:string,readonly snapshot:BudgetSnapshot){super(`evaluation_budget_exceeded:${limit}`);}
}

/** A single arm's shared ledger. Input is measured after provider usage arrives. */
export class EvaluationBudget {
 readonly options:EvaluationOptions;
 private now:()=>number;
 private started:number;
 private deadline:number;
 private timer?:ReturnType<typeof setTimeout>;
 private pending=new Map<string,BudgetTicket>();
 private settled=new Set<string>();
 private controllers=new Map<string,AbortController>();
 private usage={model_calls:0,settled_calls:0,input_tokens:0,output_tokens:0,total_tokens:0,failed_calls:0,unknown_usage_calls:0};
 private unknownOutput=0;
 private denied=0;
 private stopped:string|null=null;
 constructor(options:EvaluationOptions,clock:Clock={},restored?:BudgetSnapshot){
  this.options=budgetOptions(options);this.now=clock.now||Date.now;
  this.started=restored?Date.parse(restored.started_at):this.now();
  if(!Number.isFinite(this.started))throw failure('invalid_evaluation_snapshot');
  this.deadline=this.started+this.options.budget.max_wall_seconds*1000;
  if(restored){
   if(JSON.stringify(normalizeEvaluation({profile:restored.profile,budget_group_id:restored.budget_group_id,budget:restored.budget}))!==JSON.stringify(this.options))throw failure('evaluation_budget_group_conflict',409);
   this.usage=clone(restored.usage);this.unknownOutput=restored.unknown_output_charge;this.denied=restored.denied_calls;this.stopped=restored.stopped_reason;
   // A restarted server cannot recover a live provider call. Preserve its
   // attempt and worst-case output debit instead of resetting the shared pot.
   for(const ticket of restored.in_flight){this.unknownOutput+=ticket.max_output_tokens;this.usage.unknown_usage_calls++;this.usage.failed_calls++;this.usage.settled_calls++;}
  }
  if(clock.scheduleDeadline!==false){
   const schedule=()=>{const remaining=this.deadline-this.now();
    if(remaining<=0){this.stop('max_wall_seconds');return;}
    this.timer=setTimeout(schedule,Math.min(remaining,2_147_483_647));this.timer.unref?.();};schedule();
  }
 }
 attach(runId:string,controller:AbortController):()=>void {
  this.controllers.set(runId,controller);
  if(this.now()>=this.deadline)this.stop('max_wall_seconds');
  if(this.stopped)controller.abort(new EvaluationBudgetExceeded(this.stopped,this.snapshot()));
  return ()=>{if(this.controllers.get(runId)===controller)this.controllers.delete(runId);};
 }
 private stop(reason:string){
  this.stopped ||= reason;
  const error=new EvaluationBudgetExceeded(this.stopped,this.snapshot());
  for(const controller of this.controllers.values())if(!controller.signal.aborted)controller.abort(error);
 }
 private reservedOutput(){return [...this.pending.values()].reduce((sum,ticket)=>sum+ticket.max_output_tokens,0);}
 private deny(limit:string):never{this.denied++;throw new EvaluationBudgetExceeded(limit,this.snapshot());}
 reserve(runId:string,maxOutputTokens:number,requestId:string=randomUUID()):BudgetTicket {
  if(!Number.isSafeInteger(maxOutputTokens)||maxOutputTokens<1)throw failure('invalid_model_output_reservation');
  if(this.now()>=this.deadline)this.stop('max_wall_seconds');
  if(this.stopped)return this.deny(this.stopped);
  if(this.pending.has(requestId)||this.settled.has(requestId))throw failure('duplicate_budget_request');
  const limits=this.options.budget;
  if(this.usage.model_calls>=limits.max_model_calls)return this.deny('max_model_calls');
  if(this.usage.input_tokens>=limits.max_input_tokens)return this.deny('max_input_tokens');
  const reserved=this.reservedOutput(),chargedOutput=this.usage.output_tokens+this.unknownOutput;
  const outputRemaining=limits.max_output_tokens-chargedOutput-reserved;
  const totalRemaining=limits.max_total_tokens-this.usage.input_tokens-chargedOutput-reserved;
  if(outputRemaining<1)return this.deny('max_output_tokens');
  if(totalRemaining<1)return this.deny('max_total_tokens');
  const ticket={id:requestId,run_id:runId,max_output_tokens:Math.min(maxOutputTokens,outputRemaining,totalRemaining),created_at:new Date(this.now()).toISOString()};
  this.pending.set(requestId,ticket);this.usage.model_calls++;
  return clone(ticket);
 }
 settle(ticket:BudgetTicket,usage?:BudgetUsage,details:{failed?:boolean}={}):BudgetSnapshot {
  const reservation=this.pending.get(ticket.id);
  if(!reservation)throw failure(this.settled.has(ticket.id)?'evaluation_budget_already_settled':'evaluation_budget_unknown_reservation');
  const values=[usage?.input,usage?.cacheRead,usage?.cacheWrite,usage?.output];
  const known=!!usage&&values.some(value=>value!==undefined)&&values.every(value=>value===undefined||(Number.isSafeInteger(value)&&value>=0));
  this.pending.delete(ticket.id);this.settled.add(ticket.id);this.usage.settled_calls++;
  if(details.failed)this.usage.failed_calls++;
  if(known){
   this.usage.input_tokens+=(usage!.input||0)+(usage!.cacheRead||0)+(usage!.cacheWrite||0);
   this.usage.output_tokens+=usage!.output||0;
  }else{
   this.usage.unknown_usage_calls++;this.unknownOutput+=reservation.max_output_tokens;
  }
  this.usage.total_tokens=this.usage.input_tokens+this.usage.output_tokens;
  if(this.now()>=this.deadline)this.stop('max_wall_seconds');
  const limits=this.options.budget;
  if(this.usage.input_tokens>limits.max_input_tokens)this.stop('max_input_tokens');
  else if(this.usage.output_tokens>limits.max_output_tokens)this.stop('max_output_tokens');
  else if(this.usage.total_tokens>limits.max_total_tokens)this.stop('max_total_tokens');
  return this.snapshot();
 }
 snapshot():BudgetSnapshot {
  const limits=this.options.budget;
  return {...clone(this.options),started_at:new Date(this.started).toISOString(),deadline_at:new Date(this.deadline).toISOString(),
   elapsed_seconds:Math.max(0,(this.now()-this.started)/1000),input_limit_enforcement:'post_usage_soft_cap',usage:clone(this.usage),
   reserved:{model_calls:this.pending.size,output_tokens:this.reservedOutput()},unknown_output_charge:this.unknownOutput,denied_calls:this.denied,
   in_flight:[...this.pending.values()].map(clone),overage:{input_tokens:Math.max(0,this.usage.input_tokens-limits.max_input_tokens),
    output_tokens:Math.max(0,this.usage.output_tokens-limits.max_output_tokens),total_tokens:Math.max(0,this.usage.total_tokens-limits.max_total_tokens)},stopped_reason:this.stopped};
 }
 dispose(){if(this.timer)clearTimeout(this.timer);this.controllers.clear();}
}

export class EvaluationBudgets {
 private groups=new Map<string,EvaluationBudget>();
 constructor(private clock:Clock={}){}
 acquire(projectId:string,options:EvaluationOptions,restored?:BudgetSnapshot):EvaluationBudget {
  const normalized=budgetOptions(options),key=JSON.stringify([projectId,normalized.budget_group_id]);
  let group=this.groups.get(key);
  if(group){if(JSON.stringify(group.options)!==JSON.stringify(normalized))throw failure('evaluation_budget_group_conflict',409);return group;}
  group=new EvaluationBudget(normalized,this.clock,restored);this.groups.set(key,group);return group;
 }
 dispose(){for(const group of this.groups.values())group.dispose();this.groups.clear();}
}

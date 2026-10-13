// Evaluator scheduler. Transport and snapshots are injected for offline tests.
import {createHash,randomUUID} from 'node:crypto';
export const canonical=x=>JSON.stringify(x,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
export const digest=x=>createHash('sha256').update(typeof x==='string'||Buffer.isBuffer(x)?x:canonical(x)).digest('hex');
export const terminal=new Set(['completed','failed','cancelled','blocked_dependency']);
export function plan(config,name){
 if(!/^blind-eval-[\w.-]+$/.test(name)||config.repeats!==2||config.model!=='gpt-6-luna'||config.provider!=='cpa-local'||config.analysisOnly!==true)throw Error('Unexpected approved study configuration');
 const tasks=new Map(config.tasks.map(t=>[t.id,t]));
 const approved=new Set(['X1','X3','X4','X5','X6','X7','H1','H2']);
 if(!tasks.size||[...tasks.keys()].some(id=>!approved.has(id)))throw Error('F1.4 material block must contain approved remaining tasks');
 const rows=[],batchUUID=randomUUID();
 for(const phase of Object.keys(config.phases).map(Number).sort((a,b)=>a-b))for(const repeat of [1,2]){
  const blocks=config.phases[String(phase)].blocks;
  const ids=(repeat===1?blocks:[...blocks].reverse()).flat();
  for(const id of ids){
   const task=tasks.get(id);if(!task||task.phase!==phase)throw Error('Phase task mismatch');
   const index=task.scheduleIndex??config.tasks.findIndex(t=>t.id===id);
   const profiles=(index+repeat)%2?['prepared','financial']:['financial','prepared'];
   for(const profile of profiles){
    const parent=task.continuationOf?rows.find(r=>r.taskId===task.continuationOf&&r.repeat===repeat&&r.profile===profile):null;
    if(task.continuationOf&&(!parent||parent.projectId!==task.projectId||parent.phase!==phase))throw Error('Broken cross-task chain');
    const label=`${profile==='prepared'?'P':'F'}${repeat}_${id}`;
    const isolationKey=parent?.isolationKey??`F14_${batchUUID.replaceAll('-','')}_${label}`;
    rows.push({label,taskId:id,profile,repeat,phase,projectId:task.projectId,split:task.split,taskType:task.type,parent:parent?.label??null,isolationKey});
   }
  }
 }
 const turns=config.tasks.length*4, chains=config.tasks.filter(t=>!t.continuationOf).length*4;
 if(rows.length!==turns||new Set(rows.map(r=>r.label)).size!==turns||new Set(rows.map(r=>r.isolationKey)).size!==chains)throw Error('Incomplete material-block plan');
 return {schema:'blind-eval-f1-v1',study:name,batchUUID,config,plannedOrder:rows,runs:[],phaseFreezes:{},preparation:{newIngestion:false,ledgers:config.preparationLedgers,providerBilledCost:null},judge:{model:'gpt-6-astra',reasoningEffort:'high'},excluded:[{task:'X2',status:'未执行',reason:'美的未入库；本轮明确排除'}]};
}
export function requestFor(state,row){
 return {content:state.config.tasks.find(t=>t.id===row.taskId).prompt,documentIds:[],evaluation:{profile:row.profile,isolation_key:row.isolationKey,budget_group_id:'B_'+state.batchUUID.replaceAll('-','')+'_'+row.label,budget:state.config.evaluationLimits,analysis_only:true}};
}
export async function step(state,phase,io){
 // One invocation does one POST or one poll; no automatic paid retry.
 if(state.runs.some(r=>r.status==='cancelled')||await io.isStopped?.())return {status:'batch_stopped',reason:'Cancelled run or operator stop; no next turn may be submitted'};
 const pending=state.runs.find(r=>!terminal.has(r.status));
 if(pending){
  if(pending.status==='posting')return {status:'uncertain_post',label:pending.label,action:'reconcile original conversation/run; never resubmit'};
  const run=await io.api('/api/runs/'+pending.runId);
  const chat=await io.api('/api/conversations/'+pending.conversationId);
  await io.capture(pending,run,chat);
  const answers=chat.messages.filter(m=>m.role==='assistant'&&m.runId===pending.runId);
  Object.assign(pending,{status:run.status,usage:run.usage??null,error:run.error??null,completedAt:run.finishedAt??null,hasDeliveredAnswer:answers.some(m=>m.content?.trim()&&m.artifacts?.length)});
  await io.save(state);return {status:pending.status,label:pending.label};
 }
 const row=state.plannedOrder.find(r=>r.phase===phase&&!state.runs.some(a=>a.label===r.label));
 if(!row)return {status:'phase_complete',phase};
 if(!state.freeze||!state.phaseFreezes[String(phase)])throw Error('F1 code and phase material freeze required');
 const parent=row.parent?state.runs.find(r=>r.label===row.parent):null;
 if(row.parent&&(parent?.status!=='completed'||!parent.hasDeliveredAnswer)){
  state.runs.push({...row,status:'blocked_dependency',reason:'Parent has no completed run',usage:null,submitted:false});
  await io.save(state);return {status:'blocked_dependency',label:row.label};
 }
 await io.verify(state,phase);
 if(await io.isStopped?.())return {status:'batch_stopped',reason:'Operator stop before submission'};
 const conversationId=parent?.conversationId??(await io.api(`/api/projects/${row.projectId}/conversations`,{})).id;
 const record={...row,conversationId,status:'posting',attempt:1,requestedAt:new Date().toISOString(),usage:null};
 state.runs.push(record);await io.save(state);
 const response=await io.api(`/api/conversations/${conversationId}/messages`,requestFor(state,row));
 Object.assign(record,response,{status:'running'});await io.save(state);
 return {status:'running',label:record.label,runId:record.runId};
}
export function reconcile(state,label,run,chat){
 const r=state.runs.find(r=>r.label===label);
 if(!r||r.status!=='posting'||run.conversationId!==r.conversationId||run.projectId!==r.projectId||chat.id!==r.conversationId||chat.projectId!==r.projectId||chat.evaluationIsolationKey!==r.isolationKey)throw Error('Reconciliation identity mismatch');
 const request=run.request;
 const userMessage=chat.messages.find(m=>m.id===request?.userMessageId&&m.role==='user');
 if(canonical(request?.evaluation)!==canonical(requestFor(state,r).evaluation)||userMessage?.content!==requestFor(state,r).content||canonical(request?.documentIds)!==canonical([]))throw Error('Reconciliation request mismatch');
 if(!chat.messages.some(m=>m.runId===run.id))throw Error('Run absent from original conversation');
 Object.assign(r,{runId:run.id,status:run.status,usage:run.usage??null,error:run.error??null,hasDeliveredAnswer:chat.messages.some(m=>m.role==='assistant'&&m.runId===run.id&&m.content?.trim()&&m.artifacts?.length)});
}

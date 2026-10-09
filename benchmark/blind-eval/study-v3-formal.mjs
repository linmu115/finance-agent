// Persistent formal scheduler. No network except the injected, cancellation-aware IO.
import {canonical,digest} from './study-f14.mjs';
import {classify} from './study-v3-gate.mjs';
export {canonical,digest};
export const terminal=new Set(['completed','failed','cancelled','blocked_dependency']);
export const accountError=message=>/\b(?:401|403|429)\b|unauthori[sz]ed|authentication|invalid[_ -]?(?:api[_ -]?)?key|insufficient[_ -]?quota|quota[_ -]?(?:exceeded|exhausted)|usage[_ -]?limit|credit.*(?:exhaust|insufficient)|额度|认证失败/i.test(String(message||''));
export function requestFor(s,r){return {content:s.config.tasks.find(t=>t.id===r.taskId).prompt,documentIds:[],evaluation:{profile:r.profile,analysis_only:true,isolation_key:r.isolationKey,budget_group_id:r.isolationKey,budget:s.config.evaluationLimits}};}
async function observe(s,r,io,run){
 const chat=await io.api('/api/conversations/'+r.conversationId),expected=requestFor(s,r);
 await io.capture(r,run,chat);
 const message=chat.messages.find(m=>m.id===run.request?.userMessageId);
 if(run.projectId!==r.projectId||run.conversationId!==r.conversationId||canonical(run.request?.evaluation)!==canonical(expected.evaluation)||canonical(run.request?.documentIds)!=='[]'||message?.content!==expected.content||chat.evaluationIsolationKey!==r.isolationKey)throw Error('evaluation_request_or_isolation_drift');
 Object.assign(r,{runId:run.id,status:run.status,usage:run.usage??null,error:run.error??null,finishedAt:run.finishedAt??null,failureClass:terminal.has(run.status)?classify(run):null});
 if(accountError(run.error)){r.failureClass='authentication_or_quota';s.stopReason='authentication_or_quota';}
 if(run.status==='cancelled')s.stopReason='participant_cancelled';
 if(terminal.has(r.status)){
  r.usableParent=r.status==='completed'||chat.messages.some(m=>m.role==='assistant'&&m.runId===r.runId&&m.content?.trim()&&m.artifacts?.length);
  if(!r.usableParent)for(const child of s.runs.filter(x=>x.chainId===r.chainId&&x.ordinal>r.ordinal&&!terminal.has(x.status))){child.status='blocked_dependency';child.failureClass='parent_unavailable';child.parentLabel=r.label;}
 }
 await io.save(s);
}
export async function tick(s,io,{submit=false}={}){
 for(const r of s.runs.filter(r=>r.status==='posting')){
  const chat=await io.api('/api/conversations/'+r.conversationId),matches=[];
  const ids=[...new Set([chat.activeRunId,...chat.messages.map(m=>m.runId)].filter(Boolean))];
  for(const id of ids){const run=await io.api('/api/runs/'+id);if(run.request?.evaluation?.isolation_key===r.isolationKey&&run.request?.content===requestFor(s,r).content&&!s.runs.some(x=>x!==r&&x.runId===id))matches.push(run);}
  if(matches.length!==1)return {status:'uncertain_post',label:r.label};
  await observe(s,r,io,matches[0]);
 }
 if(s.runs.some(r=>r.status==='creating'))return {status:'uncertain_conversation'};
 for(const r of s.runs.filter(r=>['running','queued'].includes(r.status)))await observe(s,r,io,await io.api('/api/runs/'+r.runId));
 if(s.stopReason)return {status:'stopped',reason:s.stopReason};
 if(s.runs.every(r=>terminal.has(r.status)))return {status:'complete'};
 if(!submit||io.stopped())return {status:'observed'};
 if(!s.runtimeFreeze)throw Error('Runtime freeze required before participant submission');
 const eligible=s.runs.filter(r=>s.projectFreezes[r.projectId]);
 if(eligible.every(r=>terminal.has(r.status)))return {status:'ready_blocks_complete',pending:s.runs.filter(r=>!terminal.has(r.status)).length};
 const first=eligible[0];
 if(s.requiresFirstTurnInspection&&first.status!=='planned'&&!s.firstTurnInspection?.passed)return {status:terminal.has(first.status)?'first_turn_inspection_required':'waiting'};
 const chains=[...new Set(eligible.map(r=>r.chainId))].map(id=>eligible.filter(r=>r.chainId===id));
 const activeChains=chains.filter(c=>c.some(r=>r.runId)&&c.some(r=>!terminal.has(r.status)));
 // Reserve a slot through a same-session successor; it cannot be stolen by a new chain.
 let row=activeChains.map(c=>c.find(r=>['planned','ready'].includes(r.status))).find(r=>r&&s.runs.some(p=>p.chainId===r.chainId&&p.taskId===r.parentTask&&terminal.has(p.status)&&p.usableParent));
 if(!row){
  if(activeChains.length>=2)return {status:'waiting'};
  const next=chains.find(c=>!c.some(r=>r.runId)&&c.some(r=>['planned','ready'].includes(r.status)));
  if(!next||activeChains.some(c=>c[0].profile===next[0].profile))return {status:'waiting'};
  row=next.find(r=>['planned','ready'].includes(r.status));
 }
 await io.verify(s);
 if(io.stopped()||s.stopReason)return {status:'draining'};
 if(row.parentTask){
  const parent=s.runs.find(r=>r.chainId===row.chainId&&r.taskId===row.parentTask);
  if(!parent?.usableParent||!terminal.has(parent.status))throw Error('Parent not settled or not usable');
  row.conversationId=parent.conversationId;row.parentLabel=parent.label;row.status='ready';await io.save(s);
 }
 if(!row.conversationId){
  row.status='creating';row.conversationRequestedAt=new Date().toISOString();await io.save(s);
  try{row.conversationId=(await io.api(`/api/projects/${row.projectId}/conversations`,{})).id;row.status='ready';await io.save(s);}
  catch(e){if(e.code==='NOT_DISPATCHED'){row.status='planned';await io.save(s);return {status:'draining'};}throw e;}
 }
 if(io.stopped()||s.stopReason)return {status:'draining'};
 row.status='posting';row.requestedAt=new Date().toISOString();row.requestBody=requestFor(s,row);await io.save(s);
 try{Object.assign(row,await io.api(`/api/conversations/${row.conversationId}/messages`,row.requestBody),{status:'running'});await io.save(s);return {status:'submitted',label:row.label,runId:row.runId};}
 catch(e){
  if(e.code==='NOT_DISPATCHED'){row.status='ready';await io.save(s);return {status:'draining'};}
  row.postError=String(e);if(accountError(e))s.stopReason='authentication_or_quota';await io.save(s);return {status:'uncertain_post',label:row.label};
 }
}

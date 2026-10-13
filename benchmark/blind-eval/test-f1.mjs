// Entire transport is an in-memory fake. No HTTP connection, DB write or paid model.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {plan,step,reconcile,requestFor,digest} from './study-f1.mjs';
const config=JSON.parse(await fs.readFile(new URL('./f1-config.json',import.meta.url),'utf8'));
const s=plan(config,'blind-eval-f1-offline');
assert.equal(s.plannedOrder.filter(r=>r.phase===1).length,24);assert.equal(s.plannedOrder.filter(r=>r.phase===2).length,20);
assert.equal(new Set(s.plannedOrder.filter(r=>r.phase===1).map(r=>r.isolationKey)).size,20);
assert.equal(new Set(s.plannedOrder.filter(r=>r.phase===2).map(r=>r.isolationKey)).size,16);
assert.notEqual(plan(config,'blind-eval-f1-offline').batchUUID,s.batchUUID);
for(const t of config.tasks){
 const rows=s.plannedOrder.filter(r=>r.taskId===t.id);assert.equal(rows.length,4);
 assert.notEqual(rows[0].profile,rows[2].profile);
 for(const r of rows){assert.match(r.isolationKey,/^[A-Za-z0-9_-]{1,120}$/);if(r.parent)assert.equal(r.isolationKey,s.plannedOrder.find(x=>x.label===r.parent).isolationKey);assert.equal(requestFor(s,r).content,t.prompt);}
}
s.freeze={version:'F1'};s.phaseFreezes={'1':{mock:true},'2':{mock:true}};
let chats=new Map(),runs=new Map(),requests=[],saved=[],drift=false,fail=false,uncertain=false;
const io={save:async s=>saved.push(structuredClone(s)),verify:async()=>{if(drift)throw Error('Frozen inputs changed');},capture:async()=>{},api:async(route,body)=>{
 requests.push({route,body});
 if(body&&route.endsWith('/conversations')){const id='chat-'+chats.size;chats.set(id,{id,projectId:route.split('/')[3],messages:[]});return {id};}
 if(body&&route.endsWith('/messages')){
  const conversationId=route.split('/')[3],id='run-'+runs.size;
  assert.equal(saved.at(-1).runs.at(-1).status,'posting');
  const run={id,conversationId,projectId:chats.get(conversationId).projectId,request:{userMessageId:'user-'+id,documentIds:body.documentIds,evaluation:body.evaluation},status:fail?'failed':'completed',usage:fail?null:{calls:1,input:100,output:10}};
  runs.set(id,run);const chat=chats.get(conversationId);chat.evaluationIsolationKey=body.evaluation.isolation_key;
  chat.messages.push({id:'user-'+id,role:'user',content:body.content},{runId:id,role:'assistant',content:'mock delivered answer',artifacts:fail?[]:[{name:'model.csv'}]});
  if(uncertain)throw Error('POST result lost after acceptance');return {runId:id};
 }
 if(route.startsWith('/api/runs/'))return runs.get(route.split('/').at(-1));
 if(route.startsWith('/api/conversations/'))return chats.get(route.split('/').at(-1));
 throw Error('Unexpected fake route '+route);
}};
// Drift before POST, then full schedule including failed D2 and blocked D3.
drift=true;await assert.rejects(step(s,1,io),/Frozen inputs/);assert.equal(requests.length,0);drift=false;
while(true){const next=s.plannedOrder.find(r=>r.phase===1&&!s.runs.some(a=>a.label===r.label));fail=next?.label==='F1_D2';const result=await step(s,1,io);if(result.status==='phase_complete')break;}
assert.equal(s.runs.find(r=>r.label==='F1_D3').status,'blocked_dependency');
const d2=s.runs.find(r=>r.label==='P1_D2'),d3=s.runs.find(r=>r.label==='P1_D3');assert.equal(d2.conversationId,d3.conversationId);
assert.equal(s.runs.length,24);assert.equal(requests.filter(r=>r.route.endsWith('/messages')).length,23);
assert.equal(s.runs.find(r=>r.label==='F1_D2').usage,null);
// Crash after server accepts: no duplicate POST, explicit identity-checked reconciliation.
uncertain=true;fail=false;await assert.rejects(step(s,2,io),/POST result lost/);
const count=requests.length;assert.equal((await step(s,2,io)).status,'uncertain_post');assert.equal(requests.length,count);
const pending=s.runs.at(-1),run=[...runs.values()].at(-1),chat=chats.get(pending.conversationId);
assert.throws(()=>reconcile(s,pending.label,{...run,request:{...run.request,evaluation:{}}},chat),/mismatch/);
reconcile(s,pending.label,run,chat);uncertain=false;
while((await step(s,2,io)).status!=='phase_complete'){}
assert.equal(s.runs.length,44);assert.equal(requests.filter(r=>r.route.endsWith('/messages')).length,43);
for(const r of s.runs.filter(r=>r.parent&&r.status==='completed'))assert.equal(r.conversationId,s.runs.find(p=>p.label===r.parent).conversationId);
const before=requests.length;assert.equal((await step(s,2,io)).status,'phase_complete');assert.equal(requests.length,before);
const report={passed:true,realHttpRequests:0,paidRequests:0,scheduledTurns:44,chains:36,phaseTurns:[24,20],fakePosted:43,failed:1,blocked:1,checks:['two phases, same F1','fresh batch UUID','reverse arm order','exact prompts','D2-D3 and H1-H2 same conversation/key','other chains isolated','persist before POST','uncertain POST reconciled without retry','failure preserved, independent chains continued','unknown usage retained','input drift blocks submit','completed run never resubmitted'],configSha256:digest(config)};
await fs.writeFile(new URL('../../data/evaluation/blind-eval-f1-preparation-20261008/scheduler-offline-test.json',import.meta.url),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));

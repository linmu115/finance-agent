// No real transport. Check the new material-block plan against the frozen F1 sequence.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {plan,step,requestFor,reconcile,digest} from './study-f11.mjs';
import {plan as originalPlan} from './study-f1.mjs';
const read=async n=>JSON.parse(await fs.readFile(new URL(n,import.meta.url),'utf8'));
const config=await read('./f11-heldout-config.json');
const old=originalPlan(await read('./f1-abc-config.json'),'blind-eval-original-offline');
const state=plan(config,'blind-eval-f11-heldout-offline');
assert.deepEqual(state.plannedOrder.map(r=>r.label),old.plannedOrder.filter(r=>['H1','H2'].includes(r.taskId)).map(r=>r.label));
assert.equal(state.plannedOrder.length,8);assert.equal(new Set(state.plannedOrder.map(r=>r.isolationKey)).size,4);
for(const r of state.plannedOrder){assert.equal(requestFor(state,r).content,old.config.tasks.find(t=>t.id===r.taskId).prompt);assert.match(r.isolationKey,/^F11_[A-Za-z0-9_]+$/);}
state.freeze={version:'F1.1'};state.phaseFreezes={'1':{}};
const chats=new Map(),runs=new Map();let posted=0,saved,uncertain=true,drift=true;
const io={save:async s=>{saved=structuredClone(s);},capture:async()=>{},verify:async()=>{if(drift)throw Error('drift');},api:async(route,body)=>{
 if(body&&route.endsWith('/conversations')){const id='c'+chats.size;chats.set(id,{id,projectId:route.split('/')[3],messages:[]});return {id};}
 if(body&&route.endsWith('/messages')){
  assert.equal(saved.runs.at(-1).status,'posting');posted++;const id='r'+runs.size,conversationId=route.split('/')[3],chat=chats.get(conversationId);
  const failed=body.evaluation.budget_group_id.endsWith('P1_H1');
  const run={id,conversationId,projectId:chat.projectId,status:failed?'failed':'completed',request:{evaluation:body.evaluation,documentIds:body.documentIds,userMessageId:'u'+id},usage:failed?null:{calls:1}};
  runs.set(id,run);chat.evaluationIsolationKey=body.evaluation.isolation_key;chat.messages.push({id:'u'+id,role:'user',content:body.content},{runId:id,role:'assistant',content:'mock answer',artifacts:failed?[]:[{name:'mock.csv'}]});
  if(uncertain)throw Error('accepted but response lost');return {runId:id};
 }
 if(route.startsWith('/api/runs/'))return runs.get(route.split('/').at(-1));
 if(route.startsWith('/api/conversations/'))return chats.get(route.split('/').at(-1));
 throw Error('unexpected fake route');
}};
await assert.rejects(step(state,1,io),/drift/);assert.equal(posted,0);drift=false;
await assert.rejects(step(state,1,io),/response lost/);assert.equal((await step(state,1,io)).status,'uncertain_post');assert.equal(posted,1);
const pending=state.runs.at(-1),run=[...runs.values()].at(-1),chat=chats.get(pending.conversationId);
reconcile(state,pending.label,run,chat);uncertain=false;
while((await step(state,1,io)).status!=='phase_complete'){}
assert.equal(posted,7);assert.equal(state.runs.find(r=>r.label==='P1_H2').status,'blocked_dependency');
for(const r of state.runs.filter(r=>r.parent&&r.status==='completed')){const parent=state.runs.find(p=>p.label===r.parent);assert.equal(r.isolationKey,parent.isolationKey);assert.equal(r.conversationId,parent.conversationId);}
assert.equal(state.runs.find(r=>r.label==='P1_H1').usage,null);
const report={passed:true,paidRequests:0,realHttpRequests:0,turns:8,chains:4,exactOriginalHeldoutOrder:true,exactPrompts:true,fakePosted:7,blocked:1,unknownUsagePreserved:true,uncertainPostNotResent:true,configSha256:digest(config)};
await fs.writeFile(new URL('../../data/evaluation/blind-eval-heldout-reference-20261008/f11-scheduler-offline.json',import.meta.url),JSON.stringify(report,null,2));console.log(JSON.stringify(report));

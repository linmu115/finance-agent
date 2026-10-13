// Offline: no HTTP, model, product DB, or production freeze.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {plan,requestFor,step,digest} from './study-f14.mjs';
import {plan as oldPlan} from './study-f1.mjs';
const root=new URL('../../',import.meta.url),read=async p=>JSON.parse(await fs.readFile(new URL(p,root),'utf8'));
const cfg=await read('benchmark/blind-eval/f14-stage-b-config.json');
const old=oldPlan(await read('benchmark/blind-eval/f1-abc-config.json'),'blind-eval-original-offline');
const state=plan(cfg,'blind-eval-f14-b-offline');
assert.equal(cfg.freezeVersion,'F1.4');
assert.deepEqual(cfg.tasks.map(t=>t.id),['X1','X3','X4','X5','X6']);
assert.deepEqual(state.plannedOrder.map(x=>x.label),old.plannedOrder.filter(x=>x.phase===2).map(x=>x.label));
assert.equal(state.plannedOrder.length,20);
assert.equal(new Set(state.plannedOrder.map(x=>x.isolationKey)).size,20);
const payloads=state.plannedOrder.map(row=>{
 const body=requestFor(state,row),source=old.config.tasks.find(t=>t.id===row.taskId);
 assert.equal(body.content,source.prompt);assert.deepEqual(body.documentIds,[]);
 assert.equal(body.evaluation.analysis_only,true);assert.match(body.evaluation.isolation_key,/^F14_/);
 assert.deepEqual(body.evaluation.budget,old.config.evaluationLimits);assert.equal(row.parent,null);
 return {label:row.label,profile:row.profile,repeat:row.repeat,analysis_only:true,documentIds:[],promptUnchanged:true};
});
for(const task of cfg.tasks){
 const r1=state.plannedOrder.filter(r=>r.taskId===task.id&&r.repeat===1).map(r=>r.profile);
 const r2=state.plannedOrder.filter(r=>r.taskId===task.id&&r.repeat===2).map(r=>r.profile);
 assert.deepEqual(r2,[...r1].reverse());
}
// This is the observed cancellation race, checked without submitting a request.
state.runs=[{...state.plannedOrder[0],status:'cancelled'}];
let transportCalls=0;const noTransport={api:async()=>{transportCalls++;throw Error('transport forbidden')},save:async()=>{},capture:async()=>{},verify:async()=>{}};
assert.equal((await step(state,1,noTransport)).status,'batch_stopped');
assert.equal((await step(structuredClone(state),1,noTransport)).status,'batch_stopped');
assert.equal(transportCalls,0);
const stopped=plan(cfg,'blind-eval-f14-stop-offline');stopped.freeze={version:'F1.4'};stopped.phaseFreezes={'1':{}};
let stop=false;
assert.equal((await step(stopped,1,{...noTransport,isStopped:async()=>stop,verify:async()=>{stop=true;}})).status,'batch_stopped');
assert.equal(transportCalls,0);
const runner=await fs.readFile(new URL('benchmark/blind-eval/runner-f14.mjs',root),'utf8');
assert(runner.includes("receipt.freezeVersion!=='F1.4'"));
assert(runner.includes("version:'F1.4'"));
assert(runner.includes('snapshot-f14.py'));assert(!runner.includes('F1.2'));
const referencePaths=[...new Set([...cfg.referenceFiles,...cfg.phases['1'].referenceFiles])];
const references=[];
for(const path of referencePaths)references.push({path,sha256:digest(await fs.readFile(new URL(path,root)))});
const report={status:'offline_preparation_passed_not_production_freeze',turns:20,chains:20,
 exactApprovedOrder:true,reverseProfileOrderOnRepeat:true,exactPrompts:true,budgetUnchanged:true,
 analysisOnlyEveryRequest:true,cancelStopsNextAndRestart:true,stopDuringVerifyBlocksPost:true,
 realHttpRequests:0,paidRequests:0,productionReads:0,productionWrites:0,
 configSha256:digest(cfg),referenceInputsAtPreparation:references,payloadChecks:payloads,
 pending:['F1.4 deployed commit/tree/diff/PID and actual tool/context receipts','N3 production validation and preparation ledger','Coordinator project-pause, freeze and start notice'],
 productionFreeze:null,participantResults:null};
await fs.writeFile(new URL('data/evaluation/blind-eval-F14-B-preparation-20261008/offline-check.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({passed:true,turns:20,chains:20,realHttpRequests:0,paidRequests:0,productionFreeze:null}));

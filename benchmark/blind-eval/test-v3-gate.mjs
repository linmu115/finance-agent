import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {planGate,tick,terminal} from './study-v3-gate.mjs';
import {requestJson} from './evaluation-http.mjs';
const config=JSON.parse(await fs.readFile('benchmark/blind-eval/v3-gate-plan.json','utf8'));
const schedule=JSON.parse(await fs.readFile('benchmark/blind-eval/v3-gate-schedule.json','utf8'));
function fixture(){
 let state=planGate(config,schedule,'blind-eval-offline-fixture'),persisted,stopped=false,lost=false,stopAtSave=false;
 state.freeze={version:'F2.0.2'};
 const chats=new Map(),runs=new Map(),requests=[];
 const fetchImpl=async(url,init)=>{
  const route=new URL(url).pathname,body=init.body?JSON.parse(init.body):undefined;requests.push({route,method:init.method||'GET',body});
  let result;
  if(body!==undefined&&route.endsWith('/conversations')){const id='c'+chats.size;result={id,projectId:route.split('/')[3],messages:[]};chats.set(id,result);}
  else if(body!==undefined&&route.endsWith('/messages')){
   const chat=chats.get(route.split('/')[3]),id='r'+runs.size,mid='u'+runs.size;
   chat.evaluationIsolationKey=body.evaluation.isolation_key;chat.activeRunId=id;chat.messages.push({id:mid,role:'user',content:body.content,runId:id});
   const run={id,status:'running',projectId:chat.projectId,conversationId:chat.id,request:{...body,userMessageId:mid},usage:null};runs.set(id,run);result={runId:id};
   if(lost){lost=false;throw Error('Response lost after server accepted POST');}
  }else if(route.startsWith('/api/runs/'))result=runs.get(route.split('/')[3]);
  else if(route.startsWith('/api/conversations/'))result=chats.get(route.split('/')[3]);
  else throw Error('Unexpected fake request '+route);
  return new Response(JSON.stringify(result));
 };
 const io={api:(route,body)=>requestJson(route,body,{stopped:()=>stopped,fetchImpl}),stopped:()=>stopped,
  save:async s=>{persisted=structuredClone(s);if(stopAtSave&&s.runs.some(r=>r.status==='posting'))stopped=true;},verify:async()=>{},capture:async()=>{}};
 return {get state(){return state;},get persisted(){return persisted;},io,chats,runs,requests,
  stop:()=>{stopped=true;},loseNext:()=>{lost=true;},stopDuringSave:()=>{stopAtSave=true;},restart:()=>{state=structuredClone(persisted);},
  settle:(id,status='completed',error=null)=>{Object.assign(runs.get(id),{status,error,usage:{calls:1,input:9,output:1,unknownCalls:0}});}};
}
const submissions=f=>f.requests.filter(r=>r.method==='POST'&&r.route.endsWith('/messages'));
const checks=[];
{
 const f=fixture();f.state.firstFinancialInspectionRequired=true;
 for(let i=0;i<3;i++){await tick(f.state,f.io,{submit:true});f.settle('r'+i);}
 assert.equal((await tick(f.state,f.io,{submit:true})).status,'financial_inspection_required');
 assert.equal(submissions(f).length,3);f.state.firstFinancialInspection={passed:true};
 await tick(f.state,f.io,{submit:true});assert.equal(submissions(f).length,4);
 checks.push('F21 retains planned order and holds after first financial completion until diagnostic inspection');
}
{
 const f=fixture();f.state.firstTurnInspectionRequired=true;
 await tick(f.state,f.io,{submit:true});await tick(f.state,f.io,{submit:true});
 assert.equal(submissions(f).length,1);f.settle('r0');
 assert.equal((await tick(f.state,f.io,{submit:true})).status,'first_turn_inspection_required');
 assert.equal(submissions(f).length,1);f.state.firstTurnInspection={passed:true};
 await tick(f.state,f.io,{submit:true});assert.equal(submissions(f).length,2);
 checks.push('F203 first turn finishes and inspection passes before any second submission');
}
{
 const f=fixture();let loops=0;
 while(!f.state.runs.every(r=>terminal.has(r.status))){
  const observation=await tick(f.state,f.io,{submit:true});
  const active=[...f.runs.values()].filter(r=>r.status==='running');assert(active.length<=2);assert.equal(new Set(active.map(r=>r.request.evaluation.profile)).size,active.length);
  if(active.length===2||f.runs.size===18||observation.status==='waiting')for(const r of active)f.settle(r.id);
  assert(++loops<60);
 }
 assert.equal(submissions(f).length,18);assert.deepEqual(submissions(f).map(r=>r.body.evaluation.profile),schedule.map(r=>r.arm));
 assert.equal(new Set(submissions(f).map(r=>r.body.evaluation.isolation_key)).size,18);
 checks.push('complete 18-turn replay preserves all positions, distinct keys and concurrency limit');
}
{
 const f=fixture();await tick(f.state,f.io,{submit:true});await tick(f.state,f.io,{submit:true});await tick(f.state,f.io,{submit:true});
 assert.equal(submissions(f).length,2);assert.equal(new Set(submissions(f).map(r=>r.body.evaluation.profile)).size,2);
 f.restart();f.settle('r0');await tick(f.state,f.io,{submit:true});assert.equal(submissions(f).length,3);
 assert.deepEqual(submissions(f).map(r=>r.body.evaluation.profile),['original_pi','prepared','financial']);
 assert(submissions(f).every(r=>r.body.evaluation.analysis_only===true&&r.body.documentIds.length===0));
 checks.push('two different arms, fixed order, completed turn not replayed after app restart');
}
{
 const f=fixture();f.loseNext();assert.equal((await tick(f.state,f.io,{submit:true})).status,'uncertain_post');f.restart();
 await tick(f.state,f.io,{submit:false});assert.equal(f.state.runs[0].runId,'r0');assert.equal(submissions(f).length,1);
 checks.push('accepted POST with lost response reconciles original run without resubmission');
}
{
 const f=fixture();f.stopDuringSave();await tick(f.state,f.io,{submit:true});assert.equal(submissions(f).length,0);assert.equal(f.state.runs[0].status,'ready');
 checks.push('actual HTTP wrapper blocks message POST when cancellation arrives during persistence');
}
{
 const f=fixture();await tick(f.state,f.io,{submit:true});f.stop();f.settle('r0');await tick(f.state,f.io,{submit:true});assert.equal(submissions(f).length,1);assert.equal(f.state.runs[0].status,'completed');
 checks.push('drain preserves and polls in-flight run without starting next turn');
}
{
 const f=fixture();await tick(f.state,f.io,{submit:true});f.settle('r0','failed','TLS connection closed');await tick(f.state,f.io,{submit:true});assert.equal(f.state.runs[0].failureClass,'infrastructure');assert.equal(submissions(f).length,2);
 checks.push('infrastructure failure retained and next planned turn continues');
}
{
 const f=fixture();await tick(f.state,f.io,{submit:true});f.settle('r0','cancelled','operator');await tick(f.state,f.io,{submit:true});assert.equal(submissions(f).length,1);assert.equal(f.state.stopReason,'participant_cancelled');
 checks.push('participant cancellation stops subsequent dispatch');
}
{
 const f=fixture();f.io.verify=async()=>{throw Error('freeze_drift');};await assert.rejects(tick(f.state,f.io,{submit:true}),/freeze_drift/);assert.equal(submissions(f).length,0);
 checks.push('snapshot drift prevents any participant POST');
}
const result={status:'passed',checks,real_network_requests:0,paid_requests:0,uses_production_evaluator_http_wrapper:true};
if(process.env.FINANCE_COMPARISON_DIR)await fs.writeFile('data/evaluation/'+process.env.FINANCE_COMPARISON_DIR+'/offline-runner-validation.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));

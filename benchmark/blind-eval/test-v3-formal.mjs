import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {tick,terminal} from './study-v3-formal.mjs';
import {requestJson} from './evaluation-http.mjs';
const schedule=JSON.parse(await fs.readFile('benchmark/blind-eval/v3-formal-schedule.json','utf8'));
function fixture(rows=schedule){
 let state={runtimeFreeze:{},projectFreezes:{ready:{}},config:{tasks:[...new Set(rows.map(r=>r.task))].map(id=>({id,prompt:'fixture:'+id})),evaluationLimits:{}},runs:rows.map(r=>({label:r.arm+r.repeat+r.task,taskId:r.task,ordinal:r.ordinal,profile:r.arm,repeat:r.repeat,chainId:r.isolation_key_template,isolationKey:r.isolation_key_template,parentTask:r.same_session_as,projectId:r.task.startsWith('X')?'pending':'ready',status:'planned'}))},persisted,stopped=false,lost=false,stopOnPosting=false;
 const chats=new Map(),runs=new Map(),requests=[];
 const fetchImpl=async(url,init)=>{
  const route=new URL(url).pathname,body=init.body?JSON.parse(init.body):undefined;requests.push({route,body});let result;
  if(body!==undefined&&route.endsWith('/conversations')){const id='c'+chats.size;result={id,projectId:route.split('/')[3],messages:[]};chats.set(id,result);}
  else if(body!==undefined&&route.endsWith('/messages')){
   const chat=chats.get(route.split('/')[3]),id='r'+runs.size,mid='u'+runs.size;
   chat.evaluationIsolationKey=body.evaluation.isolation_key;chat.activeRunId=id;chat.messages.push({id:mid,role:'user',content:body.content,runId:id});
   runs.set(id,{id,status:'running',projectId:chat.projectId,conversationId:chat.id,request:{...body,userMessageId:mid},usage:null});result={runId:id};
   if(lost){lost=false;throw Error('Response lost after acceptance');}
  }else if(route.startsWith('/api/runs/'))result=runs.get(route.split('/')[3]);
  else if(route.startsWith('/api/conversations/'))result=chats.get(route.split('/')[3]);
  else throw Error('Unexpected fixture request');
  return new Response(JSON.stringify(result));
 };
 const io={api:(route,body)=>requestJson(route,body,{stopped:()=>stopped,fetchImpl}),stopped:()=>stopped,verify:async()=>{},capture:async()=>{},save:async s=>{persisted=structuredClone(s);if(stopOnPosting&&s.runs.some(r=>r.status==='posting'))stopped=true;}};
 return {get state(){return state;},io,chats,runs,requests,loseNext:()=>{lost=true;},stop:()=>{stopped=true;},stopAtPost:()=>{stopOnPosting=true;},restart:()=>{state=structuredClone(persisted);},settle:(id,status='completed',error=null)=>{Object.assign(runs.get(id),{status,error,usage:{calls:1,input:1,output:1,unknownCalls:0}});}};
}
const posts=f=>f.requests.filter(r=>r.body!==undefined&&r.route.endsWith('/messages'));
const checks=[];
{
 const f=fixture();let loops=0,result;
 do{
  result=await tick(f.state,f.io,{submit:true});
  const active=[...f.runs.values()].filter(r=>r.status==='running');assert(active.length<=2);assert.equal(new Set(active.map(r=>r.request.evaluation.profile)).size,active.length);
  if(active.length===2||result.status==='waiting'||result.status==='ready_blocks_complete')for(const r of active)f.settle(r.id);
  assert(++loops<400);
 }while(result.status!=='ready_blocks_complete');
 assert.equal(posts(f).length,108);assert.equal(f.chats.size,90);
 assert.equal(f.state.runs.filter(r=>r.projectId==='pending'&&r.status==='planned').length,54);
 const started=f.state.runs.filter(r=>r.runId&&!r.parentTask).sort((a,b)=>Number(a.runId.slice(1))-Number(b.runId.slice(1)));
 assert.deepEqual(started.map(r=>r.ordinal),f.state.runs.filter(r=>r.projectId==='ready'&&!r.parentTask).map(r=>r.ordinal));
 for(const r of f.state.runs.filter(r=>r.taskId==='D3')){const parent=f.state.runs.find(p=>p.chainId===r.chainId&&p.taskId==='D2');assert.equal(r.conversationId,parent.conversationId);assert.equal(r.isolationKey,parent.isolationKey);}
 assert(posts(f).every(r=>r.body.documentIds.length===0&&r.body.evaluation.analysis_only));
 checks.push('108 ready turns, 90 sessions, original chain order, two distinct active arms, dependencies preserved; 54 unfrozen turns untouched');
}
{
 const f=fixture();f.state.requiresFirstTurnInspection=true;
 await tick(f.state,f.io,{submit:true});await tick(f.state,f.io,{submit:true});assert.equal(posts(f).length,1);f.settle('r0');assert.equal((await tick(f.state,f.io,{submit:true})).status,'first_turn_inspection_required');assert.equal(posts(f).length,1);
 checks.push('first-round inspection precedes second submission');
}
{
 const f=fixture();f.loseNext();assert.equal((await tick(f.state,f.io,{submit:true})).status,'uncertain_post');f.restart();await tick(f.state,f.io,{submit:false});assert.equal(posts(f).length,1);assert.equal(f.state.runs[0].runId,'r0');
 checks.push('lost accepted POST reconciled without duplicate submission');
}
{
 const f=fixture();f.stopAtPost();await tick(f.state,f.io,{submit:true});assert.equal(posts(f).length,0);checks.push('HTTP stop boundary blocks a POST after persistence');
}
{
 const rows=schedule.filter(r=>r.task==='D2'||r.task==='D3');const f=fixture(rows);await tick(f.state,f.io,{submit:true});f.settle('r0');f.stop();await tick(f.state,f.io,{submit:true});assert.equal(posts(f).length,1);checks.push('cancelled queue never sends dependent continuation');
}
{
 const rows=schedule.filter(r=>r.task==='D2'||r.task==='D3');const f=fixture(rows);await tick(f.state,f.io,{submit:true});f.settle('r0','failed','TLS connection reset');await tick(f.state,f.io,{submit:true});assert.equal(f.state.runs[1].status,'blocked_dependency');assert.equal(posts(f).length,2);checks.push('infrastructure failure retained, unavailable child blocked, next chain continues');
}
{
 const f=fixture();await tick(f.state,f.io,{submit:true});f.settle('r0','failed','HTTP 401 authentication failed');await tick(f.state,f.io,{submit:true});assert.equal(posts(f).length,1);assert.equal(f.state.stopReason,'authentication_or_quota');checks.push('authentication or quota stops next submission');
}
{
 const f=fixture();f.io.verify=async()=>{throw Error('material drift');};await assert.rejects(tick(f.state,f.io,{submit:true}),/material drift/);assert.equal(posts(f).length,0);checks.push('material drift prevents submissions');
}
const result={passed:true,checks,network_requests:0,paid_requests:0};
await fs.writeFile('data/evaluation/blind-eval-F21-formal-20261009/offline-adapter-validation.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));

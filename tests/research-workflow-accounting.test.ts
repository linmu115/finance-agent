import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {reconcileContinuationAccounting} from '../scripts/research_workflow_accounting.mjs';

const usage=(calls=2,input=100,output=20)=>({model_calls:calls,settled_calls:calls,input_tokens:input,output_tokens:output,total_tokens:input+output,failed_calls:0,unknown_usage_calls:0});
const snapshot=(value=usage(),extra={})=>({budget_group_id:'g',usage:value,elapsed_seconds:10,reserved:{model_calls:0,output_tokens:0},in_flight:[],unknown_output_charge:0,...extra});
const before={continuation:{prior_usage:usage(12,515369,26790),prior_elapsed_seconds:158.749,original_budget:{max_model_calls:60,max_input_tokens:3000000,max_output_tokens:450000,max_total_tokens:3450000,max_wall_seconds:1800}}};
const run=(id='new',evaluation=snapshot(),status='failed')=>({id,evaluation,status});
const finished=(id='new',value=snapshot())=>({runId:id,type:'evaluation_budget',data:{action:'run_finished',...value}});
const unavailable=async()=>{throw Error('offline fixture');};
const check=(report:any,api:any=unavailable,audit:any=unavailable)=>reconcileContinuationAccounting({before,report,api,audit,pause:async()=>{}});

test('unfinished stage uses live terminal API rather than previous saved stage snapshot',async()=>{
 const report={budget_group_id:'g',stages:[{run:run('old',snapshot(usage(2,100,20)))}],active_stage:{run_id:'new'}};
 const result=await check(report,async()=>run('new',snapshot(usage(5,700,90))),async(id:string)=>id==='new'?[finished(id,snapshot(usage(5,700,90)))]:[finished(id,snapshot(usage(2,100,20)))]);
 assert.equal(result.accounting_status,'complete');assert.equal(result.combined_usage.model_calls,17);
 assert.equal(result.combined_usage.input_tokens,516069);assert.equal(result.combined_usage.output_tokens,26880);
});
test('terminal run followed by artifact read failure remains recoverable from active stage id',async()=>{
 const result=await check({budget_group_id:'g',stages:[],active_stage:{run_id:'new'},last_observed_run:run()},async()=>run(),async()=>[finished()]);
 assert.equal(result.usage_complete,true);assert.equal(result.combined_usage.total_tokens,542279);
});
test('API unavailable recovers actual terminal budget audit including failed spend',async()=>{
 const value=usage(4,900,300);value.failed_calls=2;
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},unavailable,async()=>[finished('new',snapshot(value))]);
 assert.equal(result.accounting_status,'complete');assert.equal(result.combined_usage.failed_calls,2);
 assert.equal(result.evidence.errors[0].source,'run_api');
});
test('missing active API and audit is unknown, never zero',async()=>{
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}});
 assert.equal(result.accounting_status,'unavailable');assert.equal(result.continuation_usage,null);assert.equal(result.combined_usage,null);
 assert.equal(result.combined_known_usage_lower_bound.input_tokens,515369);
 assert.equal(result.combined_active_elapsed_seconds,null);
});
test('previous completed cumulative snapshot is only a lower bound when newer stage evidence is absent',async()=>{
 const result=await check({budget_group_id:'g',stages:[{run:run('old')}],active_stage:{run_id:'new'}},unavailable,async(id:string)=>id==='old'?[finished(id)]:[]);
 assert.equal(result.accounting_status,'partial');assert.equal(result.combined_usage,null);
 assert.equal(result.combined_known_usage_lower_bound.total_tokens,542279);
});
test('a lost submission response does not imply that no model call was made',async()=>{
 const result=await check({budget_group_id:'g',stage_attempts:[{index:1,conversation_id:'chat',submission_started_at:'2026-01-01'}]});
 assert.equal(result.accounting_status,'unacknowledged_submission');assert.equal(result.combined_usage,null);
 assert.equal(result.unacknowledged_submissions.length,1);
});
test('preflight failure before any submission legitimately retains zero continuation',async()=>{
 const result=await check({budget_group_id:'g',stages:[]},async()=>{assert.fail('no API needed');},async()=>{assert.fail('no audit needed');});
 assert.equal(result.accounting_status,'not_started');assert.deepEqual(result.combined_usage,before.continuation.prior_usage);
});
test('raw model audit lower bound counts cached input and deduplicates request IDs',async()=>{
 const event={runId:'new',type:'model_usage',data:{requestId:'r1',usageKnown:true,stopReason:'length',usage:{input:30,cacheRead:70,cacheWrite:2,output:40}}};
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},unavailable,async()=>[event,event]);
 assert.equal(result.accounting_status,'partial');assert.equal(result.combined_usage,null);
 assert.deepEqual(result.continuation_known_usage_lower_bound,{...usage(1,102,40),failed_calls:1});
});
test('terminal snapshot cannot hide larger actual request audit spend',async()=>{
 const event={runId:'new',type:'model_usage',data:{requestId:'r1',usageKnown:true,usage:{input:500,output:10},stopReason:'stop'}};
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},async()=>run(),async()=>[finished(),event]);
 assert.equal(result.accounting_status,'incomplete_or_conflicting_terminal_evidence');assert.equal(result.combined_usage,null);
 assert.equal(result.continuation_known_usage_lower_bound.input_tokens,500);
});
test('unknown provider usage is not relabelled complete even with terminal budget snapshot',async()=>{
 const value=usage();value.unknown_usage_calls=1;value.failed_calls=1;
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},async()=>run('new',snapshot(value)),async()=>[]);
 assert.equal(result.accounting_status,'unknown_model_usage');assert.equal(result.usage_complete,false);assert.equal(result.combined_usage,null);
 assert.equal(result.continuation_usage.unknown_usage_calls,1);
});
test('bounded read-only polling allows cancellation settlement without restarting a run',async()=>{
 let calls=0;
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},async(route:string)=>{
  assert.equal(route,'/api/runs/new');calls++;
  return calls<3?run('new',snapshot(usage(),{reserved:{model_calls:1},in_flight:[{id:'ticket'}]}),'running'):run();
 },async()=>[finished()]);
 assert.equal(calls,3);assert.equal(result.accounting_status,'complete');
});
test('in-flight after bounded polling is explicitly partial',async()=>{
 let calls=0;
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},async()=>{calls++;return run('new',snapshot(usage(),{reserved:{model_calls:1},in_flight:[{id:'ticket'}]}),'running');},async()=>[]);
 assert.equal(calls,3);assert.equal(result.accounting_status,'partial');assert.equal(result.combined_usage,null);
});
test('different budget group and different run audit cannot establish completion',async()=>{
 const result=await check({budget_group_id:'g',active_stage:{run_id:'new'}},async()=>run('new',snapshot(usage(),{budget_group_id:'foreign'})),async()=>[finished('foreign')]);
 assert.equal(result.accounting_status,'unavailable');assert.equal(result.combined_usage,null);assert.equal(result.evidence.errors.length,2);
});
test('shared cumulative snapshots are never added across three stages',async()=>{
 const stages=[1,2,3].map(n=>({run:run('r'+n,snapshot(usage(n,n*100,n*20)))}));
 const result=await check({budget_group_id:'g',stages},async()=>stages[2].run,async(id:string)=>[finished(id,stages.find(s=>s.run.id===id)!.run.evaluation)]);
 assert.equal(result.combined_usage.model_calls,15);assert.equal(result.combined_usage.input_tokens,515669);
});
test('preserved real audit reconstructs the recorded budget without calling any API',async()=>{
 const root=path.resolve(import.meta.dirname,'..');
 const prior=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/liugong-research-workflow-v06.json'),'utf8'));
 const events=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/liugong-research-workflow-v06.stage-1.audit.json'),'utf8'));
 const originalRun=prior.stages[0].run;
 const result=await check({budget_group_id:originalRun.evaluation.budget_group_id,active_stage:{run_id:originalRun.id}},unavailable,async()=>events);
 assert.equal(result.accounting_status,'complete');assert.deepEqual(result.continuation_usage,originalRun.evaluation.usage);
 assert.equal(result.evidence.raw_model_usage_lower_bound.input_tokens,515369);
 assert.equal(result.evidence.raw_model_usage_lower_bound.output_tokens,26790);
});
test('frozen v07 task and previous reports remain byte-identical after offline prepare',async()=>{
 const root=path.resolve(import.meta.dirname,'..');
 const preserved=['liugong-research-workflow-v06.before.json','liugong-research-workflow-v06.json','liugong-research-workflow-v06.stage-1.audit.json','liugong-research-workflow-v07.before.json'];
 const hash=async(file:string)=>createHash('sha256').update(await fs.readFile(path.join(root,'benchmark/results',file))).digest('hex');
 const hashes=await Promise.all(preserved.map(hash));
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'research-accounting-'));
 try{
  const guard=path.join(directory,'offline.mjs');await fs.writeFile(guard,"globalThis.fetch=()=>{throw Error('network forbidden in offline fixture')};\n");
  const prefix=path.join(directory,'prepared');
  await promisify(execFile)(process.execPath,['--import',pathToFileURL(guard).href,'scripts/verify_liugong_research_workflow.mjs','--prepare','--version','v07','--prefix',prefix],{cwd:root});
  const actual=JSON.parse(await fs.readFile(prefix+'.before.json','utf8'));
  const expected=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/liugong-research-workflow-v07.before.json'),'utf8'));
  assert.equal(actual.task_sha256,expected.task_sha256);assert.deepEqual(actual.tasks,expected.tasks);assert.deepEqual(actual.budget,expected.budget);
  assert.deepEqual(await Promise.all(preserved.map(hash)),hashes);
 }finally{
  const resolved=await fs.realpath(directory),tempRoot=await fs.realpath(os.tmpdir());
  assert.ok(resolved.startsWith(tempRoot+path.sep)&&path.basename(resolved).startsWith('research-accounting-'));
  await fs.rm(resolved,{recursive:true,force:true});
 }
});

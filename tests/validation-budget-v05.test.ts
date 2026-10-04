import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent ESM helper.
import {summarizeBudget} from '../scripts/validation_budget_v05.mjs';
const cap={max_model_calls:5,max_input_tokens:1000,max_output_tokens:500,max_total_tokens:1500,max_wall_seconds:60};
test('v05 counts main plus every inner call exactly once, including failed inference and cached-input tokens',()=>{
 const events=[{type:'extraction_request',data:{requestId:'a',messages:[{content:'[[DEFINITION:x]]'}]}},{type:'extraction_result',at:'now',data:{requestId:'a',stopReason:'length',usage:{input:100,cacheRead:200,cacheWrite:10,output:70},durationMs:400}},{type:'extraction_request',data:{requestId:'b',messages:[{content:'financial row'}]}}];
 const result=summarizeBudget([{id:'r',usage:{calls:3,input:610,output:90}}],{r:events},20,cap);
 assert.equal(result.actual.input_tokens,610);assert.equal(result.actual.model_calls,3);assert.equal(result.main_pi.calls,2);assert.equal(result.main_pi.input,300);assert.equal(result.bridge_phases.definition.input,310);assert.equal(result.failed_calls.length,1);assert.equal(result.pending_bridge_requests,1);assert.equal(result.cap_reached,false);
 const stop=summarizeBudget([{id:'r',usage:{calls:6,input:610,output:90}}],{r:events},61,cap);assert.equal(stop.cap_reached,true);assert.deepEqual(stop.exceeded.map((x:any)=>x.metric),['model_calls','wall_seconds']);assert.equal(stop.exceeded[0].overrun,1);
 assert.equal(summarizeBudget([{id:'r',usage:{calls:0,input:0,output:0}}],{r:events},20,cap).accounting_valid,false);
});

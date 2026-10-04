import test from 'node:test';
import assert from 'node:assert/strict';
import {EvaluationBudget,EvaluationBudgetExceeded,EvaluationBudgets,normalizeEvaluation,type EvaluationOptions} from '../server/evaluation-budget.js';

const config=(patch:Partial<EvaluationOptions['budget']>={}):EvaluationOptions=>({profile:'financial',budget_group_id:'fixture-shared',budget:{max_model_calls:4,max_input_tokens:1000,max_output_tokens:100,max_total_tokens:1100,max_wall_seconds:60,...patch}});
const clock={now:()=>1000,scheduleDeadline:false};

test('both sessions share synchronous call and concurrent output reservations',()=>{
 const registry=new EvaluationBudgets(clock),a=registry.acquire('p',config({max_model_calls:2})),b=registry.acquire('p',config({max_model_calls:2}));
 assert.equal(a,b);
 const first=a.reserve('session-a',80),second=b.reserve('session-b',80);
 assert.equal(first.max_output_tokens,80);assert.equal(second.max_output_tokens,20);
 assert.throws(()=>a.reserve('session-a',1),/max_model_calls/);
 a.settle(first,{input:25,output:30});b.settle(second,{input:15,output:10});
 assert.deepEqual(a.snapshot().usage,{model_calls:2,settled_calls:2,input_tokens:40,output_tokens:40,total_tokens:80,failed_calls:0,unknown_usage_calls:0});
 assert.equal(a.snapshot().denied_calls,1);
});

test('unused reserved output is released only when that request settles',()=>{
 const b=new EvaluationBudget(config(),clock),first=b.reserve('a',80),second=b.reserve('b',80);
 assert.throws(()=>b.reserve('c',1),/max_output_tokens/);
 b.settle(first,{input:10,output:30});
 const third=b.reserve('c',100);
 assert.equal(third.max_output_tokens,50);
 assert.equal(b.snapshot().reserved.output_tokens,70);
 b.settle(second,{input:10,output:10});b.settle(third,{input:10,output:40});
 assert.equal(b.snapshot().usage.output_tokens,80);
});

test('input is an explicit post-usage soft cap and in-flight overrun is reported',()=>{
 const b=new EvaluationBudget(config({max_input_tokens:20,max_total_tokens:50}),clock),a=new AbortController(),c=new AbortController();
 b.attach('a',a);b.attach('c',c);
 const first=b.reserve('a',20),second=b.reserve('c',20);
 const snapshot=b.settle(first,{input:24,output:8});
 assert.equal(snapshot.input_limit_enforcement,'post_usage_soft_cap');assert.equal(snapshot.overage.input_tokens,4);
 assert.equal(snapshot.reserved.output_tokens,20);assert(a.signal.aborted);assert(c.signal.aborted);
 assert.throws(()=>b.reserve('later',1),EvaluationBudgetExceeded);
 const final=b.settle(second,{input:12,output:10},{failed:true});
 assert.equal(final.usage.total_tokens,54);assert.equal(final.overage.total_tokens,4);assert.equal(final.usage.failed_calls,1);
});

test('cached input and failed length output are counted exactly once',()=>{
 const b=new EvaluationBudget(config(),clock),ticket=b.reserve('a',40);
 const result=b.settle(ticket,{input:10,cacheRead:20,cacheWrite:5,output:40},{failed:true});
 assert.equal(result.usage.input_tokens,35);assert.equal(result.usage.output_tokens,40);assert.equal(result.usage.failed_calls,1);
 assert.throws(()=>b.settle(ticket,{input:10,output:40}),/already_settled/);
 assert.equal(b.snapshot().usage.model_calls,1);
});

test('failure without provider usage stays unknown and retains output debit',()=>{
 const b=new EvaluationBudget(config(),clock),ticket=b.reserve('a',70);
 const result=b.settle(ticket,undefined,{failed:true});
 assert.equal(result.usage.unknown_usage_calls,1);assert.equal(result.unknown_output_charge,70);
 assert.equal(result.usage.output_tokens,0);assert.equal(b.reserve('b',50).max_output_tokens,30);
});

test('group deadlines apply to attached runs and cannot be reset by a second session',()=>{
 let now=0;const registry=new EvaluationBudgets({now:()=>now,scheduleDeadline:false});
 const b=registry.acquire('p',config({max_wall_seconds:2})),controller=new AbortController();b.attach('a',controller);
 now=2500;
 assert.equal(registry.acquire('p',config({max_wall_seconds:2})),b);
 assert.throws(()=>b.reserve('b',1),/max_wall_seconds/);assert(controller.signal.aborted);
 assert.equal(b.snapshot().elapsed_seconds,2.5);
});

test('groups cannot change profiles or limits, while projects are isolated',()=>{
 const registry=new EvaluationBudgets(clock),original=registry.acquire('p',config());
 assert.throws(()=>registry.acquire('p',{...config(),profile:'generic'}),/group_conflict/);
 assert.throws(()=>registry.acquire('p',config({max_model_calls:9})),/group_conflict/);
 assert.notEqual(registry.acquire('q',config()),original);
});

test('restoring a ledger preserves spend and marks unrecoverable in-flight calls',()=>{
 const old=new EvaluationBudget(config(),clock),done=old.reserve('a',30);old.settle(done,{input:10,output:10});old.reserve('b',50);
 const restored=new EvaluationBudget(config(),clock,old.snapshot());
 assert.equal(restored.snapshot().usage.model_calls,2);assert.equal(restored.snapshot().usage.settled_calls,2);
 assert.equal(restored.snapshot().usage.unknown_usage_calls,1);assert.equal(restored.snapshot().unknown_output_charge,50);
 assert.equal(restored.reserve('new',90).max_output_tokens,40);
});

test('total limit constrains output reservations with already measured input',()=>{
 const b=new EvaluationBudget(config({max_total_tokens:50}),clock),first=b.reserve('a',20);
 b.settle(first,{input:25,output:5});
 assert.equal(b.reserve('b',90).max_output_tokens,20);
});

test('budget input rejects missing, unbounded, negative and unknown configuration',()=>{
 assert.equal(normalizeEvaluation(undefined),undefined);
 assert.deepEqual(normalizeEvaluation(config()),config());
 for(const invalid of [null,{}, {...config(),profile:'hidden'}, {...config(),budget_group_id:'../x'},
  {...config(),budget:{...config().budget,max_model_calls:1.5}}, {...config(),budget:{...config().budget,max_wall_seconds:Infinity}},
  {...config(),budget:{...config().budget,max_input_tokens:-1}}, {...config(),budget:{...config().budget,extra:1}}])assert.throws(()=>normalizeEvaluation(invalid));
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {addUsage,aggregateAudit,emptyUsage} from '../server/usage.js';

test('usage separates cache, reasoning, phases and failures without counting reasoning twice',()=>{
 const u=emptyUsage(),config={baseUrl:'https://api.deepseek.com',model:'deepseek-flash'};
 addUsage(u,{input:100,cacheRead:900,output:200,reasoning:150},true,'cleaning',config);
 addUsage(u,{input:40,cacheRead:60,output:10,reasoning:5},true,'cleaning_review',config);
 addUsage(u,undefined,false,'main',config);
 assert.equal(u.input,1100);assert.equal(u.output,210);assert.equal(u.reasoning,155);assert.equal(u.cacheRead,960);
 assert.equal(u.calls,3);assert.equal(u.unknownCalls,1);assert.equal(u.phases!.cleaning.input,1000);
 assert.equal(u.costUsd,null);assert.ok(Math.abs(u.costCnyMin!-.0009992)<1e-10);
});
test('manual pricing charges cache hits separately, and unknown historical zero prices are not free',()=>{
 const u=emptyUsage();addUsage(u,{input:10,cacheRead:990,output:50},true,'main',{inputPricePerMillionUsd:1,cacheReadPricePerMillionUsd:.02,outputPricePerMillionUsd:4});
 assert.equal(u.costUsd,.0002298);
 const legacy=aggregateAudit([{type:'model_usage',data:{requestId:'a',usageKnown:true,usage:{input:10,cacheRead:0,output:2,cost:{total:0}}}},{type:'model_usage',data:{requestId:'a',usageKnown:true,usage:{input:10,cacheRead:0,output:2}}}]);
 assert.equal(legacy.calls,1);assert.equal(legacy.costUsd,null);
});

test('interrupted requests remain unknown and late settlements replace unknown without double counting',()=>{
 const request=(id:string)=>({type:'model_request',data:{requestId:id,phase:'main',usagePhase:'cleaning'}});
 const unknown={type:'model_usage',data:{requestId:'late',usageKnown:false}};
 const settled={type:'model_usage',data:{requestId:'late',usageKnown:true,usage:{input:20,cacheRead:80,output:5},usagePhase:'cleaning'}};
 const before=aggregateAudit([request('lost'),request('late'),unknown]);
 assert.equal(before.calls,2);assert.equal(before.unknownCalls,2);
 const after=aggregateAudit([request('lost'),request('late'),unknown,settled,settled,unknown]);
 assert.equal(after.calls,2);assert.equal(after.unknownCalls,1);
 assert.equal(after.input,100);assert.equal(after.output,5);assert.equal(after.phases!.cleaning.calls,2);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {modelContext} from '../server/model-context.js';
import {registerNumericTables,referenceInventory} from '../server/numeric-tables.js';

test('workpaper values stay on the host; model sees reference catalog and observations',()=>{
 const report={tables:{income:{columns:{value:{unit:'百万元',currency:'CNY'}},rows:[{key:'revenue',value:'836.925'}]}}};
 const input:any={status:'ok',data:{kind:'statement_analysis',report,numeric_tables:report.tables,summary:{income:{row_keys:['revenue']}},observations:[{finding:'毛利率下降 7.7321 个百分点'}],delivery:{files:[{name:'income.csv'}]}},source_refs:[],warnings:[],trace_id:'t'};
 const output=modelContext('financial_workpaper',input);
 assert.equal(output.data.report,undefined);assert.equal(output.data.numeric_tables,undefined);
 assert.deepEqual(output.data.summary,input.data.summary);assert.equal(input.data.report,report);
 assert.deepEqual(output.data.observations,input.data.observations);
});

test('financial workpaper is absent from both general Pi profiles',async()=>{
 const {GENERIC_TOOL_ALLOWLIST,PREPARED_TOOL_ALLOWLIST}=await import('../server/runs.js');
 assert.equal(GENERIC_TOOL_ALLOWLIST.has('financial_workpaper'),false);
 assert.equal(PREPARED_TOOL_ALLOWLIST.has('financial_workpaper'),false);
});

test('workpaper tables register before projection and preserve typed cells and explicit row keys',()=>{
 const data={numeric_tables:{income:{columns:{metric:{},value:{unit:'百万元',currency:'CNY'}},rows:[{metric:'revenue',value:'836.925'}],row_keys:['revenue'],evidence:[{value:{record_id:'fact1'}}]}}};
 const registry:any={};registerNumericTables(registry,data);
 const projected=modelContext('financial_workpaper',{status:'ok',data});
 assert.equal(projected.data.numeric_tables,undefined);
 assert.equal(registry.income.rows[0].value,'836.925');assert.equal(registry.income.evidence[0].value.record_id,'fact1');
 assert.deepEqual(referenceInventory(registry).income.row_keys,['revenue']);
});

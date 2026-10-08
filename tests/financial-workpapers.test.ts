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

test('model receives ready-to-paste key values and whole-table bindings while A1 keeps exact values',()=>{
 const data={key_values:['本期收入=836.93 CNY 百万元 `{{income.revenue.2025-H1}}`'],table_bindings:{income:'{{table:income}}'},period_roles:{current:'2025-H1',comparison:'2024-H1'},numeric_tables:{}};
 const projected=modelContext('financial_workpaper',{status:'ok',data}).data;
 assert.deepEqual(projected.key_values,data.key_values);assert.deepEqual(projected.table_bindings,data.table_bindings);assert.deepEqual(projected.period_roles,data.period_roles);
});

test('management evidence, signal questions and basis restrictions remain visible after workpaper projection',()=>{
 const data={report:{tables:{}},numeric_tables:{},
  drivers_evidence:[{key:'finance_net',disclosure_status:'qualitative',evidence:[{document_id:'doc',page:12,quote:'Fixed deposits increased interest income.'}]}],
  signal_followups:[{key:'cash_conversion',persistence:{known_sample_count:2,allow_continuous_claim:false},alternative_explanations:[{status:'candidate_not_evidence'}]}],
  answer_constraints:[{code:'profit_attribution_unknown',subject:{table:'excluded_CNY_money',row_key:'r'},prohibited_uses:['label_as_parent_profit']}]};
 const projected=modelContext('financial_workpaper',{status:'ok',data}).data;
 for(const key of ['drivers_evidence','signal_followups','answer_constraints'] as const) assert.deepEqual(projected[key],data[key]);
 assert.equal(projected.report,undefined);assert.equal(projected.numeric_tables,undefined);
});

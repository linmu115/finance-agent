import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent ESM scorer.
import {scoreHoldout} from '../scripts/score_holdout.mjs';
const gold={id:'unseen',input_file:'fixture.pdf',company_id:'test',page:1,original_page:19,source_row_label:'应付租赁款',raw_value:'9,007,199,254,740,992.01',value:'9007199254740992.01',concept:'gross',metric:null,period:'2024-12-31',period_start:'',period_end:'2024-12-31',scope:'consolidated_CAS',currency:'CNY',version:'original',definition_regex:'总额|gross',period_variants:[]};
const fact={document_id:'d',metric:'lease_gross',label:'租赁负债总额',period:'2024-12-31',period_start:'',period_end:'2024-12-31',currency:'CNY',raw_unit:'元',normalized_unit:'CNY',scope:'consolidated_CAS',value:gold.value,raw_value:gold.raw_value,version:'original',dimensions:{},source_ref:{document_id:'d',table_id:'d:t1',row:2,column:2,page:1,text:'应付租赁款 | '+gold.raw_value,normalization:{engine:'LangExtract',char_interval:[2,9]}}};
const docs=[{file:'fixture.pdf',id:'d'}];
test('holdout scoring independently checks exact cents, reported unit, period and source despite a plausible normalized label',()=>{
 assert.equal(scoreHoldout([gold],[],[fact],docs).passed_facts,1);
 for(const patch of [{value:'9007199254740992.02'},{raw_unit:'万元'},{currency:'USD'},{period_start:'2024-01-01'},{period:'2024-FY'},{scope:'parent_CAS'}])assert.equal(scoreHoldout([gold],[],[{...fact,...patch}],docs).failed_facts,1);
 assert.equal(scoreHoldout([gold],[],[{...fact,source_ref:{...fact.source_ref,page:2}}],docs).failed_facts,1);
 assert.equal(scoreHoldout([gold],[],[fact,{...fact,value:'1'}],docs).failed_facts,1);
});
test('movement or source dimensions cannot make gross and net liability concepts appear safely separated',()=>{
 const netGold={...gold,id:'net',source_row_label:'合计',raw_value:'4.00',value:'4',concept:'net',definition_regex:'长期|net'};
 const netFact={...fact,metric:'lease_gross',label:'长期租赁负债',value:'4',raw_value:'4.00',dimensions:{movement:'closing_balance'},source_ref:{...fact.source_ref,row:3,text:'合计 | 4.00'}};
 const relations=[{id:'maturity',company_id:'test',concepts:['gross','net']}];
 const bad=scoreHoldout([gold,netGold],relations,[fact,netFact],docs);assert.equal(bad.passed_facts,2);assert.equal(bad.failed_relations,1);
 const good=scoreHoldout([gold,netGold],relations,[fact,{...netFact,metric:'lease_noncurrent'}],docs);assert.equal(good.failed_relations,0);
});

test('held-out scale, parentheses and quarter bounds are source-declared rather than inferred from the prediction',()=>{
 const quarterly={...gold,id:'quarter',source_row_label:'测试信用损失',raw_value:'(8,753)',value:'-8753000000',concept:'credit_loss',definition_regex:'信用损失',period:'2025-Q2',period_start:'2025-04-01',period_end:'2025-06-30',raw_unit_values:['人民币百万元','百万元']};
 const quarterlyFact={...fact,metric:'credit_loss',label:'测试信用损失',raw_value:'(8,753)',value:'-8753000000',raw_unit:'人民币百万元',period:quarterly.period,period_start:quarterly.period_start,period_end:quarterly.period_end,source_ref:{...fact.source_ref,text:'测试信用损失 | (8,753)'}};
 assert.equal(scoreHoldout([quarterly],[],[quarterlyFact],docs).passed_facts,1);
 for(const patch of [{value:'-8753'},{value:'8753000000'},{raw_unit:'元'},{period_start:'2025-01-01'},{period:'2025-H1'},{version:'restated'}])assert.equal(scoreHoldout([quarterly],[],[{...quarterlyFact,...patch}],docs).failed_facts,1);
});

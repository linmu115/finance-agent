import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent host-only ESM scorer.
import {scoreFinancialTables,validateReviewBinding,signature} from '../scripts/score_financial_tables_v05.mjs';
const cell={id:'a',role:'fact',input_file:'x.pdf',page:1,table_id:'independent-a',glyph_bbox:[110,110,140,120],source_row_label:'归属于上市公司股东的净利润',metric:'net_profit_parent',raw_value:'9,007,199,254,740,992.01',value:'9007199254740992.01',currency:'CNY',raw_unit_values:['元'],period:'2025',period_start:'2025-01-01',period_end:'2025-12-31',scope:'consolidated_CAS',version:'original'};
const make=(patch:any={})=>({fact_id:'f',document_id:'d',metric:cell.metric,label:cell.source_row_label,raw_value:cell.raw_value,value:cell.value,currency:'CNY',normalized_unit:'CNY',raw_unit:'元',period:cell.period,period_start:cell.period_start,period_end:cell.period_end,scope:cell.scope,version:'original',source_ref:{document_id:'d',page:1,bbox:[100,100,150,130],text:'归属于上市公司股东',normalization:{engine:'LangExtract',char_interval:[0,10]}},...patch});
const docs=[{file:'x.pdf',id:'d'}],suite=(cells:any[]=[cell])=>({tables:[{id:'independent-a',input_file:'x.pdf',page:1,bbox:[50,50,300,300],complete:true}],cells});
test('v05 uses original glyph geometry despite wrapped labels and independently detects exact cents, scale and scope',()=>{
 assert.equal(scoreFinancialTables(suite(),[make()],docs).passed_facts,1);
 const general=make({source_ref:{...make().source_ref,normalization:undefined}});assert.equal(scoreFinancialTables(suite(),[general],docs).passed_facts,1);
 for(const patch of [{value:'9007199254740992.02'},{value:'900719925474.099201'},{scope:'parent_CAS'},{raw_unit:'万元'},{period:'2024'},{currency:'USD'}]){
  const result=scoreFinancialTables(suite(),[make(patch)],docs);assert.equal(result.score.missing,0);assert.equal(result.score.wrong,1);assert.equal(result.score.major_error_count,1);
 }
 const wrongSource=make({source_ref:{...make().source_ref,bbox:[210,210,240,220]}});
 const missed=scoreFinancialTables(suite(),[wrongSource],docs);assert.equal(missed.score.missing,1);assert.equal(missed.score.false_extras,1);
});
test('v05 percent display contract does not forgive wrong ratio, currency or scale',()=>{
 const percentage={...cell,metric:'roe',value:'7.25',raw_value:'7.25%',currency:'percent',raw_unit_values:['%']};
 const fact=make({metric:'roe',value:'7.25',raw_value:'7.25%',currency:'percent',normalized_unit:'%',raw_unit:'%'});
 assert.equal(scoreFinancialTables(suite([percentage]),[fact],docs).passed_facts,1);
 for(const patch of [{value:'0.0725'},{normalized_unit:'percent'},{currency:'CNY'}])assert.equal(scoreFinancialTables(suite([percentage]),[{...fact,...patch}],docs).failed_facts,1);
 const points={...percentage,value:'2.84',raw_value:'增加2.84个百分点',unit_kind:'percentage_points',raw_unit_values:['个百分点'],definition_regex:'百分点'};
 const pointsFact={...fact,value:'2.84',raw_value:'2.84',raw_unit:'个百分点',unit_kind:'percentage_points',definition:'净资产收益率同比增加的百分点'};
 assert.equal(scoreFinancialTables(suite([points]),[pointsFact],docs).passed_facts,1);
 assert.equal(scoreFinancialTables(suite([points]),[{...pointsFact,unit_kind:'ratio_percent'}],docs).failed_facts,1);
});
test('whole-table precision penalizes fabricated header facts, missing cells and duplicates; ambiguous equal tokens cannot cover two cells',()=>{
 const second={...cell,id:'b',glyph_bbox:[210,110,240,120]},header={id:'h',role:'header',reason:'year header, not a financial observation',input_file:'x.pdf',page:1,table_id:'independent-a',glyph_bbox:[110,60,140,70]};
 const fact=make(),duplicate=make({fact_id:'dup'}),year=make({value:'2025',raw_value:'2025',source_ref:{...fact.source_ref,bbox:[100,55,150,75]}});
 const result=scoreFinancialTables(suite([cell,second,header]),[fact,duplicate,year],docs);
 assert.equal(result.score.correct,1);assert.equal(result.score.missing,1);assert.equal(result.score.false_extras,2);assert.equal(result.score.precision,1/3);
 const broad=make({source_ref:{...fact.source_ref,bbox:[90,100,250,130]}});
 const ambiguous=scoreFinancialTables(suite([cell,second]),[broad],docs);assert.equal(ambiguous.score.correct,0);assert.equal(ambiguous.score.missing,2);assert.equal(ambiguous.ambiguous_sources.length,1);
 const conflict=scoreFinancialTables(suite(),[fact,make({value:'1'})],docs);assert.equal(conflict.passed_facts,0);assert.equal(conflict.false_extras[0].reason,'conflicting_duplicate');
});
test('definition review can supersede an alias only with same-source actual-call/history proof',()=>{
 const review={status:'reviewed',engine:'LangExtract',source_key:'key',source_fingerprint:'fp',original_extraction_hash:'orig',owner_run_id:'owner',extraction_processing_id:'processing',before:{metric:'old',label:'旧定义'},after:{metric:'lease_all',label:'含流动部分租赁负债',definition:'包含一年内到期部分',definition_scope:'current_and_noncurrent'},grounded_quotes:[{evidence_id:'e',text:'包含一年内到期部分'}]};
 const fact=make({...review.after,canonical_alias:null,definition_review:review,source_ref:{...make().source_ref,normalization:{...make().source_ref.normalization,source_key:'key',source_fingerprint:'fp',original_extraction_hash:'orig',definition_review:review}}});
 const proof={kind:'definition',status:'passed',source_key:'key',source_fingerprint:'fp',review_sha256:signature(review),request_id:'actual',owner_run_id:'owner',processing_id:'processing',original_extraction_hash:'orig',extraction_signature:'signed',before_history_verified:true,quotes_verified:true};
 assert.equal(validateReviewBinding(fact,[proof]).status,'passed');
 for(const patch of [{owner_run_id:'other'},{source_fingerprint:'stale'},{original_extraction_hash:'forged'},{quotes_verified:false},{before_history_verified:false}])assert.equal(validateReviewBinding(fact,[{...proof,...patch}]).status,'failed');
 assert.equal(validateReviewBinding(fact,[]).status,'failed');
 assert.equal(validateReviewBinding({...fact,definition_scope:'noncurrent'},[proof]).status,'failed');
 const g={...cell,metric:null,definition_regex:'包含一年内到期部分',definition_forbidden_regex:'明确排除流动部分'};
 assert.equal(scoreFinancialTables(suite([g]),[fact],docs,{reviewProofs:[proof],requireReviewProof:true}).passed_facts,1);
 assert.equal(scoreFinancialTables(suite([g]),[{...fact,definition:'明确排除流动部分'}],docs).failed_facts,1);
});

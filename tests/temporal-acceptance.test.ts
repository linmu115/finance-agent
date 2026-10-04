import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent host-only ESM acceptance helper.
import {compareFinancialSnapshots} from '../scripts/compare_financial_snapshots.mjs';
// @ts-expect-error Independent host-only ESM acceptance helpers.
import {extractionEvidence,temporalAcceptance} from '../scripts/validation_utils.mjs';
// @ts-expect-error Independent host-only ESM acceptance helper.
import {summarizeTemporalTargets} from '../scripts/temporal_evidence.mjs';
const fact={fact_id:'old-id',document_id:'doc',metric:'ending_cash_balance',original_metric:'ending_cash_balance',company:'测试公司',scope:'consolidated_CAS',currency:'CNY',value:'9007199254740992.01',raw_value:'9007199254740992.01',raw_unit:'元',normalized_unit:'CNY',period:'2024-FY',period_start:'2024-01-01',period_end:'2024-12-31',year:2024,dimensions:{},source_ref:{document_id:'doc',table_id:'doc:t5',row:3,column:2,page:84,cell:'B3',text:'期末现金及现金等价物余额 | 9007199254740992.01'}};
test('period review may correct dates and recreate fact IDs while preserving the exact source and money',()=>{
 const after={...fact,fact_id:'new-id',period:'2024-12-31',period_start:'',value:'9007199254740992.010',source_ref:{...fact.source_ref,normalization:{temporal_correction:{before:{period:'2024-FY',start:'2024-01-01',end:'2024-12-31'},after:{period:'2024-12-31',start:'',end:'2024-12-31'}}}}};
 const result=compareFinancialSnapshots([fact],[after]);assert.equal(result.status,'passed');assert.equal(result.period_changes.length,1);assert.equal(result.changed_immutable_values.length,0);
});
test('period review cannot hide changed cents, currency, raw units or dropped source facts',()=>{
 for(const patch of [{value:'9007199254740992.02'},{currency:'USD'},{raw_unit:'万元'},{raw_value:'1'}])assert.equal(compareFinancialSnapshots([fact],[{...fact,...patch}]).status,'failed');
 assert.equal(compareFinancialSnapshots([fact],[]).status,'failed');
 assert.equal(compareFinancialSnapshots([fact],[fact,fact]).status,'failed');
 assert.equal(compareFinancialSnapshots([fact],[{...fact,period:'2024-12-31',period_start:''}]).status,'failed','a date change without matching correction evidence must not pass');
 assert.equal(compareFinancialSnapshots([],[]).status,'failed','empty snapshots cannot prove a semantic correction preserved data');
});
test('a source-backed recovery allowlist permits only the exact additional facts and never masks edits to old values',()=>{
 const recovered={...fact,metric:'previously_rejected_metric',original_metric:'previously_rejected_metric',source_ref:{...fact.source_ref,row:6,cell:'B6'}};
 const result=compareFinancialSnapshots([fact],[fact,recovered],[recovered]);assert.equal(result.status,'passed');assert.equal(result.expected_additions[0].passed,true);
 for(const after of [[fact],[fact,{...recovered,value:'1'}],[fact,recovered,recovered],[{...fact,value:'2'},recovered]])assert.equal(compareFinancialSnapshots([fact],after,[recovered]).status,'failed');
 assert.equal(compareFinancialSnapshots([fact],[fact,fact],[fact]).status,'failed','an existing fact cannot be disguised as an approved recovery');
});
test('temporal acceptance requires actual owning Pi output; zero candidates do not require fabricated corrections',()=>{
 const summary={status:'reviewed',facts_total:1,facts_reviewable:1,coverage_snapshot_valid:true,current_fact_count:1,profiles_total:1,profiles_reviewed:1,candidate_groups:0,sources_targeted:0,unresolved:[],unreviewable:[],stale_sources:[],pending_new_sources:[]};
 const attributes={period:'2024-12-31',start:'',end:'2024-12-31',reason:'期末余额为时点。',evidence:'期末现金及现金等价物余额'};
 const events=[{type:'extraction_request',data:{requestId:'t',ownerRunId:'owner',runtime:'Pi.ModelRuntime'}},{type:'extraction_result',data:{requestId:'t',ownerRunId:'owner',stopReason:'stop',content:JSON.stringify({extractions:[{temporal_review:'[[TEMPORAL_REVIEW]]',temporal_review_attributes:{reviewed_count:1,flag_count:1,keep_count:0}},{temporal_correction:'[[SOURCE:cash_cell]]',temporal_correction_attributes:{...attributes,reason:' '+attributes.reason+' '}}]})}}];
 const proof={run_id:'owner',...extractionEvidence(events,'owner')};
 assert.equal(temporalAcceptance(summary,[fact],[proof]).status,'passed');
 assert.equal(temporalAcceptance(summary,[fact],[]).status,'failed');
 assert.equal(temporalAcceptance({...summary,coverage_snapshot_valid:false},[fact],[proof]).status,'failed','a late review of an older subset must not pass as current coverage');
 const corrected={...fact,period:attributes.period,period_start:'',source_ref:{...fact.source_ref,normalization:{temporal_correction:{status:'reviewed',engine:'LangExtract',source_key:'cash_cell',source_fingerprint:'source-hash',original_extraction_hash:'original-hash',span:[10,30],owner_run_id:'owner',before:{period:'2024-FY',start:'2024-01-01',end:'2024-12-31'},after:{period:attributes.period,start:'',end:attributes.end},reason:attributes.reason,evidence:attributes.evidence}}}};
 const withCandidate={...summary,candidate_groups:1,sources_targeted:1};
 assert.equal(temporalAcceptance(withCandidate,[corrected],[proof]).status,'passed');
 assert.equal(temporalAcceptance(withCandidate,[{...corrected,period:'2023-12-31'}],[proof]).status,'failed');
 assert.equal(temporalAcceptance(withCandidate,[corrected],[{...proof,run_id:'other-owner'}]).status,'failed');
 assert.equal(temporalAcceptance({...summary,unresolved:[{source_key:'cash_cell'}]},[fact],[proof]).status,'failed');
});

test('resuming unresolved sources counts unique coverage while retaining every earlier review event',()=>{
 const first={phase:'corrections',audit:{source_count:2},cached:{corrections:[{source_key:'a'}],unresolved:[{source_key:'b'}]}};
 const resumed={phase:'corrections',audit:{source_count:1,source_keys:['b']},cached:{corrections:[{source_key:'b'}],unresolved:[]}};
 const report={review:{target_source_keys:['a','b']},chunks:[first,resumed]};
 assert.deepEqual(summarizeTemporalTargets(report),{unique_source_count:2,review_event_count:3,source_keys:['a','b'],errors:[]});
 assert.ok(summarizeTemporalTargets({...report,chunks:[first,{...resumed,audit:{source_count:1,source_keys:['wrong']}}]}).errors.length);
 assert.ok(summarizeTemporalTargets({...report,review:{target_source_keys:['a','b','missing']}}).errors.length);
});

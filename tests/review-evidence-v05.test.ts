import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent host verifier.
import {validateAcceptedCache,definitionHistoryPreserved,validateNormalizationBatch} from '../scripts/review_evidence_v05.mjs';
// @ts-expect-error independent host signature
import {signature} from '../scripts/score_financial_tables_v05.mjs';
test('accepted cache must retain complete payload hash and owner, and all extractions must come from one actual response',()=>{
 const first={class:'temporal_review',text:'[[CATALOG]]',attributes:{reviewed_count:1}},second={class:'temporal_candidate',text:'[[GROUP:g]]',attributes:{reason:'source statement'}};
 const packet={computed_result_hash:'immutable-content',payload:{_review_provenance:{owner_run_id:'owner',processing_id:'p'},extractions:[first,second]}};
 const audit={result_hash:'immutable-content',source_provenance:{owner_run_id:'owner',processing_id:'p'}};
 const request=(id:string)=>({type:'extraction_request',data:{requestId:id,ownerRunId:'owner',runtime:'Pi.ModelRuntime',messages:[{content:'[[GROUP:g]] original source'}]}});
 const result=(id:string,items:any[])=>({type:'extraction_result',data:{requestId:id,ownerRunId:'owner',stopReason:'stop',content:JSON.stringify({extractions:items.map(e=>({extraction_class:e.class,extraction_text:e.text,attributes:e.attributes}))})}});
 assert.equal(validateAcceptedCache(packet,audit,[request('r'),result('r',[first,second])]).status,'passed');
 assert.equal(validateAcceptedCache(packet,{...audit,result_hash:'other'},[request('r'),result('r',[first,second])]).status,'failed');
 assert.equal(validateAcceptedCache(packet,{...audit,source_provenance:{owner_run_id:'overwritten',processing_id:'p'}},[request('r'),result('r',[first,second])]).status,'failed');
 assert.equal(validateAcceptedCache(packet,audit,[request('r1'),result('r1',[first]),request('r2'),result('r2',[second])]).status,'failed');
 const failed=result('r',[first,second]);failed.data.stopReason='length';assert.equal(validateAcceptedCache(packet,audit,[request('r'),failed]).status,'failed');
});

test('normalization table repair accepts same-owner composite responses but rejects fabricated rows and a different owner',()=>{
 const schema={class:'table_schema',text:'[[T8]]',attributes:{unit:'元'}},row={class:'financial_row',text:'[[T8:R2]]',attributes:{metric:'revenue'}};
 const batch={document_id:'d',batch_key:'b',processing_id:'p',result:{coordinates:[['d:t8',2]],extractions:[schema,row]}};
 const request=(id:string,owner='o')=>({type:'extraction_request',data:{requestId:id,ownerRunId:owner,runtime:'Pi.ModelRuntime',messages:[{content:'[[T8]] table\n[[T8:R2]] source row'}]}});
 const response=(id:string,ex:any,owner='o')=>({type:'extraction_result',data:{requestId:id,ownerRunId:owner,stopReason:'stop',content:JSON.stringify({extractions:[{extraction_class:ex.class,extraction_text:ex.text,attributes:ex.attributes}]})}});
 const events=[request('initial'),response('initial',schema),request('repair'),response('repair',row)];
 assert.equal(validateNormalizationBatch(batch,'o',events).status,'passed');
 assert.equal(validateNormalizationBatch(batch,'o',events.slice(0,2)).status,'failed');
 assert.equal(validateNormalizationBatch(batch,'o',[...events.slice(0,2),request('other','not-owner'),response('other',row,'not-owner')]).status,'failed');
 assert.equal(validateNormalizationBatch({...batch,result:{...batch.result,coordinates:[['d:t8',3]]}},'o',events).status,'failed');
});

test('definition history permits only independently proved later date change, preserving all source and financial values',()=>{
 const meta={label:'原指标',dimensions:{channel:'直销'},source_key:'s',source_fingerprint:'fingerprint',original_extraction_hash:'original',period_start:'2024-01-01',period_end:'2024-12-31'};
 const ref={document_id:'doc',page:2,table_id:'doc:t1',row:2,column:3,text:'原表',bbox:[1,2,3,4],normalization:meta};
 const old={metric:'old',value:'123456789012345.67',raw_value:'123456789012345.67',raw_unit:'元',currency:'CNY',scope:'consolidated_CAS',company:'公司',period:'2024',source_json:JSON.stringify(ref)};
 const fact:any={...old,metric:'new',source_ref:structuredClone(ref)};
 const review={before:{metric:'old',label:'原指标'}};
 assert.equal(definitionHistoryPreserved(old,fact,review),true);
 const correction={status:'reviewed',source_key:'s',source_fingerprint:'fingerprint',original_extraction_hash:'original',before:{period:'2024',start:'2024-01-01',end:'2024-12-31'},after:{period:'2024-12-31',start:'2024-12-31',end:'2024-12-31'}};
 fact.period='2024-12-31';Object.assign(fact.source_ref.normalization,{period_start:'2024-12-31',temporal_correction:correction});
 assert.equal(definitionHistoryPreserved(old,fact,review),false);
 const proof={status:'passed',review_sha256:signature(correction)};assert.equal(definitionHistoryPreserved(old,fact,review,proof),true);
 assert.equal(definitionHistoryPreserved(old,{...fact,value:'123456789012345.68'},review,proof),false);
 fact.source_ref.normalization.temporal_correction.source_fingerprint='different';assert.equal(definitionHistoryPreserved(old,fact,review,proof),false);
});

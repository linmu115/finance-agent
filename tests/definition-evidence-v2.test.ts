import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent host-side validator.
import {expectedQuoteLocation,definitionInput,validateDefinitionCacheV2,validateDefinitionSnapshotV2,validateHistoricalDefinitionLimit} from '../scripts/definition_evidence_v2.mjs';
// @ts-expect-error Independent validation utilities.
import {digest,stableJson} from '../scripts/validation_utils.mjs';
// @ts-expect-error Independent pre-first-run workflow verifier.
import {validateAcceptedDefinitionCache} from '../scripts/review_evidence_v05.mjs';

function fixture({moved=false,whitespace=false}={}){
 const source='𠮷💡本表为普通\n股股本明细',quote={evidence_id:moved?'wrong':'own',text:whitespace?'普通股股本':'普通\n股股本'};
 const evidence=new Map([['own',source]]),located=expectedQuoteLocation(quote,evidence);
 const text='[[KNOWN_METRICS]] []\n[[EVIDENCE_CONTEXT:E1]] '+stableJson({text:source})+'\n[[DEFINITION:g]] '+stableJson({group_id:'g',evidence:[{evidence_id:'own',text_ref:'E1'}]});
 const marker='[[DEFINITION:g]]',start=Array.from(text.slice(0,text.indexOf(marker))).length;
 const decision={group_id:'g',metric:'ordinary_share_capital',label:'普通股股本',definition:'普通股份面值合计',definition_scope:'普通股',reason:'原表明确分类',grounded_quotes:[located.quote],quote_alignments:located.alignment?[{quote_index:0,...located.alignment}]:[],span:[start,start+marker.length]};
 const ex={class:'definition_decision',text:marker,span:decision.span,attributes:{metric:decision.metric,label:decision.label,definition:decision.definition,definition_scope:decision.definition_scope,reason:decision.reason,grounded_quotes_json:JSON.stringify([quote])}};
 const cache={decisions:[decision],unresolved:[],extractions:[ex],attempts:[{group_ids:['g'],input_hash:digest(text),extractions:[ex]}],_review_provenance:{owner_run_id:'owner',processing_id:'processing'}};
 const events=[{type:'processing_started',data:{ownerRunId:'owner',processingId:'processing'}},{type:'extraction_request',data:{requestId:'r',ownerRunId:'owner',runtime:'Pi.ModelRuntime',messages:[{role:'user',content:'Question\nQ: '+text+'\nA: '}]}},{type:'extraction_result',data:{requestId:'r',ownerRunId:'owner',stopReason:'stop',content:JSON.stringify({extractions:[{extraction_class:ex.class,extraction_text:ex.text,attributes:ex.attributes}]})}}];
 return {source,quote,evidence,text,decision,ex,cache,events};
}
test('v2 verifies unchanged exact quotations and same-group whitespace/id repair with Unicode codepoint spans',()=>{
 for(const options of [{},{whitespace:true},{moved:true},{moved:true,whitespace:true}]){
  const f=fixture(options),result=validateDefinitionCacheV2(f.cache,f.events);
  assert.equal(result.status,'passed',JSON.stringify(result));
  const packet={payload:f.cache,computed_result_hash:digest(f.cache)},audit={result_hash:digest(f.cache),provenance:f.cache._review_provenance};
  assert.equal(validateAcceptedDefinitionCache(packet,audit,f.events).status,'passed');
  assert.equal(validateAcceptedDefinitionCache(packet,{...audit,result_hash:'replaced'},f.events).status,'failed');
  assert.equal(validateAcceptedDefinitionCache(packet,{...audit,provenance:{owner_run_id:'foreign',processing_id:'processing'}},f.events).status,'failed');
  assert.equal(definitionInput(f.events[1].data.messages).text,f.text);
 }
 const f=fixture({moved:true,whitespace:true}),alignment=f.decision.quote_alignments[0];
 assert.equal(alignment.span[0],5); // 𠮷 and 💡 are one codepoint each.
 alignment.span[0]+=2;assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'failed');
});
test('v2 rejects ambiguous location, punctuation/word changes, cross-group evidence and fabricated repair audit',()=>{
 assert.equal(expectedQuoteLocation({evidence_id:'unknown',text:'股本'},new Map([['a','股本'],['b','股本']])).error,'ambiguous_group');
 assert.equal(expectedQuoteLocation({evidence_id:'a',text:'普通股'},new Map([['a','普通 股 普通\n股']])).error,'ambiguous_same_evidence');
 assert.ok(expectedQuoteLocation({evidence_id:'a',text:'不包含普通股'},new Map([['a','包含普通股']])).error);
 assert.ok(expectedQuoteLocation({evidence_id:'a',text:'普通股，合计'},new Map([['a','普通股、合计']])).error);
 const f=fixture({moved:true});f.decision.quote_alignments=[];assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'failed');
 const g=fixture();g.decision.grounded_quotes[0]={evidence_id:'outside',text:'普通\n股股本'};assert.equal(validateDefinitionCacheV2(g.cache,g.events).status,'failed');
});
test('v2 preserves model semantics and original owner, rejects altered raw output, input hash, marker and length failures',()=>{
 for(const mutate of [
  f=>f.decision.metric='preferred_share_capital',
  f=>f.events[1].data.ownerRunId='foreign',
  f=>f.cache._review_provenance.processing_id='foreign',
  f=>f.ex.attributes.definition_scope='changed',
  f=>f.cache.attempts[0].input_hash='forged',
  f=>f.ex.span=[0,16],
  f=>f.events[2].data.stopReason='length',
 ]){const f=fixture();mutate(f);assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'failed');}
});
function savedFixture(){
 const f=fixture(),ref={document_id:'doc',page:1,table_id:'t1',row:2,column:2,cell:'B2',normalization:{source_key:'source',source_fingerprint:'fingerprint',original_extraction_hash:'originalhash',label:'旧股本',period_start:'',period_end:'2025-12-31',dimensions:{}}};
 const before={fact_id:'fact',metric:'old_equity',value:'100',raw_value:'100',raw_unit:'元',currency:'CNY',period:'2025-12-31',year:2025,scope:'consolidated_CAS',company:'测试公司',source_json:JSON.stringify(ref)};
 const review={review_id:'review',engine:'LangExtract',status:'reviewed',source_key:'source',source_fingerprint:'fingerprint',original_extraction_hash:'originalhash',owner_run_id:'owner',extraction_processing_id:'processing',cache_key:'key',result_hash:digest(f.cache),group_id:'g',before:{metric:before.metric,label:'旧股本'},after:Object.fromEntries(['metric','label','definition','definition_scope'].map(k=>[k,f.decision[k]])),reason:f.decision.reason,grounded_quotes:f.decision.grounded_quotes,quote_alignments:[]};
 ref.normalization.label=f.decision.label;ref.normalization.definition_review=review;
 const after={...before,metric:f.decision.metric,source_json:JSON.stringify(ref)};
 const saved={source:'fixture',facts:[after],caches:{key:f.cache},cache_hashes:{key:digest(f.cache)},histories:[{history_id:'history',processing_id:'processing',fact:before}],reviews:[]};
 return {f,saved,review};
}
test('v2 discovers historical committed facts even without terminal report, while explicitly failing missing registration',()=>{
 const {f,saved}=savedFixture(),owners=new Map([['owner',f.events]]);
 let result=validateDefinitionSnapshotV2(saved,owners);
 assert.equal(result.provenance.passed,1);assert.equal(result.partial_batch_registration.passed,0);assert.equal(result.status,'failed');
 saved.reviews.push({review_id:'review',status:'failed',processing_id:'processing',audits:[{cache_key:'key',result_hash:digest(f.cache),group_count:1,provenance:f.cache._review_provenance}]});
 result=validateDefinitionSnapshotV2(saved,owners);assert.equal(result.status,'passed');
 assert.equal(result.partial_batch_registration.checks[0].report_status,'failed'); // This says persistence, not overall workflow success.
 saved.reviews[0].audits[0].result_hash='replaced';assert.equal(validateDefinitionSnapshotV2(saved,owners).status,'failed');
});
test('v2 detects money/date/source changes and rejects absent archive or cache-owner mismatch',()=>{
 for(const mutate of [
  s=>s.facts[0].value='101',s=>s.facts[0].period='2024-12-31',s=>s.histories=[],
  s=>s.cache_hashes.key='changed',
  s=>{const r=JSON.parse(s.facts[0].source_json);r.page=2;s.facts[0].source_json=JSON.stringify(r);},
 ]){const {f,saved}=savedFixture();mutate(saved);assert.equal(validateDefinitionSnapshotV2(saved,new Map([['owner',f.events]])).provenance.status,'failed');}
});
test('v2 distinguishes a later explicit revalidation from the permanently absent historical registration',()=>{
 const {f,saved}=savedFixture(),owners=new Map([['owner',f.events]]);
 saved.reviews.push({review_id:'later-review',status:'reviewed',processing_id:'later-processing',source_fingerprints:{source:'fingerprint'},audits:[{cache_key:'key',result_hash:digest(f.cache),group_count:1,provenance:f.cache._review_provenance,kind:'revalidated_cached_result',revalidated_source_keys:['source'],historical_review_ids:['review'],original_registration_missing:true}]});
 let result=validateDefinitionSnapshotV2(saved,owners);assert.equal(result.status,'passed');
 const check=result.partial_batch_registration.checks[0];assert.equal(check.original_registration_missing,true);assert.equal(check.current_revalidation_registration_exists,true);assert.deepEqual(check.current_revalidation_review_ids,['later-review']);
 saved.reviews[0].source_fingerprints.source='other';result=validateDefinitionSnapshotV2(saved,owners);assert.equal(result.partial_batch_registration.status,'failed');
 saved.reviews[0].source_fingerprints.source='fingerprint';saved.reviews[0].audits[0].historical_review_ids=[];assert.equal(validateDefinitionSnapshotV2(saved,owners).partial_batch_registration.status,'failed');
 saved.reviews[0].audits[0].historical_review_ids=['review'];saved.reviews[0].audits[0].revalidated_source_keys=[];assert.equal(validateDefinitionSnapshotV2(saved,owners).partial_batch_registration.status,'failed');
});
test('partial accepted definition cache proves the original input and real length attempt without accepting unfinished groups',()=>{
 const f=fixture(),full=f.text+'\n[[DEFINITION:h]] '+stableJson({group_id:'h',evidence:[{evidence_id:'own',text_ref:'E1'}]}),pending=f.text.replace('[[DEFINITION:g]]','[[DEFINITION:h]]').replace('"group_id":"g"','"group_id":"h"');
 f.events[1].data.messages[0].content='Q: '+full+'\nA: ';
 f.events.push({type:'extraction_request',data:{requestId:'limited',ownerRunId:'owner',runtime:'Pi.ModelRuntime',messages:[{role:'user',content:'Q: '+pending+'\nA: '}]}},{type:'extraction_result',data:{requestId:'limited',ownerRunId:'owner',stopReason:'length',content:''}});
 f.cache.partial_coverage={original_group_ids:['g','h'],pending_group_ids:['h']};
 f.cache.attempts=[{group_ids:['g','h'],input_hash:digest(full),extractions:[f.ex]},{outcome:'output_limit',group_ids:['h'],input_hash:digest(pending),extractions:[],bridge_error:{code:'model_output_limit',stop_reason:'length',request_id:'limited'}}];
 assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'passed');
 const copied=structuredClone(f.cache);copied.partial_coverage.pending_group_ids=['g'];assert.equal(validateDefinitionCacheV2(copied,f.events).status,'failed');
 f.events[4].data.stopReason='error';assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'failed');
 f.events[4].data.stopReason='length';f.cache.attempts[1].bridge_error.request_id='fabricated';assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'failed');
});
test('historical limit is bound to immutable original audit/config/source/usage and zero-call exact split, never a new successful result',()=>{
 const f=fixture(),text=f.text+'\n[[DEFINITION:h]] '+stableJson({group_id:'h',evidence:[{evidence_id:'own',text_ref:'E1'}]});
 f.events[0].data.documentIds=['document'];Object.assign(f.events[1].data,{model:'test-model',reasoningEffort:'high',maxTokens:32768});f.events[1].data.messages[0].content='Q: '+text+'\nA: ';Object.assign(f.events[2].data,{stopReason:'length',content:'',usage:{input:100,output:32768,reasoning:32768}});
 const entry={kind:'verified_historical_output_limit',policy_version:'verified-historical-output-limit-1',cache_key:'cache',group_ids:['g','h'],original_review_id:'old-review',original_owner_run_id:'owner',original_processing_id:'processing',original_request_id:'r',audit_sha256:'immutable-bytes',input_hash:digest(text),messages_hash:digest(f.events[1].data.messages),source_fingerprints:{source:'fingerprint'},model:'test-model',reasoning_effort:'high',max_tokens:32768,stop_reason:'length',historical_usage:f.events[2].data.usage,current_model_requests:0};
 const context={events:f.events,auditSha256:'immutable-bytes',reviews:[{review_id:'old-review',owner_run_id:'owner',processing_id:'processing',source_fingerprints:{source:'fingerprint'}}],currentFingerprints:{source:'fingerprint'},projectDocumentIds:['document'],split:{children:[['g'],['h']],model_requests:0}};
 assert.equal(validateHistoricalDefinitionLimit(entry,context).status,'passed');
 for(const mutate of [e=>e.messages_hash='altered',e=>e.original_owner_run_id='foreign',e=>e.historical_usage={input:0,output:0},e=>e.current_model_requests=1,e=>e.input_hash='altered',e=>e.max_tokens=64000,e=>e.source_fingerprints.source='changed']){const clone=structuredClone(entry);mutate(clone);assert.equal(validateHistoricalDefinitionLimit(clone,context).status,'failed');}
 assert.equal(validateHistoricalDefinitionLimit(entry,{...context,events:[...f.events,f.events[2]]}).status,'failed');
 assert.equal(validateHistoricalDefinitionLimit(entry,{...context,split:{children:[['g'],['g']],model_requests:0}}).status,'failed');
 assert.equal(validateHistoricalDefinitionLimit(entry,{...context,projectDocumentIds:['other-project-document']}).status,'failed');
});
test('v2 accepts recorded same-owner partial repair across responses without requiring a fictitious single response',()=>{
 const f=fixture(),secondGroup={group_id:'h',evidence:[{evidence_id:'own',text_ref:'E1'}]},firstText=f.text+'\n[[DEFINITION:h]] '+stableJson(secondGroup);
 const secondText=f.text.replace('[[DEFINITION:g]]','[[DEFINITION:h]]').replace('"group_id":"g"','"group_id":"h"');
 const hMarker='[[DEFINITION:h]]',hStart=Array.from(firstText.slice(0,firstText.indexOf(hMarker))).length;
 const hEx={...f.ex,text:hMarker,span:[hStart,hStart+hMarker.length],attributes:{...f.ex.attributes,label:'普通股资本'}};
 const hDecision={...f.decision,group_id:'h',label:'普通股资本',span:hEx.span};
 const badH={...hEx,attributes:{...hEx.attributes,grounded_quotes_json:'[]'}};
 f.events[1].data.messages[0].content='Q: '+firstText+'\nA: ';
 f.events[2].data.content=JSON.stringify({extractions:[f.ex,badH].map(ex=>({extraction_class:ex.class,extraction_text:ex.text,attributes:ex.attributes}))});
 f.events.push({type:'extraction_request',data:{requestId:'repair',ownerRunId:'owner',runtime:'Pi.ModelRuntime',messages:[{role:'user',content:'Q: '+secondText+'\nA: '}]}},{type:'extraction_result',data:{requestId:'repair',ownerRunId:'owner',stopReason:'stop',content:JSON.stringify({extractions:[{extraction_class:hEx.class,extraction_text:hEx.text,attributes:hEx.attributes}]})}});
 f.cache.decisions.push(hDecision);f.cache.extractions.push(hEx);
 f.cache.attempts=[{group_ids:['g','h'],input_hash:digest(firstText),extractions:[f.ex,badH]},{group_ids:['h'],input_hash:digest(secondText),extractions:[hEx]}];
 const result=validateDefinitionCacheV2(f.cache,f.events);assert.equal(result.status,'passed',JSON.stringify(result));
 assert.equal(validateAcceptedDefinitionCache({payload:f.cache,computed_result_hash:digest(f.cache)},{result_hash:digest(f.cache),provenance:f.cache._review_provenance},f.events).status,'passed');
 f.events[3].data.ownerRunId='foreign';assert.equal(validateDefinitionCacheV2(f.cache,f.events).status,'failed');
});

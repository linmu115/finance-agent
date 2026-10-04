// Independent host verifier for immutable review winners and their actual calls.
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {extractionEvidence,extractionSignature,temporalAcceptance} from './validation_utils.mjs';
import {validateDefinitionCacheV2} from './definition_evidence_v2.mjs';
import {validateReviewBinding,signature,exactDecimal} from './score_financial_tables_v05.mjs';
const root=path.resolve(import.meta.dirname,'..'),execute=promisify(execFile);
const stable=v=>JSON.stringify(v),same=(a,b)=>signature(a)===signature(b);
const flatten=messages=>messages.flatMap(m=>typeof m.content==='string'?[m.content]:Array.isArray(m.content)?m.content.filter(p=>p.type==='text').map(p=>p.text):[]).join('\n');
export function validateAcceptedCache(packed,audit,events){
 const cache=packed?.payload,owner=cache?._review_provenance?.owner_run_id,errors=[];
 if(!cache||!owner)return {status:'failed',errors:['cache_or_owner_missing'],matching_requests:[]};
 if(!audit.result_hash||audit.result_hash!==packed.computed_result_hash)errors.push('accepted_result_hash_changed');
 const provenance=audit.source_provenance??audit.provenance;
 if(!same(provenance,cache._review_provenance))errors.push('accepted_owner_changed');
 const requests=new Map(events.filter(e=>e.type==='extraction_request').map(e=>[e.data.requestId,e])),matches=[];
 for(const result of events.filter(e=>e.type==='extraction_result')){
  if(!['stop','toolUse'].includes(result.data.stopReason))continue;
  const request=requests.get(result.data.requestId);if(!request)continue;
  const evidence=extractionEvidence([request,result],owner);
  if(evidence.valid_owners&&(cache.extractions||[]).length&&(cache.extractions||[]).every(ex=>evidence.signatures.has(extractionSignature(ex))))matches.push({request_id:result.data.requestId,input_text:flatten(request.data.messages||[])});
 }
 if(!matches.length)errors.push('all_accepted_extractions_not_in_same_actual_pi_response');
 return {status:errors.length?'failed':'passed',errors,owner_run_id:owner,processing_id:cache._review_provenance.processing_id,result_hash:packed.computed_result_hash,matching_requests:matches};
}

// Definition repair records each attempted input/output; unchanged accepted
// groups can legitimately come from different calls of the same original owner.
// Catalog and temporal review continue to use the single-response gate above.
export function validateAcceptedDefinitionCache(packed,audit,events){
 const cache=packed?.payload,errors=[];
 if(!cache)return {status:'failed',errors:['cache_missing'],matching_requests:[],semantic:null};
 if(!audit?.result_hash||audit.result_hash!==packed.computed_result_hash)errors.push('accepted_result_hash_changed');
 if(!same(audit?.source_provenance??audit?.provenance,cache._review_provenance))errors.push('accepted_owner_changed');
 const semantic=validateDefinitionCacheV2(cache,events);
 if(semantic.status!=='passed')errors.push('definition_original_outputs_or_quote_locations');
 const ids=new Set(semantic.checks.flatMap(c=>c.matching_request_ids||[]));
 const matching_requests=events.filter(e=>e.type==='extraction_request'&&ids.has(e.data.requestId)).map(e=>({request_id:e.data.requestId,input_text:flatten(e.data.messages||[])}));
 return {status:errors.length?'failed':'passed',errors,owner_run_id:cache._review_provenance?.owner_run_id,processing_id:cache._review_provenance?.processing_id,result_hash:packed.computed_result_hash,matching_requests,semantic};
}

export function validateNormalizationBatch(batch,owner,events){
 const result=batch.result||{},errors=[],matches=[];
 if(!owner)errors.push('original_processing_owner_missing');
 if(!Array.isArray(result.extractions)||!result.extractions.length)errors.push('accepted_extractions_missing');
 const requests=new Map(events.filter(e=>e.type==='extraction_request').map(e=>[e.data.requestId,e]));
 const responses=events.filter(e=>e.type==='extraction_result'&&['stop','toolUse'].includes(e.data.stopReason)).map(response=>{
  const request=requests.get(response.data.requestId);if(!request)return null;
  return {id:response.data.requestId,evidence:extractionEvidence([request,response],owner),input:flatten(request.data.messages||[])};
 }).filter(Boolean);
 for(const extraction of result.extractions||[]){
  const signature=extractionSignature(extraction),actual=responses.filter(r=>r.evidence.valid_owners&&r.evidence.signatures.has(signature)&&r.input.includes(extraction.text));
  if(!actual.length)errors.push('extraction_without_original_owner_response:'+extraction.class+':'+extraction.text);
  matches.push({class:extraction.class,text:extraction.text,signature,request_ids:actual.map(r=>r.id)});
 }
 // Numeric headers/notes may be explicitly skipped by the grounded schema.
 // Financial completeness is scored against independent whole-table gold.
 const coordinates=new Set((result.coordinates||[]).map(([tableId,row])=>'[[T'+/:t(\d+)$/.exec(tableId)?.[1]+':R'+row+']]'));
 for(const extraction of result.extractions||[]){
  if(extraction.class==='financial_row'&&!coordinates.has(extraction.text))errors.push('accepted_row_outside_original_batch:'+extraction.text);
 }
 return {batch_key:batch.batch_key,document_id:batch.document_id,status:errors.length?'failed':'passed',owner_run_id:owner,processing_id:result.extraction_processing_id||batch.processing_id,errors,extractions:matches,
  contract:'Each accepted schema/row must occur unchanged in a successful response from the immutable original processing owner; table repair may combine multiple responses from that owner.'};
}

// Definition-only writes must preserve money, dimensions and source. A later
// separately proved temporal correction is allowed to change dates, never value.
export function definitionHistoryPreserved(old,fact,review,temporalProof=null){
 const ref=JSON.parse(old.source_json),m=ref.normalization||{},meta=fact.source_ref?.normalization||{};
 const immutable=same(review.before,{metric:old.metric,label:m.label})&&['value','raw_value','raw_unit','currency','scope','company'].every(k=>k==='value'?exactDecimal(old[k])===exactDecimal(fact[k]):old[k]===fact[k])&&['dimensions','source_key','source_fingerprint','original_extraction_hash'].every(k=>same(m[k],meta[k]))&&['document_id','page','table_id','row','column','cell','text','bbox'].every(k=>same(ref[k],fact.source_ref[k]));
 if(!immutable)return false;
 const before={period:old.period,start:m.period_start||'',end:m.period_end||''},after={period:fact.period,start:meta.period_start||'',end:meta.period_end||''};
 if(same(before,after))return true;
 const correction=meta.temporal_correction;
 return temporalProof?.status==='passed'&&temporalProof?.review_sha256===signature(correction)&&same(correction?.before,before)&&same(correction?.after,after)&&['source_key','source_fingerprint','original_extraction_hash'].every(k=>correction[k]===meta[k]);
}

export async function verifyReviewsV05(projectId,catalog,facts){
 const args=[path.join(root,'scripts/export_review_evidence_v05.py'),'--project',projectId];if(catalog.temporal_review?.review_id)args.push('--temporal-review',catalog.temporal_review.review_id);
 const {stdout}=await execute(path.join(root,'.venv/Scripts/python.exe'),args,{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:32*1024*1024});
 const saved=JSON.parse(stdout),ownerEvents=new Map();
 const events=async owner=>{if(!ownerEvents.has(owner))ownerEvents.set(owner,(await fs.readFile(path.join(root,'data/audit',owner+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse));return ownerEvents.get(owner);};
 const normalizationChecks=[];
 for(const batch of saved.normalization||[]){const origin=batch.result?.extraction_processing_id||batch.processing_id,owner=saved.processing_owners?.[origin];normalizationChecks.push(validateNormalizationBatch(batch,owner,owner?await events(owner):[]));}
 const proofs=[],catalogChecks=[],definitionChecks=[];
 for(const fact of facts){
  const meta=fact.source_ref?.normalization||{},definition=fact.definition_review??meta.definition_review,alias=fact.canonical_alias??meta.canonical_alias;
  if(definition){
   const packet=saved.definitions.caches[definition.cache_key],cache=packet?.payload,owner=cache?._review_provenance?.owner_run_id;
   const report=saved.definitions.reviews.find(r=>r.review_id===definition.review_id);
   const audit=report?.audits?.find(a=>a.cache_key===definition.cache_key&&a.result_hash===definition.result_hash);
   const proof=owner&&audit?validateAcceptedDefinitionCache(packet,audit,await events(owner)):null;
   const semantic=proof?.semantic;
   const decision=cache?.decisions?.find(d=>d.group_id===definition.group_id),history=saved.definitions.histories.find(h=>h.review_id===definition.review_id&&JSON.parse(h.fact.source_json).normalization?.source_key===meta.source_key);
   let historyOkay=false;
   if(history){
    let temporalProof=null;const correction=meta.temporal_correction;
    if(correction){
     const chunk=saved.temporal?.chunks.find(c=>c.phase==='corrections'&&c.audit.cache_key===correction.cache_key&&c.computed_result_hash===correction.result_hash),owner=chunk?.payload?._review_provenance?.owner_run_id;
     if(owner&&owner===correction.owner_run_id&&chunk.payload._review_provenance.processing_id===correction.extraction_processing_id){
      const proof=validateAcceptedCache(chunk,chunk.audit,await events(owner)),decision=chunk.payload.corrections?.find(c=>c.source_key===meta.source_key);
      if(proof.status==='passed'&&correction.status==='reviewed'&&correction.engine==='LangExtract'&&decision&&same({period:decision.period,start:decision.start,end:decision.end},correction.after)&&same(decision.evidence,correction.evidence)&&decision.reason===correction.reason)temporalProof={status:'passed',review_sha256:signature(correction)};
     }
    }
    historyOkay=definitionHistoryPreserved(history.fact,fact,definition,temporalProof);
   }
   const groupProof=semantic?.checks.find(c=>c.group_id===definition.group_id),quotesBound=decision&&same(definition.grounded_quotes,decision.grounded_quotes)&&same(definition.quote_alignments||[],decision.quote_alignments||[])&&definition.reason===decision.reason;
   definitionChecks.push({source_key:meta.source_key,review_id:definition.review_id,cache_key:definition.cache_key,report_status:report?.status??'absent',registration_verified:!!audit,quotes_bound:!!quotesBound,proof:proof?{status:proof.status,errors:proof.errors,group:groupProof}:null});
   if(proof?.status==='passed'&&groupProof?.status==='passed'&&quotesBound&&definition.result_hash===packet.computed_result_hash&&['metric','label','definition','definition_scope'].every(k=>decision[k]===definition.after?.[k]))proofs.push({kind:'definition',status:'passed',source_key:meta.source_key,source_fingerprint:meta.source_fingerprint,original_extraction_hash:meta.original_extraction_hash,review_sha256:signature(definition),owner_run_id:owner,processing_id:cache._review_provenance.processing_id,request_id:groupProof.matching_request_ids[0],extraction_signature:extractionSignature(cache.extractions.find(e=>e.class==='definition_decision'&&e.text==='[[DEFINITION:'+definition.group_id+']]')),before_history_verified:historyOkay,quotes_verified:true});
  }else if(alias){
   const packet=saved.catalog.find(p=>p.computed_result_hash===alias.result_hash&&p.payload.catalog_hash===alias.catalog_hash),cache=packet?.payload,owner=cache?._review_provenance?.owner_run_id;
   const proof=owner?validateAcceptedCache(packet,{result_hash:alias.result_hash,source_provenance:alias.source_provenance},await events(owner)):null;
   if(proof?.status==='passed'){
    const keep=cache.review?.keep||[],decisions=cache.review?.aliases||{},expected=decisions[alias.source_metric];
    const decisionOkay=alias.decision==='keep'?keep.includes(alias.source_metric)&&alias.canonical_metric===alias.source_metric:expected?.canonical_metric===alias.canonical_metric&&expected?.canonical_label===alias.canonical_label&&expected?.reason===alias.reason;
    const marker='[[METRIC:'+alias.source_metric+']]',request=proof.matching_requests.find(r=>r.input_text.includes(marker+' '));
    const summary=cache.extractions.find(e=>e.class==='catalog_review'),attrs=summary?.attributes||{},count=keep.length+Object.keys(decisions).length;
    const counts=Number(attrs.reviewed_count)===count&&(attrs.keep_ids_json?new Set(JSON.parse(attrs.keep_ids_json)).size===keep.length:Number(attrs.keep_count)===keep.length&&Number(attrs.merge_count)===Object.keys(decisions).length);
    if(decisionOkay&&request&&summary&&counts)proofs.push({kind:'catalog',status:'passed',source_key:meta.source_key,source_fingerprint:meta.source_fingerprint,original_extraction_hash:meta.original_extraction_hash,review_sha256:signature(alias),owner_run_id:owner,processing_id:cache._review_provenance.processing_id,request_id:request.request_id,extraction_signature:extractionSignature(summary)});
   }
  }
  catalogChecks.push({fact_id:fact.fact_id,source_key:meta.source_key,...validateReviewBinding(fact,proofs)});
 }
 const temporalChunks=[],temporalErrors=[],targetKeys=new Set();
 if(saved.temporal){
  for(const chunk of saved.temporal.chunks){
   const owner=chunk.payload?._review_provenance?.owner_run_id,proof=owner?validateAcceptedCache(chunk,chunk.audit,await events(owner)):null,cache=chunk.payload;
   const members=chunk.phase==='profiles'?cache?.reviewed_group_ids||[]:[...(cache?.corrections||[]),...(cache?.unresolved||[])].map(x=>x.source_key);
   const coverage=members.length===(chunk.phase==='profiles'?chunk.audit.reviewed_count:chunk.audit.source_count)&&new Set(members).size===members.length;
   if(chunk.phase==='corrections')members.forEach(k=>targetKeys.add(k));
   const prefix=chunk.phase==='profiles'?'[[GROUP:':'[[SOURCE:';
   const grounded=members.every(k=>proof?.matching_requests.some(r=>r.input_text.includes(prefix+k+']]')));
   temporalChunks.push({phase:chunk.phase,cache_key:chunk.audit.cache_key,result_hash:chunk.computed_result_hash,owner_run_id:owner,covered:members.length,status:proof?.status==='passed'&&coverage&&grounded?'passed':'failed',errors:[...(proof?.errors||['proof_missing']),...(!coverage?['coverage']:[]),...(!grounded?['members_not_in_same_actual_request']:[])]});
  }
  const r=saved.temporal.review;
  if(r.review_id!==catalog.temporal_review?.review_id||r.source_snapshot_hash!==catalog.temporal_review?.source_snapshot_hash)temporalErrors.push('source_snapshot');
  if(temporalChunks.filter(c=>c.phase==='profiles').reduce((n,c)=>n+c.covered,0)!==catalog.temporal_review?.profiles_total)temporalErrors.push('profile_count');
  if(targetKeys.size!==catalog.temporal_review?.sources_targeted)temporalErrors.push('unique_target_count');
  if(r.target_source_keys&&!same([...targetKeys].sort(),[...r.target_source_keys].sort()))temporalErrors.push('target_keys');
 }else temporalErrors.push('no_accepted_temporal_review');
 if(temporalChunks.some(c=>c.status!=='passed'))temporalErrors.push('cache_signature_or_owner');
 const audits=[...ownerEvents].map(([owner,e])=>{const {signatures,...p}=extractionEvidence(e,owner);return {run_id:owner,...p};}),temporal=temporalAcceptance(catalog.temporal_review,facts,audits);
 return {source:saved.source,normalization:{status:normalizationChecks.length&&normalizationChecks.every(c=>c.status==='passed')?'passed':'failed',checks:normalizationChecks},catalog:{status:catalogChecks.length&&catalogChecks.every(c=>c.status==='passed')?'passed':'failed',checks:catalogChecks,verified:catalogChecks.filter(c=>c.status==='passed').length},definition_provenance_v2:definitionChecks,temporal:{...temporal,status:temporal.status==='passed'&&!temporalErrors.length?'passed':'failed',cache_errors:temporalErrors,chunks:temporalChunks,unique_target_sources:targetKeys.size},proofs,audited_owners:[...ownerEvents.keys()]};
}

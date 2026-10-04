/** Independent provenance only. No production imports or financial rescoring. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {digest,stableJson,extractionSignature,extractionEvidence,decimalKey} from './validation_utils.mjs';
const root=path.resolve(import.meta.dirname,'..'),execute=promisify(execFile);
const equal=(a,b)=>stableJson(a)===stableJson(b),chars=t=>Array.from(t),cpSlice=(t,a,b)=>chars(t).slice(a,b).join('');
// Python str.isspace includes C0 separators; JavaScript \s includes BOM instead.
const whitespace=c=>/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/u.test(c);
function occurrences(text,needle,ignoreWhitespace=false){
 const source=chars(text),indices=source.map((c,i)=>i).filter(i=>!ignoreWhitespace||!whitespace(source[i]));
 const hay=indices.map(i=>source[i]),want=chars(needle).filter(c=>!ignoreWhitespace||!whitespace(c)),found=[];
 if(!want.length)return found;
 for(let i=0;i<=hay.length-want.length;i++)if(want.every((c,j)=>hay[i+j]===c))found.push([indices[i],indices[i+want.length-1]+1]);
 return found;
}
export function expectedQuoteLocation(original,evidence){
 if(!original||!equal(Object.keys(original).sort(),['evidence_id','text'])||typeof original.evidence_id!=='string'||typeof original.text!=='string'||!chars(original.text).some(c=>!whitespace(c)))return {error:'invalid_original_quote'};
 const own=evidence.get(original.evidence_id);
 if(typeof own==='string'&&own.includes(original.text))return {quote:original,alignment:null};
 let candidates=[],method='whitespace_within_evidence';
 if(typeof own==='string'){
  candidates=occurrences(own,original.text,true).map(span=>({id:original.evidence_id,span}));
  if(candidates.length>1)return {error:'ambiguous_same_evidence'};
 }
 if(!candidates.length)for(const folded of [false,true]){
  candidates=[...evidence].flatMap(([id,text])=>occurrences(text,original.text,folded).map(span=>({id,span})));
  method=folded?'unique_group_whitespace':'unique_group_exact';if(candidates.length)break;
 }
 if(candidates.length!==1)return {error:candidates.length?'ambiguous_group':'quote_absent_from_group'};
 const {id,span}=candidates[0],quote={evidence_id:id,text:cpSlice(evidence.get(id),...span)};
 return {quote,alignment:{version:'definition-quote-location-1',method,original_quote:original,grounded_quote:quote,span,offset_unit:'python_unicode_codepoint'}};
}
function content(message){return typeof message.content==='string'?message.content:(message.content||[]).map(v=>v.text||'').join('\n');}
export function definitionInput(messages){
 const combined=messages.map(content).join('\n'),tag='Q: [[KNOWN_METRICS]] ',pos=combined.lastIndexOf(tag);
 let text=pos>=0?combined.slice(pos+3):combined.slice(combined.lastIndexOf('[[KNOWN_METRICS]] '));
 text=text.replace(/\nA:\s*$/,'');
 const contexts=new Map(),groups=new Map();
 for(const line of text.split('\n')){
  let match=line.match(/^\[\[EVIDENCE_CONTEXT:([^\]]+)\]\] (.+)$/);
  if(match){if(contexts.has(match[1]))throw Error('duplicate_context');contexts.set(match[1],JSON.parse(match[2]).text);}
  match=line.match(/^\[\[DEFINITION:([^\]]+)\]\] (.+)$/);
  if(match){const group=JSON.parse(match[2]);if(groups.has(match[1])||group.group_id!==match[1])throw Error('duplicate_or_wrong_group');groups.set(match[1],group);}
 }
 for(const group of groups.values()){
  group.sourceEvidence=new Map();
  for(const item of group.evidence||[]){const value=item.text??contexts.get(item.text_ref);if(typeof value!=='string'||group.sourceEvidence.has(item.evidence_id))throw Error('invalid_evidence');group.sourceEvidence.set(item.evidence_id,value);}
 }
 return {text,groups,input_hash:digest(text)};
}
function actualRequests(events,owner){
 const requests=new Map(events.filter(e=>e.type==='extraction_request').map(e=>[e.data.requestId,e])),found=[];
 for(const result of events.filter(e=>e.type==='extraction_result')){
  const request=requests.get(result.data.requestId);if(!request)continue;
  const proof=extractionEvidence([request,result],owner);
  if(!proof.valid_owners||!proof.successful_results)continue;
  try{const input=definitionInput(request.data.messages||[]);if(input.groups.size)found.push({id:result.data.requestId,input,signatures:proof.signatures,request,result});}catch{}
 }
 return found;
}
function quoteChecks(decision,extraction,group){
 const errors=[],quotes=[];let originals;
 try{originals=JSON.parse(extraction.attributes.grounded_quotes_json);}catch{}
 if(!Array.isArray(originals)||!originals.length||!Array.isArray(decision.grounded_quotes)||originals.length!==decision.grounded_quotes.length)return {errors:['quote_shape_or_count'],quotes};
 const alignments=decision.quote_alignments||[],seen=new Set();
 for(const item of alignments){if(!Number.isInteger(item.quote_index)||item.quote_index<0||item.quote_index>=originals.length||seen.has(item.quote_index))errors.push('invalid_or_duplicate_quote_alignment');seen.add(item.quote_index);}
 originals.forEach((original,i)=>{
  const expected=expectedQuoteLocation(original,group.sourceEvidence),recorded=alignments.find(a=>a.quote_index===i),fail=[];
  if(expected.error)fail.push(expected.error);
  else{
   if(!equal(expected.quote,decision.grounded_quotes[i]))fail.push('grounded_quote_not_exact_original_substring');
   if(expected.alignment?!equal({...expected.alignment,quote_index:i},recorded):recorded!==undefined)fail.push('alignment_method_uniqueness_or_unicode_offsets');
  }
  errors.push(...fail.map(e=>'quote_'+i+':'+e));quotes.push({quote_index:i,status:fail.length?'failed':'passed',errors:fail,alignment:expected.alignment||null});
 });
 return {errors,quotes};
}
export function validateDefinitionCacheV2(cache,events){
 const owner=cache?._review_provenance?.owner_run_id,processing=cache?._review_provenance?.processing_id,requests=actualRequests(events,owner),errors=[],checks=[],attemptChecks=[];
 if(!owner||!processing||!events.some(e=>e.type==='processing_started'&&e.data.ownerRunId===owner&&e.data.processingId===processing))errors.push('original_processing_owner_not_audited');
 const attempts=cache?.attempts||[];
 for(const [i,attempt] of attempts.entries()){
  let matching=[];
  if(attempt.outcome==='output_limit'){
   const bridge=attempt.bridge_error||{};
   if(bridge.code==='model_output_limit'&&bridge.stop_reason==='length'&&typeof bridge.request_id==='string'&&Array.isArray(attempt.extractions)&&!attempt.extractions.length){
    const request=events.find(e=>e.type==='extraction_request'&&e.data.requestId===bridge.request_id),result=events.find(e=>e.type==='extraction_result'&&e.data.requestId===bridge.request_id);
    if(request?.data.ownerRunId===owner&&request.data.runtime==='Pi.ModelRuntime'&&result?.data.ownerRunId===owner&&result.data.stopReason==='length')try{const input=definitionInput(request.data.messages||[]);if(input.input_hash===attempt.input_hash&&equal([...input.groups.keys()],attempt.group_ids))matching=[{id:bridge.request_id}];}catch{}
   }
  }else matching=requests.filter(r=>r.input.input_hash===attempt.input_hash&&equal([...r.input.groups.keys()],attempt.group_ids)&&attempt.extractions.every(e=>r.signatures.has(extractionSignature(e))));
  attemptChecks.push({attempt:i,status:matching.length?'passed':'failed',matching_request_ids:matching.map(r=>r.id)});
 }
 if(attemptChecks.some(c=>c.status==='failed'))errors.push('attempt_input_or_original_output_missing');
 const acceptedIds=[...(cache.decisions||[]),...(cache.unresolved||[])].map(d=>d.group_id),partial=cache.partial_coverage;
 const originalIds=new Set(partial?.original_group_ids||acceptedIds);
 if(partial){const pending=partial.pending_group_ids||[],all=[...acceptedIds,...pending];if(!Array.isArray(partial.original_group_ids)||!Array.isArray(partial.pending_group_ids)||!pending.length||!acceptedIds.length||new Set(all).size!==all.length||new Set(partial.original_group_ids).size!==partial.original_group_ids.length||!equal([...new Set(all)].sort(),[...originalIds].sort()))errors.push('partial_coverage_partition');}
 const initial=requests.filter(r=>(!attempts.length||r.input.input_hash===attempts[0].input_hash)&&r.input.groups.size===originalIds.size&&[...originalIds].every(id=>r.input.groups.has(id)));
 for(const decision of cache?.decisions||[]){
  const ownErrors=[],marker='[[DEFINITION:'+decision.group_id+']]',extractions=(cache.extractions||[]).filter(e=>e.class==='definition_decision'&&e.text===marker);
  if(extractions.length!==1){checks.push({group_id:decision.group_id,status:'failed',errors:['accepted_extraction_missing_or_duplicate']});continue;}
  const ex=extractions[0],attrs=ex.attributes||{};
  for(const field of ['metric','label','definition','definition_scope','reason'])if(String(attrs[field]??'').trim()!==decision[field])ownErrors.push('changed_model_semantics:'+field);
  const matching=requests.filter(r=>r.signatures.has(extractionSignature(ex))&&r.input.groups.has(decision.group_id));
  const proofs=matching.map(r=>({request_id:r.id,...quoteChecks(decision,ex,r.input.groups.get(decision.group_id))}));
  if(!proofs.some(p=>!p.errors.length))ownErrors.push('same_original_request_and_group_quotes_missing');
  const offsetMatches=initial.filter(r=>Array.isArray(ex.span)&&ex.span.length===2&&ex.span.every(Number.isInteger)&&occurrences(r.input.text,marker).length===1&&cpSlice(r.input.text,...ex.span)===marker&&equal(decision.span,ex.span));
  if(!offsetMatches.length)ownErrors.push('accepted_marker_unicode_span');
  if(attempts.length&&!attempts.some(a=>a.extractions.some(e=>extractionSignature(e)===extractionSignature(ex))))ownErrors.push('accepted_extraction_not_in_recorded_attempts');
  checks.push({group_id:decision.group_id,status:ownErrors.length?'failed':'passed',errors:ownErrors,matching_request_ids:matching.map(r=>r.id),marker_input_request_ids:offsetMatches.map(r=>r.id),quote_proofs:proofs,extraction_signature:extractionSignature(ex)});
 }
 const unresolved=(cache?.unresolved||[]).map(d=>{const ex=(cache.extractions||[]).filter(e=>e.class==='definition_unresolved'&&e.text==='[[DEFINITION:'+d.group_id+']]');return {group_id:d.group_id,passed:ex.length===1&&requests.some(r=>r.input.groups.has(d.group_id)&&r.signatures.has(extractionSignature(ex[0])))};});
 if(unresolved.some(c=>!c.passed))errors.push('unresolved_original_output_missing');
 return {owner_run_id:owner,processing_id:processing,status:!errors.length&&checks.length+unresolved.length>0&&checks.every(c=>c.status==='passed')?'passed':'failed',errors,checks,attempt_checks:attemptChecks,unresolved};
}
function normalizeFact(row){if(!row.source_json)return row;const ref=JSON.parse(row.source_json),meta=ref.normalization||{};return {...row,source_ref:ref,label:meta.label,definition:meta.definition_review?.after?.definition,definition_scope:meta.definition_review?.after?.definition_scope};}
export function validateHistoricalDefinitionLimit(entry,{events,auditSha256,reviews,currentFingerprints,projectDocumentIds,split}={}){
 const errors=[],owner=entry.original_owner_run_id,requests=events.filter(e=>e.type==='extraction_request'&&e.data.requestId===entry.original_request_id),results=events.filter(e=>e.type==='extraction_result'&&e.data.requestId===entry.original_request_id);
 if(entry.kind!=='verified_historical_output_limit'||entry.policy_version!=='verified-historical-output-limit-1'||entry.stop_reason!=='length'||entry.current_model_requests!==0)errors.push('historical_receipt_contract');
 if(entry.audit_sha256!==auditSha256)errors.push('original_audit_bytes_changed');
 if(requests.length!==1||results.length!==1)errors.push('original_request_result_not_unique');
 const request=requests[0],result=results[0],index=events.indexOf(request),start=events.slice(0,index).filter(e=>e.type==='processing_started').at(-1);
 if(!request||!result||request.data.ownerRunId!==owner||result.data.ownerRunId!==owner||request.data.runtime!=='Pi.ModelRuntime'||result.data.stopReason!=='length')errors.push('original_owner_runtime_or_length');
 if(!start||start.data.ownerRunId!==owner||start.data.processingId!==entry.original_processing_id||!start.data.documentIds?.length||start.data.documentIds.some(id=>!projectDocumentIds.includes(id)))errors.push('original_processing_project_binding');
 const originalReview=reviews.find(r=>r.review_id===entry.original_review_id);
 if(!originalReview||originalReview.owner_run_id!==owner||originalReview.processing_id!==entry.original_processing_id)errors.push('original_review_binding');
 if(request){
  if(request.data.model!==entry.model||request.data.reasoningEffort!==entry.reasoning_effort||request.data.maxTokens!==entry.max_tokens)errors.push('original_inference_config');
  if(digest(request.data.messages)!==entry.messages_hash)errors.push('complete_original_messages_hash');
  try{const input=definitionInput(request.data.messages);if(input.input_hash!==entry.input_hash||!equal([...input.groups.keys()],entry.group_ids))errors.push('original_input_or_groups');}catch{errors.push('original_input_unreadable');}
 }
 if(result&&!equal(result.data.usage,entry.historical_usage))errors.push('historical_usage_changed');
 const sources=Object.entries(entry.source_fingerprints||{});
 if(!sources.length||sources.some(([key,fingerprint])=>currentFingerprints[key]!==fingerprint||originalReview?.source_fingerprints?.[key]!==fingerprint))errors.push('original_and_current_source_fingerprints');
 if(split){
  const children=split.children??split.child_group_ids;
  if(split.model_requests!==0)errors.push('historical_split_not_zero_new_calls');
  if(!Array.isArray(children)||children.length!==2||children.some(g=>!Array.isArray(g)||!g.length)||new Set(children.flat()).size!==children.flat().length||!equal(children.flat(),entry.group_ids))errors.push('historical_split_partition');
 }
 return {status:errors.length?'failed':'passed',errors,original_owner_run_id:owner,original_request_id:entry.original_request_id,historical_usage:entry.historical_usage,current_model_requests:0,source_count:sources.length,
  scope:'Independently verifies receipt against immutable original audit, original project review and current source identities. Fresh full-template generation equality is a separate production scheduling check; no fictitious new model request is inferred.'};
}
export function validateDefinitionSnapshotV2(saved,owners,{ownerRunId}={}){
 const proofs=new Map(Object.entries(saved.caches).map(([key,cache])=>[key,validateDefinitionCacheV2(cache,owners.get(cache._review_provenance?.owner_run_id)||[])]));
 const checks=[],registration=[];
 for(const fact of saved.facts.map(normalizeFact)){
  const ref=fact.source_ref,meta=ref.normalization,review=meta.definition_review;if(ownerRunId&&review.owner_run_id!==ownerRunId)continue;
  const errors=[],cache=saved.caches[review.cache_key],proof=proofs.get(review.cache_key),decision=cache?.decisions?.find(d=>d.group_id===review.group_id),report=saved.reviews.find(r=>r.review_id===review.review_id);
  if(review.status!=='reviewed'||review.engine!=='LangExtract')errors.push('accepted_review_contract');
  if(proof?.checks.find(c=>c.group_id===review.group_id)?.status!=='passed'||proof?.status!=='passed')errors.push('actual_pi_decision_and_quote_proof');
  if(review.owner_run_id!==proof?.owner_run_id||review.extraction_processing_id!==proof?.processing_id)errors.push('cache_original_owner');
  if(review.result_hash!==saved.cache_hashes[review.cache_key])errors.push('accepted_cache_result_hash');
  if(review.source_key!==meta.source_key||review.source_fingerprint!==meta.source_fingerprint||review.original_extraction_hash!==meta.original_extraction_hash)errors.push('source_fingerprint');
  for(const field of ['metric','label','definition','definition_scope'])if(review.after?.[field]!==decision?.[field]||fact[field]!==decision?.[field])errors.push('accepted_after:'+field);
  if(!equal(review.grounded_quotes,decision?.grounded_quotes)||!equal(review.quote_alignments||[],decision?.quote_alignments||[])||review.reason!==decision?.reason)errors.push('accepted_evidence_metadata');
  const history=saved.histories.filter(h=>h.processing_id===(report?.processing_id||review.extraction_processing_id)).find(h=>{const prior=normalizeFact(h.fact);return prior.source_ref.normalization?.source_key===meta.source_key&&equal(review.before,{metric:prior.metric,label:prior.label});});
  if(!history)errors.push('archived_before_source_missing');
  else{
   const prior=normalizeFact(history.fact),pm=prior.source_ref.normalization||{};
   for(const field of ['value','raw_value','raw_unit','currency','period','year','scope','company'])if(field==='value'?decimalKey(prior[field])!==decimalKey(fact[field]):prior[field]!==fact[field])errors.push('changed_immutable:'+field);
   for(const field of ['period_start','period_end','dimensions','original_metric','original_extraction_hash','source_fingerprint'])if(!equal(pm[field],meta[field]))errors.push('changed_immutable_meta:'+field);
   for(const field of ['document_id','page','table_id','row','column','cell','text','bbox'])if(!equal(prior.source_ref[field],ref[field]))errors.push('changed_original_source:'+field);
  }
  const audit=report?.audits?.find(a=>a.cache_key===review.cache_key),registerErrors=[];
  const validAudit=a=>a&&a.result_hash===saved.cache_hashes[review.cache_key]&&equal(a.provenance,cache?._review_provenance)&&a.group_count===(cache?.decisions||[]).length+(cache?.unresolved||[]).length;
  // A later explicit revalidation can restore current discoverability, while
  // never pretending the historical report was written when it was not.
  const laterRegistrations=saved.reviews.filter(r=>r.review_id!==review.review_id&&r.source_fingerprints?.[meta.source_key]===meta.source_fingerprint&&r.audits?.some(a=>a.cache_key===review.cache_key&&validAudit(a)&&(a.kind!=='revalidated_cached_result'||(a.revalidated_source_keys?.includes(meta.source_key)&&a.historical_review_ids?.includes(review.review_id)))));
  if(!validAudit(audit)&&!laterRegistrations.length){
   if(!report)registerErrors.push('partial_batch_report_absent');
   else if(!audit)registerErrors.push('committed_fact_not_registered_in_report');
   else{if(audit.result_hash!==saved.cache_hashes[review.cache_key])registerErrors.push('report_cache_hash');if(!equal(audit.provenance,cache?._review_provenance))registerErrors.push('report_original_owner');if(audit.group_count!==(cache.decisions||[]).length+(cache.unresolved||[]).length)registerErrors.push('report_group_count');}
  }
  registration.push({source_key:meta.source_key,review_id:review.review_id,report_status:report?.status??'absent',original_registration_missing:!validAudit(audit),current_revalidation_registration_exists:laterRegistrations.length>0,current_revalidation_review_ids:laterRegistrations.map(r=>r.review_id),status:registerErrors.length?'failed':'passed',errors:registerErrors});
  checks.push({source_key:meta.source_key,source:{document_id:ref.document_id,page:ref.page,table_id:ref.table_id,row:ref.row,column:ref.column},cache_key:review.cache_key,group_id:review.group_id,review_id:review.review_id,owner_run_id:review.owner_run_id,history_id:history?.history_id,status:errors.length?'failed':'passed',errors});
 }
 const historical=[];
 for(const report of saved.reviews)for(const [index,entry] of (report.historical_output_limits||[]).entries()){
  const splits=(report.split_attempts||[]).filter(s=>s.historical_index===index),context={events:owners.get(entry.original_owner_run_id)||[],auditSha256:saved.audit_hashes?.[entry.original_owner_run_id],reviews:saved.reviews,currentFingerprints:saved.source_fingerprints||{},projectDocumentIds:saved.project_document_ids||[]};
  const proof=validateHistoricalDefinitionLimit(entry,context);if(splits.length!==1){proof.status='failed';proof.errors.push('historical_split_link_missing_or_duplicate');}
  else{const splitProof=validateHistoricalDefinitionLimit(entry,{...context,split:splits[0]});proof.status=splitProof.status;proof.errors.push(...splitProof.errors);}
  historical.push({review_id:report.review_id,index,...proof});
 }
 const provenancePassed=checks.length>0&&checks.every(c=>c.status==='passed'),registrationPassed=registration.length>0&&registration.every(c=>c.status==='passed');
 return {schema:'definition-provenance-2',source:saved.source,captured_at:saved.captured_at,project_id:saved.project_id,owner_filter:ownerRunId??null,status:provenancePassed&&registrationPassed&&historical.every(c=>c.status==='passed')?'passed':'failed',
  provenance:{status:provenancePassed?'passed':'failed',passed:checks.filter(c=>c.status==='passed').length,total:checks.length,checks},
  partial_batch_registration:{status:registrationPassed?'passed':'failed',passed:registration.filter(c=>c.status==='passed').length,total:registration.length,checks:registration},
  cache_proofs:[...proofs].map(([cache_key,value])=>({cache_key,...value})),
  historical_output_limit_proofs:historical,
  limitation:'Proves original model output, exact source location, ownership and persistence only. Does not judge financial semantics or replace the frozen 15-anchor/9-distinction score.',model_calls:0,database_writes:0};
}
export async function verifyDefinitionEvidenceV2(projectId,{database=path.join(root,'data/finance.sqlite'),auditRoot=path.join(root,'data/audit'),ownerRunId}={}){
 const {stdout}=await execute(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/export_definition_evidence_v2.py'),'--project',projectId,'--database',database],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:48*1024*1024});
 const saved=JSON.parse(stdout),owners=new Map(),auditFiles=[];saved.audit_hashes={};
 const ownerIds=new Set([...Object.values(saved.caches).map(cache=>cache._review_provenance?.owner_run_id),...saved.reviews.flatMap(r=>(r.historical_output_limits||[]).map(e=>e.original_owner_run_id))]);
 for(const owner of ownerIds){if(owner&&!owners.has(owner)){const file=path.join(auditRoot,owner+'.jsonl');try{const raw=await fs.readFile(file);owners.set(owner,raw.toString('utf8').trim().split('\n').filter(Boolean).map(JSON.parse));saved.audit_hashes[owner]=digest(raw);auditFiles.push({owner,path:file,sha256:digest(raw)});}catch{owners.set(owner,[]);auditFiles.push({owner,path:file,error:'missing_or_invalid_audit'});}}}
 return {...validateDefinitionSnapshotV2(saved,owners,{ownerRunId}),audit_files:auditFiles,export_sha256:digest(stdout)};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2),arg=k=>args[args.indexOf(k)+1];
 if(!args.includes('--project')||!args.includes('--output'))throw Error('Required --project PROJECT --output NEW.json; optional --owner RUN_ID. Read-only, no model.');
 const result=await verifyDefinitionEvidenceV2(arg('--project'),{...(args.includes('--owner')?{ownerRunId:arg('--owner')}:{})});
 await fs.writeFile(path.resolve(arg('--output')),JSON.stringify(result,null,2),{flag:'wx'});
 console.log(JSON.stringify({status:result.status,provenance:{passed:result.provenance.passed,total:result.provenance.total},registration:{passed:result.partial_batch_registration.passed,total:result.partial_batch_registration.total}}));
}

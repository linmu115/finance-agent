// Independent host-side provenance checks. Does not import production code.
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {extractionEvidence,extractionSignature,stableJson,decimalKey} from './validation_utils.mjs';
const execute=promisify(execFile),root=path.resolve(import.meta.dirname,'..');
function texts(message){return typeof message.content==='string'?[message.content]:Array.isArray(message.content)?message.content.filter(v=>typeof v.text==='string').map(v=>v.text):[];}
function groupEvidence(messages,marker){
 const text=messages.flatMap(texts).join('\n');
 if(text.split(marker).length!==2)return null;
 const contexts=new Map();let group;
 for(const line of text.split('\n')){
  const match=line.match(/^\[\[EVIDENCE_CONTEXT:([^\]]+)\]\] (.+)$/);
  if(match){try{contexts.set(match[1],JSON.parse(match[2]).text);}catch{}}
  if(line.startsWith(marker+' ')){try{group=JSON.parse(line.slice(marker.length+1));}catch{}}
 }
 if(!group)return null;
 return new Map((group.evidence||[]).map(e=>[e.evidence_id,e.text??contexts.get(e.text_ref)]));
}
export function validateDefinitionCache(cache,events){
 const owner=cache?._review_provenance?.owner_run_id,requests=new Map(events.filter(e=>e.type==='extraction_request').map(e=>[e.data.requestId,e])),checks=[];
 for(const decision of cache?.decisions||[]){
  const marker='[[DEFINITION:'+decision.group_id+']]',ex=(cache.extractions||[]).filter(e=>e.class==='definition_decision'&&e.text===marker),errors=[];
  if(ex.length!==1){checks.push({group_id:decision.group_id,status:'failed',errors:['accepted_extraction_missing_or_duplicate']});continue;}
  const attrs=ex[0].attributes||{};
  for(const field of ['metric','label','definition','definition_scope','reason'])if(String(attrs[field]??'').trim()!==decision[field])errors.push('cache_decision_differs_from_extraction:'+field);
  let quotes;try{quotes=JSON.parse(attrs.grounded_quotes_json);}catch{}
  if(!Array.isArray(quotes)||!quotes.length||stableJson(quotes)!==stableJson(decision.grounded_quotes))errors.push('cached_quotes_differ_from_extraction');
  const matched=[];
  for(const result of events.filter(e=>e.type==='extraction_result')){
   const request=requests.get(result.data.requestId);if(!request)continue;
   const proof=extractionEvidence([request,result],owner);
   if(!proof.valid_owners||!proof.signatures.has(extractionSignature(ex[0])))continue;
   const evidence=groupEvidence(request.data.messages||[],marker);
   if(evidence&&quotes?.every(q=>typeof q.text==='string'&&q.text.length&&typeof evidence.get(q.evidence_id)==='string'&&evidence.get(q.evidence_id).includes(q.text)))matched.push(result.data.requestId);
  }
  if(!matched.length)errors.push('decision_and_quotes_not_in_same_actual_pi_request');
  checks.push({group_id:decision.group_id,status:errors.length?'failed':'passed',errors,matching_request_ids:matched,extraction_signature:extractionSignature(ex[0])});
 }
 return {owner_run_id:owner,processing_id:cache?._review_provenance?.processing_id,status:checks.length&&checks.every(c=>c.status==='passed')?'passed':'failed',checks};
}
export async function verifyDefinitionEvidence(projectId,beforeFacts,afterFacts){
 const {stdout}=await execute(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/export_definition_evidence.py'),'--project',projectId],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:24*1024*1024});
 const saved=JSON.parse(stdout),owners=new Map(),proofs=new Map(),checks=[];
 for(const [key,cache] of Object.entries(saved.caches)){
  const owner=cache._review_provenance?.owner_run_id;
  if(owner&&!owners.has(owner))owners.set(owner,(await fs.readFile(path.join(root,'data/audit',owner+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse));
  proofs.set(key,validateDefinitionCache(cache,owners.get(owner)||[]));
 }
 const previous=new Map(beforeFacts.map(f=>[f.source_ref?.normalization?.source_key,f]));
 for(const fact of afterFacts){
  const meta=fact.source_ref?.normalization||{},old=previous.get(meta.source_key),review=meta.definition_review;
  const changed=old&&(old.metric!==fact.metric||old.label!==fact.label);
  if(!changed&&!review)continue;
  const errors=[];
  if(!old)errors.push('before_source_missing');
  if(!review)errors.push('definition_changed_without_review');
  else{
   const cache=saved.caches[review.cache_key],proof=proofs.get(review.cache_key),decision=cache?.decisions?.find(d=>d.group_id===review.group_id);
   if(review.engine!=='LangExtract'||review.status!=='reviewed'||!decision||proof?.checks.find(c=>c.group_id===review.group_id)?.status!=='passed')errors.push('actual_pi_decision_missing');
   if(review.owner_run_id!==proof?.owner_run_id||review.extraction_processing_id!==proof?.processing_id)errors.push('wrong_owner');
   if(!review.source_key||review.source_key!==meta.source_key||review.source_fingerprint!==meta.source_fingerprint||review.source_fingerprint!==old?.source_ref?.normalization?.source_fingerprint||review.original_extraction_hash!==meta.original_extraction_hash)errors.push('source_fingerprint');
   const history=saved.histories?.find(h=>h.review_id===review.review_id&&JSON.parse(h.fact.source_json).normalization?.source_key===meta.source_key),prior=history?.fact,priorRef=prior&&JSON.parse(prior.source_json),priorMeta=priorRef?.normalization;
   if(!prior||stableJson(review.before)!==stableJson({metric:prior.metric,label:priorMeta.label}))errors.push('before_definition_not_archived_source');
   if(prior){
    for(const field of ['value','raw_value','raw_unit','currency','period','year','scope','company'])if((field==='value'?decimalKey(prior[field])!==decimalKey(fact[field]):prior[field]!==fact[field]))errors.push('definition_changed_immutable:'+field);
    for(const field of ['period_start','period_end','dimensions','original_metric','original_extraction_hash','source_fingerprint'])if(stableJson(priorMeta?.[field])!==stableJson(meta[field]))errors.push('definition_changed_immutable_meta:'+field);
    for(const field of ['document_id','page','table_id','row','column','cell','text','bbox'])if(stableJson(priorRef?.[field])!==stableJson(fact.source_ref[field]))errors.push('definition_changed_source:'+field);
   }
   for(const field of ['metric','label','definition','definition_scope'])if(review.after?.[field]!==decision?.[field]||fact[field]!==decision?.[field])errors.push('after_definition:'+field);
   if(stableJson(review.grounded_quotes)!==stableJson(decision?.grounded_quotes)||review.reason!==decision?.reason)errors.push('decision_evidence_differs');
  }
  checks.push({source_key:meta.source_key,source:{document_id:fact.source_ref.document_id,page:fact.source_ref.page,table_id:fact.source_ref.table_id,row:fact.source_ref.row,column:fact.source_ref.column},changed_metric_or_label:!!changed,before:old&&{metric:old.metric,label:old.label},after:{metric:fact.metric,label:fact.label,definition:fact.definition,definition_scope:fact.definition_scope},review_id:review?.review_id,cache_key:review?.cache_key,status:errors.length?'failed':'passed',errors});
 }
 return {source:saved.source,status:checks.length&&checks.every(c=>c.status==='passed')?'passed':'failed',reviewed_facts:checks.length,changed_metric_or_label:checks.filter(c=>c.changed_metric_or_label).length,checks,cache_proofs:[...proofs].map(([cache_key,proof])=>({cache_key,...proof})),reports:saved.reviews.map(({source_fingerprints,audits,...report})=>report)};
}

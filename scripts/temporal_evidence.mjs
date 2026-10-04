import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {extractionEvidence,extractionSignature} from './validation_utils.mjs';
const execute=promisify(execFile),root=path.resolve(import.meta.dirname,'..');
export function summarizeTemporalTargets(saved){
 const keys=new Set(),errors=[];let events=0;
 for(const chunk of saved.chunks.filter(c=>c.phase==='corrections')){
  const actual=[...(chunk.cached?.corrections||[]),...(chunk.cached?.unresolved||[])].map(x=>x.source_key);
  events+=actual.length;
  if(actual.some(x=>typeof x!=='string'||!x)||new Set(actual).size!==actual.length||actual.length!==chunk.audit.source_count)errors.push('invalid_correction_batch_members');
  if(chunk.audit.source_keys&&JSON.stringify([...chunk.audit.source_keys].sort())!==JSON.stringify([...actual].sort()))errors.push('batch_members_differ_from_accepted_cache');
  actual.forEach(key=>keys.add(key));
 }
 if(saved.review.target_source_keys&&JSON.stringify([...saved.review.target_source_keys].sort())!==JSON.stringify([...keys].sort()))errors.push('target_sources_differ_from_accepted_caches');
 return {unique_source_count:keys.size,review_event_count:events,source_keys:[...keys].sort(),errors};
}
export async function verifyTemporalCacheEvidence(projectId,summary){
 if(!summary?.review_id)return {status:'failed',errors:['missing_review_id'],chunks:[]};
 const {stdout}=await execute(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/export_temporal_evidence.py'),'--project',projectId,'--review',summary.review_id],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:12*1024*1024});
 const saved=JSON.parse(stdout),owners=new Map(),chunks=[],errors=[];
 for(const chunk of saved.chunks){
  const cache=chunk.cached,owner=chunk.audit.source_provenance?.owner_run_id;
  if(owner&&!owners.has(owner)){
   const events=(await fs.readFile(path.join(root,'data/audit',owner+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
   const proof=extractionEvidence(events,owner);
   owners.set(owner,{run_id:owner,...proof,request_contents:events.filter(e=>e.type==='extraction_request').map(e=>JSON.stringify(e.data.messages))});
  }
  const proof=owners.get(owner),extractions=cache?.extractions||[],matched=extractions.filter(ex=>proof?.signatures.has(extractionSignature(ex))).length;
  const sourceMarkers=extractions.filter(ex=>['temporal_candidate','temporal_correction','temporal_unresolved'].includes(ex.class));
  const groundedMarkers=sourceMarkers.filter(ex=>typeof ex.text==='string'&&proof?.request_contents.some(content=>content.split(ex.text).length===2)).length;
  const phaseReview=extractions.filter(ex=>ex.class==='temporal_review');
  const coverage=chunk.phase==='profiles'
   ?cache?.reviewed_count===chunk.audit.reviewed_count&&cache?.reviewed_group_ids?.length===chunk.audit.reviewed_count&&phaseReview.length===1&&Number(phaseReview[0].attributes.reviewed_count)===chunk.audit.reviewed_count&&cache.reviewed_group_ids.every(id=>proof?.request_contents.some(content=>content.includes('[[GROUP:'+id+']]')))
   :(cache?.corrections?.length||0)+(cache?.unresolved?.length||0)===chunk.audit.source_count;
  chunks.push({phase:chunk.phase,cache_key:chunk.audit.cache_key,owner_run_id:owner||null,accepted_extractions:extractions.length,matched_pi_extractions:matched,source_markers:sourceMarkers.length,unique_markers_in_actual_pi_input:groundedMarkers,coverage_count:chunk.phase==='profiles'?chunk.audit.reviewed_count:chunk.audit.source_count,passed:!!proof?.valid_owners&&cache?._review_provenance?.owner_run_id===owner&&extractions.length>0&&matched===extractions.length&&groundedMarkers===sourceMarkers.length&&!!coverage});
 }
 if(saved.review.review_id!==summary.review_id||saved.review.source_snapshot_hash!==summary.source_snapshot_hash)errors.push('review_snapshot_mismatch');
 if(chunks.filter(c=>c.phase==='profiles').reduce((n,c)=>n+c.coverage_count,0)!==summary.profiles_total)errors.push('accepted_profile_coverage');
 const targets=summarizeTemporalTargets(saved);
 if(targets.unique_source_count!==summary.sources_targeted||targets.errors.length)errors.push('accepted_correction_coverage',...targets.errors);
 if(!chunks.length||chunks.some(c=>!c.passed))errors.push('accepted_extractions_not_proven');
 return {status:errors.length?'failed':'passed',source:saved.source,errors,review_id:summary.review_id,targets,chunks,audits:[...owners.values()].map(({signatures,request_contents,...a})=>a)};
}

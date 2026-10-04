import {createHash} from 'node:crypto';
export {decimalKey} from './score_normalization.mjs';
export function stableJson(value){
 if(Array.isArray(value))return '['+value.map(stableJson).join(',')+']';
 if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+stableJson(value[key])).join(',')+'}';
 return JSON.stringify(value);
}
export const digest=value=>createHash('sha256').update(typeof value==='string'||Buffer.isBuffer(value)?value:stableJson(value)).digest('hex');
export function extractionSignature(ex){return digest({class:ex.class,text:ex.text,attributes:ex.attributes||{}});}
export function extractionEvidence(events,ownerRunId){
 const requests=events.filter(e=>e.type==='extraction_request'),results=events.filter(e=>e.type==='extraction_result');
 const byId=new Map(requests.map(e=>[e.data.requestId,e.data]));
 const signatures=new Set(),classes=new Set(),temporalSignatures=new Set();let successful=0,failed=0;
 const record=ex=>{classes.add(ex.class);signatures.add(extractionSignature(ex));if(ex.class==='temporal_correction')temporalSignatures.add(extractionSignature({...ex,attributes:{...ex.attributes,reason:typeof ex.attributes?.reason==='string'?ex.attributes.reason.trim():ex.attributes?.reason}}));};
 for(const event of results){
  const result=event.data,request=byId.get(result.requestId);
  if(!request||request.ownerRunId!==ownerRunId||request.runtime!=='Pi.ModelRuntime'||result.ownerRunId!==ownerRunId||['error','length'].includes(result.stopReason)||!result.content?.trim()){failed++;continue;}
  try{
   const body=JSON.parse(result.content),items=body.extractions;
   if(!Array.isArray(items)){failed++;continue;}
   for(const item of items){
    if(item.extraction_class&&item.extraction_text)record({class:item.extraction_class,text:item.extraction_text,attributes:item.attributes||{}});
    else for(const key of Object.keys(item).filter(k=>!k.endsWith('_attributes'))){
     if(typeof item[key]==='string')record({class:key,text:item[key],attributes:item[key+'_attributes']||{}});
    }
   }
   successful++;
  }catch{failed++;}
 }
 return {requests:requests.length,results:results.length,successful_results:successful,failed_results:failed,
  unmatched_requests:requests.length-results.length,
  valid_owners:requests.every(e=>e.data.ownerRunId===ownerRunId&&e.data.runtime==='Pi.ModelRuntime'),extraction_classes:[...classes].sort(),temporal_correction_signatures:[...temporalSignatures],signatures};
}
export function temporalAcceptance(summary,facts,audits){
 const errors=[];
 if(summary?.status!=='reviewed')errors.push('review_not_complete');
 if(summary?.facts_total!==facts.length||summary?.facts_reviewable!==facts.length)errors.push('fact_coverage');
 if(summary?.coverage_snapshot_valid!==true||summary?.current_fact_count!==facts.length)errors.push('current_source_snapshot');
 if(!(summary?.profiles_total>0)||summary?.profiles_reviewed!==summary?.profiles_total)errors.push('profile_coverage');
 for(const key of ['unresolved','unreviewable','stale_sources','pending_new_sources'])if(!Array.isArray(summary?.[key])||summary[key].length)errors.push(key);
 if(!audits.some(a=>a.valid_owners&&a.extraction_classes?.includes('temporal_review')))errors.push('missing_actual_pi_review');
 const corrections=facts.filter(f=>f.source_ref?.normalization?.temporal_correction).map(f=>{
  const meta=f.source_ref.normalization.temporal_correction,after=meta.after||{},audit=audits.find(a=>a.run_id===meta.owner_run_id);
  const signature=extractionSignature({class:'temporal_correction',text:'[[SOURCE:'+meta.source_key+']]',attributes:{period:after.period,start:after.start,end:after.end,reason:meta.reason,evidence:meta.evidence}});
  const grounded=Array.isArray(meta.span)&&meta.span.length===2&&meta.span[1]>meta.span[0];
  return {fact_id:f.fact_id,source_key:meta.source_key,owner_run_id:meta.owner_run_id,passed:meta.engine==='LangExtract'&&meta.status==='reviewed'&&!!meta.source_fingerprint&&!!meta.original_extraction_hash&&grounded&&!!audit?.valid_owners&&audit.temporal_correction_signatures?.includes(signature)&&f.period===after.period&&(f.period_start||'')===(after.start||'')&&(f.period_end||'')===(after.end||'')};
 });
 if(corrections.some(c=>!c.passed))errors.push('correction_provenance');
 if(summary?.sources_targeted>0&&!corrections.length)errors.push('missing_source_corrections');
 return {status:errors.length?'failed':'passed',errors,summary,corrections,audited_owners:audits.filter(a=>a.extraction_classes?.some(c=>c.startsWith('temporal_'))).map(a=>({run_id:a.run_id,valid_owners:a.valid_owners,classes:a.extraction_classes}))};
}
export async function collectNormalizationPages(request,route){
 const batches=[],seen=new Set();let first,offset=0,requests=0;
 while(true){
  const page=await request(route+'?limit=50&offset='+offset);requests++;
  if(!first)first=page;
  if(page.offset!==undefined&&page.offset!==offset)throw Error('Normalization endpoint ignored pagination offset; restart the updated server, then rescore this same run with --resume.');
  if(!Array.isArray(page.batches))throw Error('Normalization endpoint returned no batch list.');
  for(const batch of page.batches){if(seen.has(batch.batch_key))throw Error('Normalization pagination repeated a batch; coverage cannot be verified.');seen.add(batch.batch_key);batches.push(batch);}
  offset+=page.batches.length;
  if(page.total===undefined||offset===page.total)break;
  if(offset>page.total||!page.batches.length)throw Error('Normalization pagination did not cover its reported total.');
 }
 return {...first,batches,pagination:{requests,total:first.total??batches.length,loaded:batches.length,source:'public_http_all_pages'}};
}
// A completed run can be visible before its last conversation-state write lands.
// Poll only the read endpoint; never start another turn to repair an observation.
export async function readPersistedRunAnswer(readConversation,runId,{timeoutMs=15000,pollMs=100}={}){
 const started=Date.now();let conversation,answer,attempts=0;
 do{
  conversation=await readConversation();attempts++;
  answer=conversation.messages.find(m=>m.runId===runId&&m.role==='assistant'&&m.content?.trim());
  if(answer)return {conversation,answer,attempts,waited_ms:Date.now()-started};
  await new Promise(resolve=>setTimeout(resolve,pollMs));
 }while(Date.now()-started<timeoutMs);
 return {conversation,answer,attempts,waited_ms:Date.now()-started};
}

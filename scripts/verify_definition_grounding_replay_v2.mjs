/** Compare recorded locator corrections against original paid responses, read-only. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {definitionInput,expectedQuoteLocation} from './definition_evidence_v2.mjs';
import {digest,stableJson} from './validation_utils.mjs';
const args=process.argv.slice(2),arg=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const auditPath=path.resolve(arg('--audit','data/audit/9467d3ac-95ab-4519-8ab5-13ac7cae032c.jsonl'));
const replayPath=path.resolve(arg('--replay','benchmark/results/known-definition-clean1-grounding-replay.json'));
const output=path.resolve(arg('--output','benchmark/results/known-definition-clean1-grounding-independent-v2.json'));
const auditBytes=await fs.readFile(auditPath),replayBytes=await fs.readFile(replayPath),events=auditBytes.toString('utf8').trim().split('\n').map(JSON.parse),replay=JSON.parse(replayBytes);
const requests=new Map(events.filter(e=>e.type==='extraction_request').map(e=>[e.data.requestId,e.data])),results=new Map(events.filter(e=>e.type==='extraction_result').map(e=>[e.data.requestId,e.data]));
const checks=[];
for(const recorded of replay.responses){
 const errors=[],request=requests.get(recorded.request_id),result=results.get(recorded.request_id);
 if(!request||!result)throw Error('Actual request/response missing');
 if(request.runtime!=='Pi.ModelRuntime'||request.ownerRunId!==result.ownerRunId||result.stopReason!=='stop')errors.push('actual_owner_or_completion');
 if(digest(result.content)!==recorded.raw_response_sha256)errors.push('original_response_hash');
 const input=definitionInput(request.messages),body=JSON.parse(result.content),quoteChecks=[];
 for(const raw of body.extractions){
  const kind=raw.extraction_class??Object.keys(raw).find(key=>!key.endsWith('_attributes'));
  if(kind!=='definition_decision')continue;
  const marker=raw.extraction_text??raw[kind],groupId=marker.match(/^\[\[DEFINITION:([^\]]+)\]\]$/)?.[1],group=input.groups.get(groupId),attrs=raw.attributes??raw[kind+'_attributes'];
  if(!group){errors.push('unknown_source_group');continue;}
  const originals=JSON.parse(attrs.grounded_quotes_json),alignments=recorded.quote_alignments.find(item=>item.group_id===groupId)?.alignments??[],expected=[];
  for(const [index,quote] of originals.entries()){
   const location=expectedQuoteLocation(quote,group.sourceEvidence);
   if(location.error)errors.push(groupId+':'+location.error);
   if(location.alignment)expected.push({quote_index:index,...location.alignment});
   quoteChecks.push({group_id:groupId,quote_index:index,status:location.error?'failed':'passed',method:location.alignment?.method??'unchanged_exact',original_quote:quote,grounded_quote:location.quote,unicode_span:location.alignment?.span??null});
  }
  if(stableJson(expected)!==stableJson(alignments))errors.push(groupId+':recorded_locator_differs_from_independent_unique_match');
 }
 checks.push({request_id:recorded.request_id,owner_run_id:request.ownerRunId,status:errors.length?'failed':'passed',errors,input_hash:input.input_hash,quotes:quoteChecks});
}
const report={schema:'definition-grounding-independent-replay-2',created_at:new Date().toISOString(),status:checks.length&&checks.every(c=>c.status==='passed')?'passed':'failed',model_calls:0,database_writes:0,
 original_audit:{path:auditPath,sha256:digest(auditBytes)},recorded_replay:{path:replayPath,sha256:digest(replayBytes)},responses:{passed:checks.filter(c=>c.status==='passed').length,total:checks.length},
 quotes:{total:checks.reduce((n,c)=>n+c.quotes.length,0),aligned:checks.reduce((n,c)=>n+c.quotes.filter(q=>q.method!=='unchanged_exact').length,0)},checks,
 limitation:'Independent exact quotation locator and codepoint audit of unchanged original paid responses. Not a new model run, financial semantic score, or proof that originally rejected decisions were accepted in the database.'};
await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
console.log(JSON.stringify({status:report.status,responses:report.responses,quotes:report.quotes}));

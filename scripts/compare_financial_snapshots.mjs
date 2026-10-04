// Period corrections may change dates/year, but never source cells or money.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {decimalKey,stableJson,digest} from './validation_utils.mjs';
function sourceIdentity(fact){
 const source=fact.source_ref||{},meta=source.normalization||{};
 if(!source.document_id||!source.table_id||!source.row||!source.column)throw Error('Cannot verify a financial fact without source coordinates.');
 return stableJson({document_id:source.document_id,table_id:source.table_id,row:source.row,column:source.column,
  original_metric:fact.original_metric||meta.original_metric||fact.metric,scope:fact.scope,currency:fact.currency,dimensions:fact.dimensions||meta.dimensions||{}});
}
function immutableValue(fact){
 const source=fact.source_ref||{},value=decimalKey(fact.value);
 if(value===null)throw Error('Invalid decimal in financial snapshot.');
 return stableJson({source:sourceIdentity(fact),page:source.page,cell:source.cell,text:source.text,company:fact.company,
  value,raw_value:fact.raw_value,raw_unit:fact.raw_unit,normalized_unit:fact.normalized_unit,
  restatement:fact.restatement||fact.version||source.normalization?.restatement||'original'});
}
const period=fact=>({period:fact.period,start:fact.period_start??fact.source_ref?.normalization?.period_start??'',end:fact.period_end??fact.source_ref?.normalization?.period_end??'',year:fact.year});
const datesOnly=value=>({period:value?.period,start:value?.start||'',end:value?.end||''});
export function compareFinancialSnapshots(before,after,expectedAdditions=[]){
 const count=items=>{const counts=new Map();for(const fact of items){const signature=immutableValue(fact);counts.set(signature,(counts.get(signature)||0)+1);}return counts;};
 const prior=count(before),next=count(after),expected=count([...before,...expectedAdditions]),changedValues=[];
 const additions=expectedAdditions.map(fact=>{const key=immutableValue(fact);return {source:JSON.parse(sourceIdentity(fact)),value:fact.value,raw_value:fact.raw_value,raw_unit:fact.raw_unit,normalized_unit:fact.normalized_unit,expected_count:1,observed_count:(next.get(key)||0)-(prior.get(key)||0),passed:!prior.has(key)&&(next.get(key)||0)===1};});
 for(const key of new Set([...expected.keys(),...next.keys()]))if(expected.get(key)!==next.get(key))changedValues.push({invariant:JSON.parse(key),before_count:prior.get(key)||0,expected_after_count:expected.get(key)||0,after_count:next.get(key)||0});
 const group=items=>{const result=new Map();for(const fact of items){const key=sourceIdentity(fact);if(!result.has(key))result.set(key,[]);result.get(key).push(fact);}return result;};
 const oldGroups=group(before),newGroups=group(after),changes=[],ambiguous=[];
 for(const [key,old] of oldGroups){
  const fresh=newGroups.get(key)||[];
  if(old.length!==1||fresh.length!==1){ambiguous.push({source:JSON.parse(key),before_count:old.length,after_count:fresh.length});continue;}
  if(stableJson(period(old[0]))!==stableJson(period(fresh[0]))){
   const correction=fresh[0].source_ref?.normalization?.temporal_correction||null;
   changes.push({source:JSON.parse(key),before:period(old[0]),after:period(fresh[0]),value_before:old[0].value,value_after:fresh[0].value,raw_value:old[0].raw_value,raw_unit:old[0].raw_unit,temporal_correction:correction,
    evidence_matches_snapshots:!!correction&&stableJson(datesOnly(correction.before))===stableJson(datesOnly(period(old[0])))&&stableJson(datesOnly(correction.after))===stableJson(datesOnly(period(fresh[0])))&&fresh[0].year===Number(fresh[0].period.slice(0,4))});
  }
 }
 return {status:!before.length||changedValues.length||ambiguous.length||before.length+expectedAdditions.length!==after.length||additions.some(a=>!a.passed)||changes.some(c=>!c.evidence_matches_snapshots)?'failed':'passed',scope:'Source/value/unit preservation across a period review, with only individually specified source-backed recoveries allowed. Every changed period must carry matching before/after metadata; period correctness and actual model provenance require separate source/audit checks.',
  before_count:before.length,after_count:after.length,before_invariant_sha256:digest([...prior].sort()),expected_after_invariant_sha256:digest([...expected].sort()),after_invariant_sha256:digest([...next].sort()),expected_additions:additions,changed_immutable_values:changedValues,period_changes:changes,ambiguous_source_keys:ambiguous};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2),arg=key=>args.includes(key)?args[args.indexOf(key)+1]:null;
 const beforePath=arg('--before'),afterPath=arg('--after'),output=arg('--output');
 if(!beforePath||!afterPath||!output)throw Error('Provide --before SNAPSHOT --after SNAPSHOT --output REPORT');
 const before=JSON.parse(await fs.readFile(beforePath,'utf8')),after=JSON.parse(await fs.readFile(afterPath,'utf8'));
 if(before.project_id!==after.project_id)throw Error('Snapshots belong to different projects.');
 const allowPath=arg('--allowed-additions'),allowed=allowPath?JSON.parse(await fs.readFile(allowPath,'utf8')):null;
 if(allowed&&(allowed.project_id!==before.project_id||allowed.before_facts_sha256!==digest(before.facts)))throw Error('Addition allowlist is not bound to this exact project and before snapshot.');
 const result={project_id:before.project_id,before_snapshot:path.resolve(beforePath),after_snapshot:path.resolve(afterPath),allowed_additions:allowPath?{path:path.resolve(allowPath),sha256:digest(allowed)}:null,compared_at:new Date().toISOString(),...compareFinancialSnapshots(before.facts,after.facts,allowed?.facts||[])};
 await fs.writeFile(output,JSON.stringify(result,null,2),{flag:'wx'});
 console.log(JSON.stringify({output,status:result.status,before:result.before_count,after:result.after_count,period_changes:result.period_changes.length,changed_immutable_values:result.changed_immutable_values.length,ambiguous_sources:result.ambiguous_source_keys.length}));
 if(result.status!=='passed')process.exitCode=1;
}

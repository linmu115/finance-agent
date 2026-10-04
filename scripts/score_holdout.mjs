// Host-only scorer. No application imports, model calls, floating-point arithmetic,
// or inferred answers. The source-authored gold is immutable before inference.
import {decimalKey,checkFact} from './score_normalization.mjs';
import {stableJson} from './validation_utils.mjs';
const compact=value=>String(value??'').replace(/\s/g,'');
const rawNumber=value=>{const raw=String(value??'').replace(/[,，\s%％]/g,'');return decimalKey(/^\([^()]+\)$/.test(raw)?'-'+raw.slice(1,-1):raw);};
function semanticSignature(fact){
 const dims={...fact.dimensions};
 for(const key of ['movement','counterparty','source_page','page','table_id','row','column','source_id'])delete dims[key];
 return stableJson({metric:fact.metric,scope:fact.scope,dimensions:dims});
}
export function scoreHoldout(gold,relations,facts,documents){
 const files=new Map(documents.map(d=>[d.file,d.id]));
 const checks=gold.map(g=>{
  const document=files.get(g.input_file),allowedPeriods=[g.period,...g.period_variants];
  // Locate by source row and reported raw cell, independently of the model's
  // normalized metric/value. This still catches wrong scale, sign and meaning.
  const located=facts.filter(f=>(f.document_id||f.source_ref?.document_id)===document&&f.source_ref?.page===g.page&&compact(f.source_ref?.text).includes(compact(g.source_row_label))&&rawNumber(f.raw_value)===rawNumber(g.raw_value));
  const candidates=located.map(f=>{
   const expected={page:g.page,metric:g.metric,value:g.value,currency:g.currency,scope:g.scope,restatement:g.version,period:g.period,period_alternatives:g.period_variants};
   const errors=checkFact(expected,f),meta=f.source_ref?.normalization||{};
   if(f.normalized_unit!==g.currency)errors.push('normalized_unit');
   const rawUnit=compact(f.raw_unit).replaceAll('／','/');
   const unitPattern=g.currency==='percent'?/^(?:%|百分比|percent)$/i:g.currency==='CNY/share'?/^(?:人民币)?元\/股$|^CNY\/share$/i:/^(?:人民币)?元$|^CNY$/i;
   if(g.raw_unit_values?!g.raw_unit_values.some(unit=>compact(unit).replaceAll('／','/').toLowerCase()===rawUnit.toLowerCase()):!unitPattern.test(rawUnit))errors.push('raw_unit');
   const instant=g.period.length===10,start=f.period_start??meta.period_start??'',end=f.period_end??meta.period_end??'';
   if(instant?(start!==''||end!==f.period):(start!==g.period_start||end!==g.period_end))errors.push('period_bounds');
   if(g.definition_regex&&!new RegExp(g.definition_regex,'i').test([f.metric,f.label,JSON.stringify(f.dimensions||{}),JSON.stringify(f.semantic_correction?.after||{})].join(' ')))errors.push('concept_definition');
   if(f.source_ref.document_id!==document)errors.push('source_document');
   return {fact:f,errors};
  }).sort((a,b)=>a.errors.length-b.errors.length);
  const best=candidates[0],errors=best?[...best.errors]:['missing_fact'];
  if(best&&!errors.length){
   const sameCell=facts.filter(f=>f.source_ref?.document_id===document&&f.source_ref?.table_id===best.fact.source_ref.table_id&&f.source_ref?.row===best.fact.source_ref.row&&f.source_ref?.column===best.fact.source_ref.column);
   if(sameCell.some(f=>decimalKey(f.value)!==decimalKey(g.value)||f.currency!==g.currency||!allowedPeriods.includes(f.period)||semanticSignature(f)!==semanticSignature(best.fact)))errors.push('conflicting_source_cell');
  }
  return {id:g.id,file:g.input_file,status:errors.length?'failed':'passed',expected:{...g,metric:g.metric||g.concept},actual:best?.fact||null,errors,source_candidates:located.length};
 });
 const relationChecks=relations.map(relation=>{
  const members=checks.filter(c=>c.expected.company_id===relation.company_id&&relation.concepts.includes(c.expected.concept)),byConcept=new Map();
  for(const member of members){if(!byConcept.has(member.expected.concept))byConcept.set(member.expected.concept,new Set());if(member.actual)byConcept.get(member.expected.concept).add(semanticSignature(member.actual));}
  const overlapping=[];
  for(let i=0;i<relation.concepts.length;i++)for(let j=i+1;j<relation.concepts.length;j++){
   const [a,b]=[relation.concepts[i],relation.concepts[j]];
   if([...byConcept.get(a)||[]].some(signature=>byConcept.get(b)?.has(signature)))overlapping.push([a,b]);
  }
  return {id:relation.id,status:members.every(m=>m.status==='passed')&&byConcept.size===relation.concepts.length&&!overlapping.length?'passed':'failed',overlapping_concepts:overlapping,member_ids:members.map(m=>m.id)};
 });
 return {expected_facts:gold.length,passed_facts:checks.filter(c=>c.status==='passed').length,failed_facts:checks.filter(c=>c.status==='failed').length,checks,relations:relationChecks,failed_relations:relationChecks.filter(r=>r.status==='failed').length};
}

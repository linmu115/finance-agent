// Independent v0.5 scorer. Never imports application code or calls a model.
// Geometry and expected concepts must be locked from the original PDF first.
import {createHash} from 'node:crypto';

export const SCORER_VERSION='0.5.0';
const stable=value=>Array.isArray(value)?'['+value.map(stable).join(',')+']':value&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}':JSON.stringify(value);
export const signature=value=>createHash('sha256').update(stable(value)??'undefined').digest('hex');
export function exactDecimal(value){
 const m=String(value).trim().match(/^([+-]?)(\d+)(?:\.(\d+))?$/);if(!m)return null;
 const integer=m[2].replace(/^0+(?=\d)/,''),fraction=(m[3]||'').replace(/0+$/,'');
 return (m[1]==='-'&&(integer!=='0'||fraction)?'-':'')+integer+(fraction?'.'+fraction:'');
}
const compact=value=>String(value??'').replace(/\s/g,'').replaceAll('／','/');
const rawNumber=value=>{let v=compact(value).replace(/[,，%％]/g,'');const points=v.match(/^(增加|减少)?([+-]?\d+(?:\.\d+)?)个?百分点$/);if(points)v=(points[1]==='减少'?'-':'')+points[2];if(/^\([^()]+\)$/.test(v))v='-'+v.slice(1,-1);return exactDecimal(v);};
const validBox=b=>Array.isArray(b)&&b.length===4&&b.every(Number.isFinite)&&b[2]>b[0]&&b[3]>b[1];
const inside=(outer,inner,tolerance=1)=>validBox(outer)&&validBox(inner)&&outer[0]-tolerance<=inner[0]&&outer[1]-tolerance<=inner[1]&&outer[2]+tolerance>=inner[2]&&outer[3]+tolerance>=inner[3];
const overlaps=(a,b)=>validBox(a)&&validBox(b)&&Math.min(a[2],b[2])>Math.max(a[0],b[0])&&Math.min(a[3],b[3])>Math.max(a[1],b[1]);
const source=f=>f.source_ref||{};
const meta=f=>source(f).normalization||{};
const field=(f,name)=>f[name]??meta(f)[name];

export function checkFinancialCell(expected,actual){
 const errors=[],m=meta(actual),ref=source(actual),equal=(key,wanted,got)=>{if(wanted!==undefined&&stable(wanted)!==stable(got))errors.push(key);};
 if(exactDecimal(actual.value)===null||exactDecimal(actual.value)!==exactDecimal(expected.value))errors.push('value');
 if(rawNumber(actual.raw_value)===null||rawNumber(actual.raw_value)!==rawNumber(expected.raw_value))errors.push('raw_value');
 equal('currency',expected.currency,actual.currency);
 // Public API contract: percentage facts have currency=percent, display unit=%.
 equal('normalized_unit',expected.normalized_unit??(expected.currency==='percent'?'%':expected.currency),actual.normalized_unit);
 equal('unit_kind',expected.unit_kind,field(actual,'unit_kind'));
 if(expected.raw_unit_values&&!expected.raw_unit_values.some(u=>compact(u).toLowerCase()===compact(actual.raw_unit).toLowerCase()))errors.push('raw_unit');
 if(expected.metric)equal('metric',expected.metric,actual.metric);
 if(expected.label_regex&&!new RegExp(expected.label_regex,'iu').test(String(field(actual,'label')??''))&&!new RegExp(expected.label_regex,'iu').test(compact(field(actual,'label'))))errors.push('label');
 const definitionText=[actual.metric,field(actual,'label'),actual.definition,actual.definition_scope,actual.definition_review?.after?.definition,actual.definition_review?.after?.definition_scope,JSON.stringify(field(actual,'dimensions')||{})].join(' ');
 if(expected.definition_regex&&!new RegExp(expected.definition_regex,'iu').test(definitionText))errors.push('definition');
 if(expected.definition_forbidden_regex&&new RegExp(expected.definition_forbidden_regex,'iu').test(definitionText))errors.push('definition_exclusion');
 if(![expected.period,...(expected.period_variants||[])].includes(actual.period))errors.push('period');
 equal('period_start',expected.period_start,field(actual,'period_start')||'');
 equal('period_end',expected.period_end,field(actual,'period_end')||'');
 equal('scope',expected.scope,actual.scope);
 equal('version',expected.version,field(actual,'version')??field(actual,'restatement'));
 for(const [key,value] of Object.entries(expected.dimensions||{}))equal('dimension:'+key,value,field(actual,'dimensions')?.[key]);
 if(expected.dimensions_exact)equal('dimensions_exact',expected.dimensions,field(actual,'dimensions')||{});
 // Framework provenance is a separate workflow gate. A generic Pi baseline
 // must not lose financial accuracy merely for not using LangExtract.
 if(!ref.document_id||!Number.isInteger(ref.page)||!validBox(ref.bbox))errors.push('source_reference');
 return errors;
}

// A non-null reviewed flag is insufficient. The caller independently verifies
// raw Pi calls/cache/history and supplies proof records bound to exact metadata.
// Definition reviews legitimately supersede catalog aliases; no alias required.
export function validateReviewBinding(fact,proofs=[]){
 const m=meta(fact),definition=fact.definition_review??m.definition_review;
 const review=definition??fact.canonical_alias??m.canonical_alias;
 const kind=definition?'definition':'catalog',errors=[];
 if(!m.source_key||!m.source_fingerprint||!m.original_extraction_hash)errors.push('immutable_source_identity_missing');
 if(!review||review.status!=='reviewed'||review.engine!=='LangExtract')return {status:'failed',kind,errors:['review_missing']};
 const proof=proofs.find(p=>p.status==='passed'&&p.kind===kind&&p.source_key===m.source_key&&p.source_fingerprint===m.source_fingerprint&&p.review_sha256===signature(review));
 if(!proof||!proof.request_id||!proof.owner_run_id||!proof.extraction_signature||proof.original_extraction_hash!==m.original_extraction_hash)errors.push('actual_pi_proof_missing');
 if(kind==='definition'){
  if(review.source_key!==m.source_key||review.source_fingerprint!==m.source_fingerprint||review.original_extraction_hash!==m.original_extraction_hash)errors.push('review_source');
  if(review.owner_run_id!==proof?.owner_run_id||review.extraction_processing_id!==proof?.processing_id)errors.push('review_owner');
  if(!review.before?.metric||!review.before?.label||!review.grounded_quotes?.length||!proof?.before_history_verified||!proof?.quotes_verified)errors.push('definition_evidence');
  for(const key of ['metric','label','definition','definition_scope'])if(fact[key]!==review.after?.[key])errors.push('definition_after:'+key);
 }else if(review.canonical_metric!==fact.metric)errors.push('catalog_after');
 return {kind,status:errors.length?'failed':'passed',errors,request_id:proof?.request_id};
}

export function scoreFinancialTables(suite,facts,documents,{reviewProofs,requireReviewProof=false}={}){
 const files=new Map(documents.map(d=>[d.file,d.id])),cells=suite.cells||[],tables=suite.tables||[];
 const gold=cells.filter(c=>c.role==='fact'),ignored=cells.filter(c=>c.role!=='fact');
 const mapped=c=>files.get(c.input_file);
 if(new Set(cells.map(c=>c.id)).size!==cells.length)throw Error('Duplicate gold cell ID');
 if(!gold.length||gold.some(c=>!validBox(c.glyph_bbox)||!tables.some(t=>t.id===c.table_id)||!mapped(c)))throw Error('Incomplete locked whole-table geometry');
 for(const table of tables)if(table.complete!==true)throw Error('Only fully annotated tables may be scored');
 const locations=new Map(gold.map(c=>[c.id,[]])),extra=[],outOfScope=[],ambiguous=[],unscored=[];
 for(let index=0;index<facts.length;index++){
  const fact=facts[index],ref=source(fact),document=ref.document_id||fact.document_id;
  const pageTables=tables.filter(t=>mapped(t)===document&&t.page===ref.page);
  if(!pageTables.length){outOfScope.push(index);continue;}
  if(!validBox(ref.bbox)){extra.push({index,reason:'unverifiable_source_box',table_ids:pageTables.map(t=>t.id),actual:fact});continue;}
  const inTables=pageTables.filter(t=>overlaps(ref.bbox,t.bbox));
  if(!inTables.length){outOfScope.push(index);continue;}
  const possible=gold.filter(c=>mapped(c)===document&&c.page===ref.page&&inTables.some(t=>t.id===c.table_id)&&inside(ref.bbox,c.glyph_bbox));
  // A single-cell source locates independently of output value. For a row box,
  // require a unique reported raw token; equal repeated amounts stay ambiguous.
  const narrow=possible.length>1?possible.filter(c=>rawNumber(c.raw_value)!==null&&rawNumber(c.raw_value)===rawNumber(fact.raw_value)):possible;
  if(narrow.length===1){locations.get(narrow[0].id).push({index,fact});continue;}
  const ignoredHere=ignored.filter(c=>mapped(c)===document&&c.page===ref.page&&inside(ref.bbox,c.glyph_bbox||c.bbox));
  if(!narrow.length&&ignoredHere.length===1&&ignoredHere[0].role==='unscored'&&ignoredHere[0].allowed_values?.some(v=>exactDecimal(v)===exactDecimal(fact.value))){unscored.push({index,cell_id:ignoredHere[0].id,reason:ignoredHere[0].reason,actual:fact});continue;}
  const nonfact=ignoredHere.map(c=>({id:c.id,role:c.role,reason:c.reason}));
  const item={index,reason:narrow.length>1?'ambiguous_source_cell':nonfact.length?'nonfinancial_or_blank_source':'no_gold_cell',table_ids:inTables.map(t=>t.id),actual:fact,candidate_ids:narrow.map(c=>c.id),nonfact};
  extra.push(item);if(narrow.length>1)ambiguous.push(item);
 }
 const checks=gold.map(g=>{
  const candidates=locations.get(g.id),evaluated=candidates.map(({index,fact})=>({index,fact,errors:checkFinancialCell(g,fact)}));
  evaluated.sort((a,b)=>a.errors.length-b.errors.length||a.index-b.index);
  const best=evaluated[0],errors=best?[...best.errors]:['missing_fact'];
  const duplicates=evaluated.slice(1).map(c=>({index:c.index,actual:c.fact,errors:c.errors,kind:c.errors.length?'conflicting_duplicate':'equivalent_duplicate'}));
  for(const d of duplicates)extra.push({...d,reason:d.kind,gold_id:g.id,table_ids:[g.table_id]});
  if(duplicates.some(d=>d.kind==='conflicting_duplicate'))errors.push('conflicting_source_facts');
  const review=best&&requireReviewProof?validateReviewBinding(best.fact,reviewProofs):null;
  if(review?.status==='failed')errors.push(...review.errors.map(e=>'review:'+e));
  return {id:g.id,file:g.input_file,table_id:g.table_id,status:errors.length?'failed':'passed',expected:g,actual:best?.fact||null,errors,located_candidates:candidates.length,duplicates,review};
 });
 const passed=checks.filter(c=>c.status==='passed').length,missing=checks.filter(c=>c.errors.includes('missing_fact')).length;
 const predicted=checks.filter(c=>c.actual).length+extra.length;
 const severe=new Set(['value','currency','normalized_unit','raw_unit','unit_kind','metric','scope','definition','definition_exclusion','dimension','period','period_start','period_end','conflicting_source_facts']);
 const major=checks.filter(c=>c.errors.some(e=>severe.has(e)||e.startsWith('dimension:'))).map(c=>({id:c.id,errors:c.errors,expected:c.expected,actual:c.actual}));
 const normalization={expected_facts:gold.length,passed_facts:passed,failed_facts:gold.length-passed,checks};
 const groupScore=(selected,selectedExtras)=>{const good=selected.filter(c=>c.status==='passed').length,n=selected.filter(c=>c.actual).length+selectedExtras.length;return {expected:selected.length,passed:good,missing:selected.filter(c=>c.errors.includes('missing_fact')).length,false_extras:selectedExtras.length,predictions_in_scope:n,precision:n?good/n:0,recall:selected.length?good/selected.length:0};};
 const precision=predicted?passed/predicted:0,recall=passed/gold.length;
 return {version:SCORER_VERSION,...normalization,normalization,score:{decidable_gold:gold.length,correct:passed,missing,wrong:gold.length-passed-missing,predictions_in_scope:predicted,false_extras:extra.length,unverifiable_or_ambiguous:extra.filter(e=>['unverifiable_source_box','ambiguous_source_cell'].includes(e.reason)).length,exact_cell_recall:recall,recall,precision,major_error_count:major.length},acceptance:{precision_min:0.95,recall_min:0.95,statistical_gate_passed:precision>=0.95&&recall>=0.95,major_errors_require_independent_review:true},major_errors:major,false_extras:extra,out_of_scope_prediction_indexes:outOfScope,unscored_predictions:unscored,ambiguous_sources:ambiguous,table_scores:tables.map(t=>({table_id:t.id,...groupScore(checks.filter(c=>c.table_id===t.id),extra.filter(e=>e.table_ids?.includes(t.id)))})),company_scores:[...new Set(gold.map(g=>g.company_id))].map(company_id=>{const selected=checks.filter(c=>c.expected.company_id===company_id),ids=new Set(selected.map(c=>c.table_id));return {company_id,...groupScore(selected,extra.filter(e=>e.table_ids?.some(id=>ids.has(id))))};})};
}

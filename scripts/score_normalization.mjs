// Independent benchmark scorer. Does not import application code or use an LLM.
const legacyMetrics=new Set(['revenue','net_profit_parent','net_profit','operating_cash_flow','assets','equity_parent','liabilities','cost_of_revenue','gross_profit','net_profit_excluding_nonrecurring','eps','roe']);
const semanticLabels={revenue:/营业收入|(?:net\s+sales|revenue)/i,assets:/总资产|资产总(?:额|计)|total\s+assets/i,
 net_profit:/净利润|净亏损|net\s+(?:income|profit|loss)/i,net_profit_parent:/归母|归属于.*(?:母公司|股东)|attributable.*(?:parent|owner)/i,
 operating_cash_flow:/经营.*现金.*(?:净|额)|cash.*operating/i,eps:/每股收益|earnings\s+per\s+share/i,roe:/净资产收益率|return\s+on\s+equity/i};
export function decimalKey(value){
 const match=String(value).trim().match(/^([+-]?)(\d+)(?:\.(\d+))?$/);if(!match)return null;
 const whole=match[2].replace(/^0+(?=\d)/,''),fraction=(match[3]||'').replace(/0+$/,'');
 return (match[1]==='-'&&(whole!=='0'||fraction)?'-':'')+whole+(fraction?'.'+fraction:'');
}
export function checkFact(expected,actual){
 const source=actual.source_ref||actual.source||{},meta=source.normalization||{},errors=[];
 const field=(name)=>actual[name]??meta[name];
 if(expected.cell&&source.cell!==expected.cell)errors.push('source_cell');
 if(expected.page&&source.page!==expected.page)errors.push('source_page');
 if(expected.metric&&actual.metric!==expected.metric)errors.push('metric');
 if(expected.metric&&semanticLabels[expected.metric]&&!semanticLabels[expected.metric].test(field('label')||''))errors.push('semantic_metric_label');
 if(expected.new_metric&&legacyMetrics.has(actual.metric))errors.push('new_metric_not_created');
 if(expected.label_regex&&!new RegExp(expected.label_regex,'i').test(field('label')||''))errors.push('metric_label');
 if(![expected.period,...(expected.period_alternatives||[])].includes(actual.period))errors.push('period');
 if(decimalKey(actual.value)!==decimalKey(expected.value))errors.push('value');
 if(actual.currency!==expected.currency)errors.push('currency');
 if(expected.scope&&actual.scope!==expected.scope)errors.push('scope');
 if(expected.restatement&&(field('restatement')||field('version'))!==expected.restatement)errors.push('restatement');
 if(expected.start&&field('period_start')!==expected.start)errors.push('period_start');
 if(expected.end&&field('period_end')!==expected.end)errors.push('period_end');
 const dimensions=field('dimensions')||{},dimValues=Object.values(dimensions).map(String);
 for(const wanted of expected.dimension_values||[])if(!dimValues.some(value=>value.includes(wanted)))errors.push('dimension:'+wanted);
 if(expected.consolidated_dimension&&dimValues.some(value=>/华东|华南/.test(value)))errors.push('segment_instead_of_total');
 if(meta.engine!=='LangExtract')errors.push('not_langextract');
 if(!source.document_id||!source.table_id||!source.row||!source.column)errors.push('missing_source_coordinates');
 if(!Array.isArray(meta.char_interval)||meta.char_interval.length!==2||!(meta.char_interval[1]>meta.char_interval[0]))errors.push('missing_grounded_span');
 return errors;
}
export function scoreNormalization(gold,forbidden,facts,documents){
 const byFile=new Map(documents.map(d=>[d.file,d.id]));
 const checks=gold.filter(g=>byFile.has(g.file)).map(g=>{
  const documentId=byFile.get(g.file),all=facts.filter(f=>(f.document_id||f.source_ref?.document_id)===documentId);
  const located=all.filter(f=>g.cell?f.source_ref?.cell===g.cell:f.source_ref?.page===g.page&&f.metric===g.metric);
  const candidates=located.map(f=>({fact:f,errors:checkFact(g,f)})).sort((a,b)=>a.errors.length-b.errors.length);
  const best=candidates[0];
  // One correct value must not hide an additional contradictory fact for the
  // same source cell. PDF anchors may have other periods on the same page.
  const comparable=g.cell?located:located.filter(f=>[g.period,...(g.period_alternatives||[])].includes(f.period));
  const conflicts=best&&!best.errors.length?comparable.filter(f=>checkFact(g,f).length>0):[];
  const errors=best?[...best.errors,...(conflicts.length?['conflicting_source_facts']:[])]:['missing_fact'];
  return {id:g.id,file:g.file,status:best&&!errors.length?'passed':'failed',expected:g,actual:best?.fact||null,errors,candidates:located.length,...(conflicts.length?{conflicts}: {})};
 });
 const negatives=forbidden.filter(g=>byFile.has(g.file)).map(g=>{
  const bad=facts.filter(f=>(f.document_id||f.source_ref?.document_id)===byFile.get(g.file)&&f.source_ref?.cell===g.cell&&(!g.metric||f.metric===g.metric));
  return {file:g.file,cell:g.cell,status:bad.length?'failed':'passed',reason:g.reason,unexpected_facts:bad};
 });
 return {expected_facts:checks.length,passed_facts:checks.filter(x=>x.status==='passed').length,failed_facts:checks.filter(x=>x.status==='failed').length,
  forbidden_checks:negatives.length,failed_forbidden_checks:negatives.filter(x=>x.status==='failed').length,checks,negatives};
}

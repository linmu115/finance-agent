// Known disclosed-scope regressions: source material locked before review.
import fs from 'node:fs/promises';
import path from 'node:path';
import {decimalKey,stableJson,digest} from './validation_utils.mjs';
import {verifyDefinitionEvidence} from './definition_evidence.mjs';
const root=path.resolve(import.meta.dirname,'..'),args=process.argv.slice(2),arg=k=>args.includes(k)?args[args.indexOf(k)+1]:null;
const beforePath=arg('--before'),afterPath=arg('--after'),output=arg('--output');
if(!beforePath||!afterPath||!output)throw Error('Provide --before SNAPSHOT --after SNAPSHOT --output REPORT');
const before=JSON.parse(await fs.readFile(beforePath,'utf8')),after=JSON.parse(await fs.readFile(afterPath,'utf8'));
const oracle=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/known-disclosure-scope-assertions.json'),'utf8'));
if(before.project_id!==oracle.project_id||after.project_id!==oracle.project_id)throw Error('Wrong project');
if(digest(await fs.readFile(path.join(root,'samples/native-pdf/贵州茅台2024年年度报告.pdf')))!==oracle.source_sha256)throw Error('Original PDF changed');
const compact=s=>String(s||'').replace(/\s/g,''),checks=[];
function signature(f){const dims={...f.dimensions};for(const key of ['movement','counterparty','source_page','page','table_id','row','column','source_id'])delete dims[key];return stableJson({metric:f.metric,scope:f.scope,dimensions:dims});}
for(const gold of oracle.facts){
 const source=gold.source,found=after.facts.filter(f=>f.source_ref?.document_id===source.document_id&&f.source_ref.table_id===source.table_id&&f.source_ref.row===source.row&&f.source_ref.column===source.column),f=found[0],errors=[];
 if(found.length!==1)errors.push('source_cardinality');
 if(decimalKey(f?.value)!==decimalKey(gold.value)||f?.raw_value!==gold.raw_value)errors.push('exact_amount');
 if(f?.raw_unit!==gold.raw_unit||f?.currency!==gold.currency||f?.normalized_unit!==gold.currency||f?.scope!==gold.scope)errors.push('unit_currency_scope');
 if(f?.source_ref?.page!==source.original_page||compact(f?.source_ref?.text)!==compact(source.row_text))errors.push('original_source');
 const meaning=compact([f?.label,f?.definition,f?.definition_scope].join(' '));
 if(gold.id.startsWith('main_')&&!/主营/.test(meaning))errors.push('missing_main_business_definition');
 if(gold.id.startsWith('all_')&&!/全部营业|营业收入.*(?:合计|总额)|(?:含|括|及|和).*其他业务|总营业/.test(meaning))errors.push('missing_all_business_definition');
 if(gold.id==='other_total'&&!/其他业务/.test(meaning))errors.push('missing_other_business_definition');
 if(gold.id==='lease_current'&&!/一年内到期|流动部分/.test(meaning))errors.push('missing_current_maturity');
 if(gold.id==='lease_noncurrent'&&!/长期|非流动|不含一年内|扣除一年内/.test(meaning))errors.push('missing_noncurrent_maturity');
 if(gold.id==='lease_all'&&!/(?:含|包括).*一年内到期/.test(meaning))errors.push('missing_including_current_maturity');
 if(gold.id==='grant_income'&&!/与收益相关/.test(meaning))errors.push('missing_income_related_definition');
 if(gold.id==='grant_all'&&!/计入当期损益|与收益相关/.test(meaning))errors.push('missing_income_grants_definition');
 if(gold.id==='grant_nonrecurring'&&!/非经常|(?:除外|排除|不包括).*正常经营|正常经营.*(?:除外|排除)/.test(meaning))errors.push('missing_nonrecurring_exclusion');
 checks.push({id:gold.id,status:errors.length?'failed':'passed',errors,expected:gold,actual:f||null});
}
const byId=new Map(checks.map(c=>[c.id,c]));
const relations=oracle.assertions.map(relation=>({id:relation.id,checks:relation.different_definition_pairs.map(([a,b])=>({a,b,passed:byId.get(a)?.status==='passed'&&byId.get(b)?.status==='passed'&&signature(byId.get(a).actual)!==signature(byId.get(b).actual)}))}));
const provenance=await verifyDefinitionEvidence(after.project_id,before.facts,after.facts);
const report={scope:'15 previously known Moutai disclosure-scope regressions; not holdout. Source facts preserved and accepted definitions independently traced to owning Pi requests. Definition-stage archived rows separately prove no money/date/source mutation.',project_id:after.project_id,checked_at:new Date().toISOString(),before_facts_sha256:before.facts_sha256,after_facts_sha256:after.facts_sha256,oracle_sha256:digest(oracle),checks,relations,provenance};
report.status=checks.every(c=>c.status==='passed')&&relations.every(r=>r.checks.every(c=>c.passed))&&provenance.status==='passed'?'passed':'failed';
await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
console.log(JSON.stringify({output,status:report.status,anchors_passed:checks.filter(c=>c.status==='passed').length,anchors_total:checks.length,relation_pairs:relations.flatMap(r=>r.checks).filter(c=>c.passed).length,definition_facts:provenance.reviewed_facts,changed_definitions:provenance.changed_metric_or_label,provenance:provenance.status}));
if(report.status!=='passed')process.exitCode=1;

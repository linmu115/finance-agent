// Four source-reviewed regressions from the unchanged original annual report.
// This is a known-bug regression, separate from the frozen small benchmark.
import fs from 'node:fs/promises';
import path from 'node:path';
import {decimalKey,digest,extractionEvidence,extractionSignature} from './validation_utils.mjs';
const root=path.resolve(import.meta.dirname,'..'),args=process.argv.slice(2),arg=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
const afterPath=arg('--after'),output=arg('--output');
if(!afterPath||!output)throw Error('Provide --after SNAPSHOT --output REPORT');
const before=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/pi-full-report-v03-before-temporal-facts.json'),'utf8'));
const after=JSON.parse(await fs.readFile(afterPath,'utf8'));
if(before.project_id!==after.project_id)throw Error('Wrong project snapshot');
const document='39de9b118212463bbee6c2ab3c571432',table=document+':t104';
const source=path.join(root,'samples/native-pdf/贵州茅台2024年年度报告.pdf'),sourceHash=digest(await fs.readFile(source));
if(sourceHash!=='5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30')throw Error('Original source PDF changed');
const expected=[
 {row:5,column:3,value:'71147917165.03',label:'期初现金及现金等价物余额',original_metric:'cash_and_cash_equivalents_beginning_balance',periods:['2024-01-01','2023-12-31']},
 {row:5,column:4,value:'67960589067.53',label:'期初现金及现金等价物余额',original_metric:'cash_and_cash_equivalents_beginning_balance',periods:['2023-01-01','2022-12-31']},
 {row:6,column:3,value:'76517140680.50',label:'期末现金及现金等价物余额',original_metric:'cash_and_cash_equivalents_ending_balance',periods:['2024-12-31']},
 {row:6,column:4,value:'71147917165.03',label:'期末现金及现金等价物余额',original_metric:'cash_and_cash_equivalents_ending_balance',periods:['2023-12-31']}
];
const owners=new Map(),checks=[];
for(const gold of expected){
 const match=f=>f.source_ref?.document_id===document&&f.source_ref?.table_id===table&&f.source_ref.row===gold.row&&f.source_ref.column===gold.column;
 const old=before.facts.filter(match),found=after.facts.filter(match),fact=found[0],meta=fact?.source_ref?.normalization?.temporal_correction;
 if(meta?.owner_run_id&&!owners.has(meta.owner_run_id)){
  const events=(await fs.readFile(path.join(root,'data/audit',meta.owner_run_id+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
  owners.set(meta.owner_run_id,extractionEvidence(events,meta.owner_run_id));
 }
 const proof=owners.get(meta?.owner_run_id),signature=meta&&extractionSignature({class:'temporal_correction',text:'[[SOURCE:'+meta.source_key+']]',attributes:{period:meta.after.period,start:meta.after.start,end:meta.after.end,reason:meta.reason,evidence:meta.evidence}});
 const errors=[];
 if(old.length!==1||!/^202[34]-FY$/.test(old[0]?.period))errors.push('before_snapshot_does_not_demonstrate_known_duration_error');
 if(found.length!==1)errors.push('source_cardinality');
 if(decimalKey(fact?.value)!==decimalKey(gold.value)||decimalKey(old[0]?.value)!==decimalKey(gold.value))errors.push('amount');
 if(fact?.currency!=='CNY'||fact?.normalized_unit!=='CNY'||fact?.raw_unit!=='元'||fact?.scope!=='parent_CAS')errors.push('currency_unit_scope');
 if((fact?.original_metric||fact?.metric)!==gold.original_metric)errors.push('source_concept');
 if(!gold.periods.includes(fact?.period)||fact?.period_start!==''||fact?.period_end!==fact?.period)errors.push('instant_period');
 if(!meta||!proof?.valid_owners||!proof.temporal_correction_signatures.includes(signature)||meta.before.period!==old[0]?.period||meta.after.period!==fact?.period)errors.push('actual_pi_correction_evidence');
 checks.push({source:{document_id:document,table_id:table,page:69,row:gold.row,column:gold.column},expected:gold,before:old.map(f=>({value:f.value,period:f.period})),after:found.map(f=>({value:f.value,period:f.period,start:f.period_start,end:f.period_end,original_metric:f.original_metric,scope:f.scope,temporal_correction:meta})),status:errors.length?'failed':'passed',errors});
}
const report={scope:'Known period-error regression independently read from native PDF pages 68–69; not a blind or exhaustive annual-report accuracy benchmark.',source_pdf:source,source_sha256:sourceHash,source_header:{page:68,title:'母公司现金流量表',reporting_interval:'2024 年1—12 月',columns:['2024年度','2023年度'],unit:'元',currency:'人民币'},opening_balance_convention:'Opening balance may use the first day of the financial year or the preceding year-end boundary, both as an instant with empty period_start. Year-long periods are rejected.',project_id:after.project_id,before_sha256:before.facts_sha256,after_sha256:after.facts_sha256,checked_at:new Date().toISOString(),status:checks.every(c=>c.status==='passed')?'passed':'failed',checks};
await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
console.log(JSON.stringify({output,status:report.status,passed:checks.filter(c=>c.status==='passed').length,total:checks.length}));
if(report.status!=='passed')process.exitCode=1;

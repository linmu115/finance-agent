// Read-only correction of a pre-discovered host scoring contract error.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest} from './validation_utils.mjs';
export function correctPublishedPercentUnit(original){
 const report=structuredClone(original),changes=[];
 for(const item of report.normalization.checks){
  if(item.expected.currency==='percent'&&item.actual?.currency==='percent'&&item.actual.normalized_unit==='%'&&item.errors.includes('normalized_unit')){
   changes.push({id:item.id,removed_error:'normalized_unit',actual_currency:'percent',actual_normalized_unit:'%',remaining_errors:item.errors.filter(e=>e!=='normalized_unit')});
   item.errors=item.errors.filter(e=>e!=='normalized_unit');item.status=item.errors.length?'failed':'passed';
  }
 }
 report.normalization.passed_facts=report.normalization.checks.filter(c=>c.status==='passed').length;
 report.normalization.failed_facts=report.normalization.checks.length-report.normalization.passed_facts;
 report.score={passed:report.normalization.passed_facts,total:report.normalization.checks.length,failed:report.normalization.failed_facts};
 for(const check of report.checks)if(check.name==='30个独立源格逐项核对'){
  check.status=report.normalization.failed_facts?'failed':'passed';check.evidence={...report.score,failed_ids:report.normalization.checks.filter(c=>c.status==='failed').map(c=>c.id)};
 }
 report.status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
 return {report,changes};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2),arg=k=>args.includes(k)?args[args.indexOf(k)+1]:null,input=arg('--report'),output=arg('--output');
 if(!input||!output)throw Error('Provide --report original.json --output independent-rescore.json');
 const bytes=await fs.readFile(input),original=JSON.parse(bytes);
 if(!original.finished_at||original.status==='running'||!original.normalization?.checks)throw Error('The original run and original scoring must have finished first');
 const {report,changes}=correctPublishedPercentUnit(original);
 const result={...report,kind:'same_run_read_only_scorer_contract_correction',rescored_at:new Date().toISOString(),original_report:{path:path.resolve(input),sha256:digest(bytes),status:original.status,score:original.score},rescore:{additional_model_calls:0,new_run_created:false,gold_modified:false,scope:'Only normalized_unit % with expected and actual currency percent satisfies the published API contract. Other score and workflow failures are copied unchanged.',discovery:'benchmark/results/holdout-v041-scorer-unit-contract-discovery.json',changed_checks:changes,scorer_sha256:digest(await fs.readFile(fileURLToPath(import.meta.url)))}};
 await fs.writeFile(output,JSON.stringify(result,null,2),{flag:'wx'});console.log(JSON.stringify({output,status:result.status,original_score:original.score,rescored:result.score,changed_checks:changes.length}));
}

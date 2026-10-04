// Independent host-only review; preserves the frozen benchmark and official score.
import fs from 'node:fs/promises';
const source='benchmark/results/pi-workflow-4c1fddcc-8854-4415-b687-81fdc15ede67.json';
const report=JSON.parse(await fs.readFile(source,'utf8'));
const failed=report.normalization.checks.filter(c=>c.status==='failed');
const ppe=failed.find(c=>c.id==='02_usd_million_cashflow_B6_2025-FY');
const assets=failed.find(c=>c.id==='native_assets_2024');
if(failed.length!==2||!ppe||!assets)throw Error('Source report differs from the reviewed evidence; stop instead of substituting expected conclusions.');
if(ppe.errors.join(',')!=='metric_label'||assets.errors.join(',')!=='period')throw Error('Failure types differ from the independent review.');
const review={
 source_report:source,reviewed_at:new Date().toISOString(),official_status:report.status,official_gold_score:'35/37',
 official_flow_score:report.checks.filter(c=>c.status==='passed').length+'/'+report.checks.length,
 original_report_changed:false,gold_changed:false,new_model_calls:0,
 findings:[
  {id:ppe.id,classification:'benchmark_false_negative',reason:'The frozen label regex omits an equivalent Chinese wording for the original English PPE purchase cash-flow item. The actual dynamic metric, cash-flow direction, exact base-currency amount, period, currency and scope agree with the source. This observation does not overwrite the official automated failure.',
   original_cell_text:ppe.actual.source_ref.text,expected_label_regex:ppe.expected.label_regex,
   actual_metric:ppe.actual.metric,actual_label:ppe.actual.label,expected_value:ppe.expected.value,actual_value:ppe.actual.value,
   currency:ppe.actual.currency,scope:ppe.actual.scope,period:ppe.actual.period},
  {id:assets.id,classification:'application_period_error',reason:'Total assets are a stock at the reporting date. The date endpoint is present, but the stored period ID is a fiscal-year duration; date-filtered queries will not identify it as the expected balance-sheet instant. Correct the semantic period mapping without changing the raw numeric amount.',
   expected_period:assets.expected.period,actual_period:assets.actual.period,actual_period_start:assets.actual.period_start,actual_period_end:assets.actual.period_end,
   expected_value:assets.expected.value,actual_value:assets.actual.value,physical_original_pdf_page:assets.expected.original_page,source_ref:assets.actual.source_ref}
 ],
 scope:'Two narrowly identified differences in a frozen developer regression suite. The official score remains 35/37. No inference about exhaustive annual-report accuracy.'
};
await fs.writeFile('benchmark/results/pi-workflow-v03-final-independent-review.json',JSON.stringify(review,null,2));
console.log(JSON.stringify({official_score:review.official_gold_score,findings:review.findings.map(f=>({id:f.id,classification:f.classification}))}));

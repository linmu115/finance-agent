import {readFile,writeFile} from 'node:fs/promises';
import {modelContext} from '../server/model-context.js';
const dir='data/evaluation/'+(process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261006');
const state=JSON.parse(await readFile(dir+'/experiment.json','utf8'));
const rows=[];
for(const run of state.runs.filter((r:any)=>r.status==='completed')){
 const events=(await readFile(`${dir}/${run.label}-audit.jsonl`,'utf8')).trim().split('\n').map(JSON.parse);
 const requests=events.filter(e=>e.type==='tool_request');
 const analyses=requests.filter(e=>e.data.name==='run_analysis').map(e=>e.data.params||e.data.args);
 const models=requests.filter(e=>e.data.name==='run_financial_model').map(e=>e.data.params||e.data.args);
 const results=events.filter(e=>e.type==='tool_result'&&['get_data_catalog','query_financial_data','query_research_records'].includes(e.data.name));
 const manifest=JSON.parse(await readFile(`${dir}/${run.label}-deliverables.json`,'utf8'));
 rows.push({label:run.label,analysis_calls:analyses.length,
  full_script_chars:analyses.reduce((n,x)=>n+(x.code?.length||0),0),
  patch_calls:analyses.filter(x=>x.source_run_id&&x.edits?.length).length,
  patch_chars:analyses.reduce((n,x)=>n+(x.edits?.length?JSON.stringify(x.edits).length:0),0),
  selected_model_calls:analyses.filter(x=>Object.keys(x.model_refs||{}).length).length,
  selected_comparison_calls:analyses.filter(x=>Object.keys(x.comparisons||{}).length).length,
  model_calls:models.length,bound_record_inputs:models.reduce((n,x)=>n+Object.keys(x.bindings||{}).length,0),
  query_rows:results.reduce((n,x)=>n+(x.data.result.data?.items?.length||0),0),
  query_raw_chars:results.reduce((n,x)=>n+JSON.stringify(x.data.result).length,0),
  query_model_chars:results.reduce((n,x)=>n+JSON.stringify(modelContext(x.data.name,x.data.result)).length,0),
  failed_sandbox_attempts:manifest.evaluatorScripts.filter((s:any)=>s.status!=='succeeded').length,
  tool_errors:events.filter(e=>e.type==='tool_error').map(e=>({name:e.data.name,message:e.data.message})),
  successful_sandbox_attempts:manifest.evaluatorScripts.filter((s:any)=>s.status==='succeeded').length,
 });
}
await writeFile(dir+'/reuse-metrics.json',JSON.stringify(rows,null,2));console.log(JSON.stringify(rows));

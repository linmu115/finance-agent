// Replay recorded queries offline; no model/API calls and no mutation of evidence.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {modelContext} from '../server/model-context.js';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const priorRevision=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
const priorPath=path.resolve('data/evaluation/pi-analysis-20261006/released-model-context.ts');
await writeFile(priorPath,execFileSync('git',['show',priorRevision+':server/model-context.ts'],{encoding:'utf8'}));
const prior=(await import(pathToFileURL(priorPath).href)).modelContext;
const audit=(await readFile('data/evaluation/pi-analysis-20261005-r2/C1-audit.jsonl','utf8')).trim().split('\n').map(JSON.parse);
const checks=[];
for(const event of audit.filter(e=>e.type==='tool_result'&&['query_financial_data','get_data_catalog'].includes(e.data.name))){
 const {name,result}=event.data,before=JSON.stringify(result),out=modelContext(name,result);
 for(let i=0;i<(result.data.items?.length||0);i++){
  const a=result.data.items[i],b=out.data.items[i];
  for(const k of ['fact_id','value','raw_value','raw_unit','normalized_unit','currency','period','scope','quality','unit_kind','numeric_span','version','definition','dimensions'])
   if(a[k]!==null&&a[k]!==undefined&&a[k]!==''&&JSON.stringify(a[k])!=='{}')assert.deepEqual(b[k],a[k]);
  for(const k of ['document_id','page','table_id','row','column','cell'])assert.deepEqual(b.source_ref[k],a.source_ref[k]);
  for(const k of ['review_warnings','semantic_review_note'])assert.deepEqual(b.source_ref.normalization?.[k],a.source_ref.normalization?.[k]);
 }
 assert.equal(JSON.stringify(result),before);
 checks.push({name,rows:out.data.items?.length,rawChars:before.length,priorModelChars:JSON.stringify(prior(name,result)).length,analysisChars:JSON.stringify(out).length});
}
await mkdir('docs/evidence/pi-analysis-20261006',{recursive:true});
await writeFile('docs/evidence/pi-analysis-20261006/offline-projection.json',JSON.stringify({priorRevision,checks,scope:'Checked-in projection versus current projection on identical recorded queries. Exact recorded numerical fields, units, basis, uncertainty and source coordinates retained; counts are characters, not billed tokens.'},null,2));
console.log(JSON.stringify(checks));

/** Independent zero-call inspection of one actual historical length receipt. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {validateHistoricalDefinitionLimit} from './definition_evidence_v2.mjs';
import {digest} from './validation_utils.mjs';
const root=path.resolve(import.meta.dirname,'..'),input=path.join(root,'benchmark/results/known-definition-clean2-historical-limit-verified.json'),raw=await fs.readFile(input),record=JSON.parse(raw),execute=promisify(execFile);
const {stdout}=await execute(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/export_definition_evidence_v2.py'),'--project','3b4c43c9-51b8-432c-807d-2a15323f7a80'],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:48*1024*1024}),saved=JSON.parse(stdout),checks=[];
for(const entry of record.proofs){
 const audit=await fs.readFile(path.join(root,'data/audit',entry.original_owner_run_id+'.jsonl')),events=audit.toString('utf8').trim().split('\n').map(JSON.parse);
 checks.push(validateHistoricalDefinitionLimit(entry,{events,auditSha256:digest(audit),reviews:saved.reviews,currentFingerprints:saved.source_fingerprints,projectDocumentIds:saved.project_document_ids}));
}
const result={kind:'independent_original_length_record_v2',created_at:new Date().toISOString(),status:checks.length&&checks.every(c=>c.status==='passed')?'passed':'failed',source:{path:input,sha256:digest(raw)},model_calls:0,database_writes:0,schedule_not_executed:true,checks,
 limitations:['Original receipt proof only; no new model request, no current split execution or new financial result is inferred.','Current full LangExtract template generation equality is covered by separate production tests and known-definition-clean2-full-prompt-match.json, not imported or silently assumed by this independent original-record check.']};
await fs.writeFile(path.join(root,'benchmark/results/known-definition-clean2-historical-limit-independent-v2.json'),JSON.stringify(result,null,2),{flag:'wx'});console.log(JSON.stringify({status:result.status,checks:checks.map(c=>({status:c.status,errors:c.errors,source_count:c.source_count}))}));

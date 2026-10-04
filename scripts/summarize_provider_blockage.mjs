// Host-side evidence summary. Never calls the API or reads settings/credentials.
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const reportPath='benchmark/results/pi-workflow-0a2f1e99-5240-46f1-86c8-54e021f22ac4.json';
const report=JSON.parse(await fs.readFile(path.join(root,reportPath),'utf8'));
const redact=value=>String(value||'').replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');
const failures=[];
for(const run of [...report.runs,...(report.followup_run?[report.followup_run]:[])]){
 if(!/402|Insufficient Balance/i.test(run.error||''))continue;
 const events=(await fs.readFile(path.join(root,'data/audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 const errors=events.filter(e=>e.type==='event'&&e.data?.type==='error'&&/402|Insufficient Balance/i.test(e.data?.data?.message||''));
 failures.push({run_id:run.id,conversation_id:run.conversationId,status:run.status,finished_at:run.finishedAt,error:redact(run.error),audit_path:'data/audit/'+run.id+'.jsonl',audit_error_events:errors.map(e=>({at:e.at,message:redact(e.data.data.message)}))});
}
if(!failures.length)throw new Error('The preserved report has no provider balance failure evidence.');
const summary={
 version:'v0.3',recorded_at:new Date().toISOString(),classification:'provider_balance_insufficient',http_status:402,
 provider:'Official DeepSeek API',source_report:reportPath,
 report_url:'http://127.0.0.1:3001/api/benchmark/run/0a2f1e99-5240-46f1-86c8-54e021f22ac4',
 run_started_at:report.started_at,run_finished_at:report.finished_at,end_to_end_status:report.status,
 completed_data:{documents:report.documents.length,facts:report.fact_count,gold_passed:report.normalization.passed_facts,gold_total:report.normalization.expected_facts,forbidden_failed:report.normalization.failed_forbidden_checks},
 implementation_changed_during_run:report.implementation_changed_during_run,failures,
 scope:'Point-in-time evidence: extraction gold passed; complete conversation acceptance failed when the provider returned HTTP 402. This does not establish the current account balance. Preserved source report and historical passing report were not modified.'
};
const output=path.join(root,'benchmark/results/provider-blockage-v03.json');
await fs.writeFile(output,JSON.stringify(summary,null,2));
console.log(JSON.stringify({output,failures:failures.length,first_error_at:failures.flatMap(f=>f.audit_error_events).map(e=>e.at).sort()[0]}));

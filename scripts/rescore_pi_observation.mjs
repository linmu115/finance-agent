// One failed observation can be re-read without new model calls. Preserve source report.
import fs from 'node:fs/promises';
import path from 'node:path';
import {digest,readPersistedRunAnswer} from './validation_utils.mjs';
const args=process.argv.slice(2),arg=key=>args.includes(key)?args[args.indexOf(key)+1]:null;
const input=arg('--report'),output=arg('--output'),base=arg('--base-url')||'http://127.0.0.1:3001';
if(!input||!output)throw Error('Provide --report ORIGINAL --output NEW_REPORT');
const text=await fs.readFile(input,'utf8'),original=JSON.parse(text),target='同一 Pi 会话下一轮保留自己的上下文并查询共享目录';
const failed=original.checks.filter(c=>c.status==='failed');
if(failed.length!==1||failed[0].name!==target||failed[0].evidence?.answer!==''||original.followup_run?.status!=='completed')throw Error('This correction is restricted to the evidenced blank-persisted-reply observation race.');
const request=async route=>{const response=await fetch(base+route);if(!response.ok)throw Error('HTTP '+response.status);return response.json();};
const run=await request('/api/runs/'+original.followup_run_id);
const persisted=await readPersistedRunAnswer(()=>request('/api/conversations/'+original.conversation_ids[0]),run.id);
const answer=persisted.answer,marker=original.session_markers[0],other=original.session_markers[1];
const passed=run.status==='completed'&&answer?.content.includes(marker)&&!answer?.content.includes(other)&&run.tools.some(t=>t.name==='get_data_catalog');
const report={...original,checks:original.checks.map(c=>c.name===target?{name:target,status:passed?'passed':'failed',evidence:{run_id:run.id,status:run.status,message_id:answer?.id,expected_session_marker:marker,answer:answer?.content}}:c),
 observation_rescore:{created_at:new Date().toISOString(),original_report:path.resolve(input),original_report_sha256:digest(text),original_status:original.status,model_calls:0,new_run_created:false,
 reason:'The completed run state preceded the final conversation-state write. The original report observed an empty reply; this separate report reads the same run/message after persistence.',reread_check:target,read_attempts:persisted.attempts,all_other_checks:'Retained from the original run; not re-executed.',source_report_preserved:true}};
report.status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
if(digest(await fs.readFile(input,'utf8'))!==digest(text))throw Error('Source report changed during read-only rescore');
console.log(JSON.stringify({output,status:report.status,checks:report.checks.length,passed:report.checks.filter(c=>c.status==='passed').length,model_calls:0,source_sha256:digest(text)}));
if(report.status!=='passed')process.exitCode=1;

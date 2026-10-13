// Actual first financial trace only; no model calls or changed participant inputs.
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const name='blind-eval-F21-gate-20261009',dir=path.resolve('data/evaluation',name),file=path.join(dir,'experiment.json');
const s=JSON.parse(await fs.readFile(file,'utf8')),r=s.runs.find(r=>r.profile==='financial');
if(s.freeze.version!=='F2.1'||r.status!=='completed'||s.runs.filter(r=>r.runId).length!==3)throw Error('First financial terminal inspection boundary differs');
const events=(await fs.readFile(path.join(dir,r.label+'-audit.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
const plots=events.filter(e=>e.type==='tool_result').flatMap(e=>(e.data.result?.data?.plot_diagnostics?.files||[]).map(p=>({tool:e.data.name,at:e.at,...p})));
const c=events.filter(e=>e.type==='answer_direction_notices'||(e.type==='answer_consistency_issues'&&e.data.issues?.some(i=>String(i.kind).startsWith('direction'))));
if(!plots.length||!plots.every(p=>Array.isArray(p.waterfall_issues))||!c.length)throw Error('Required live B/C diagnostic fields not observed');
execFileSync(process.execPath,['benchmark/blind-eval/runner-v3-gate.mjs','verify',name],{windowsHide:true});
const health=await(await fetch('http://127.0.0.1:3001/api/health')).json();if(!health.ok||health.service!=='connected')throw Error('Service disconnected');
const receipt={passed:true,at:new Date().toISOString(),version:'F2.1',runId:r.runId,label:r.label,health,B:{field:'tool_result.data.result.data.plot_diagnostics.files[].waterfall_issues',records:plots},C:{events:c},judgment:'Presence only. A diagnostic is not proof of a financial defect or successful correction.',remaining:15};
await fs.writeFile(path.join(dir,'first-financial-inspection.json'),JSON.stringify(receipt,null,2)+'\n');s.firstFinancialInspection={passed:true,at:receipt.at,receipt:'first-financial-inspection.json'};
await fs.writeFile(file+'.tmp',JSON.stringify(s,null,2)+'\n');await fs.rename(file+'.tmp',file);
console.log(JSON.stringify({passed:true,service:health.service,B_records:plots.length,C_events:c.length,remaining:15}));

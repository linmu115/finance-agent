// Read-only host capture of an already dispatched run while STOP.json remains.
// Does not submit, cancel, retry, or lift the submission pause.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {canonical} from './study-f14.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const [name,label]=process.argv.slice(2);
if(!/^blind-eval-[\w.-]+$/.test(name||''))throw Error('Expected blind-eval study');
const dir=path.join(root,'data/evaluation',name);
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const write=async(p,x)=>fs.writeFile(p,JSON.stringify(x,null,2)+'\n');
await fs.access(path.join(dir,'STOP.json'));
const state=await read(path.join(dir,'experiment.json'));
const row=state.runs.find(r=>r.label===label);
if(!row?.runId||!['running','queued'].includes(row.status))throw Error('Expected already dispatched pending run');
const get=async route=>{
 const response=await fetch('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(120000)});
 if(!response.ok)throw Error(`${route}: ${response.status}`);
 return response.json();
};
const run=await get('/api/runs/'+row.runId);
const chat=await get('/api/conversations/'+row.conversationId);
await write(path.join(dir,label+'-run.json'),run);
await write(path.join(dir,label+'-conversation.json'),chat);
if(run.request?.evaluation?.isolation_key!==row.isolationKey||chat.evaluationIsolationKey!==row.isolationKey||run.conversationId!==row.conversationId)throw Error('Isolation mismatch; original response preserved');
await fs.copyFile(path.join(root,'data/active/audit',row.runId+'.jsonl'),path.join(dir,label+'-audit.jsonl'));
const events=(await fs.readFile(path.join(dir,label+'-audit.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
const config=events.find(e=>e.type==='run_config')?.data;
const expected=(await read(path.join(dir,'deployment-receipt.json'))).analysisOnlyProfiles[row.profile].tools;
const match=run.request?.evaluation?.analysis_only===true&&config?.analysis_only===true&&canonical([...config.tools].sort())===canonical([...expected].sort());
await write(path.join(dir,label+'-analysis-only-receipt.json'),{request_analysis_only:run.request.evaluation.analysis_only,run_config_analysis_only:config?.analysis_only??null,actual_tools:config?.tools??null,expected_tools:expected,matches:match});
if(!match)throw Error('Actual analysis-only tools do not match frozen configuration');
const answers=chat.messages.filter(m=>m.role==='assistant'&&m.runId===run.id);
Object.assign(row,{status:run.status,usage:run.usage??null,error:run.error??null,completedAt:run.finishedAt??null,hasDeliveredAnswer:answers.some(m=>m.content?.trim()&&m.artifacts?.length)});
await write(path.join(dir,'experiment.json.tmp'),state);
await fs.rename(path.join(dir,'experiment.json.tmp'),path.join(dir,'experiment.json'));
await write(path.join(dir,label+'-paused-capture-receipt.json'),{at:new Date().toISOString(),label,runId:run.id,status:run.status,methods:['GET','GET'],paidSubmissions:0,submissionPausePreserved:true});
console.log(JSON.stringify({label,status:run.status,calls:run.usage?.calls,unknownCalls:run.usage?.unknownCalls,submissionPausePreserved:true}));

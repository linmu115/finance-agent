// Append an authorized frozen project only while the participant dispatcher is idle.
// Never changes planned order, keys, question text, code freeze or submitted runs.
import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {digest} from './study-v3-formal.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const base=path.join(root,'data/evaluation/blind-eval-F21-formal-private-20261009');
const [folderName]=process.argv.slice(2);
if(!['yili-freeze','haier-freeze'].includes(folderName))throw Error('Expected an authorized project freeze directory');
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const file=path.join(base,'experiment.json'),before=await fs.readFile(file);
const state=JSON.parse(before.toString('utf8'));
if(existsSync(path.join(base,'worker.lock'))||existsSync(path.join(base,'DRAIN.json'))||state.stopReason||state.runs.some(r=>['running','queued','submitting'].includes(r.status)))throw Error('Dispatcher must be idle and not stopped by an exception');
const folder=path.join(base,folderName),receipt=await read(path.join(folder,'freeze-receipt.json'));
const project=receipt.project_id;
if(state.projectFreezes[project]||state.runs.some(r=>r.projectId===project&&r.status!=='planned'))throw Error('Project has already been admitted or submitted');
const data=(await read(path.join(folder,'material-snapshot.json')))[project];
if(digest(data)!==receipt.snapshot_sha256)throw Error('Frozen project digest mismatch');
const current=JSON.parse(execFileSync(path.join(root,'.venv/Scripts/python.exe'),['-B','benchmark/blind-eval/snapshot-f14.py',project],{
  cwd:root,windowsHide:true,encoding:'utf8',maxBuffer:512*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8'}}))[project];
if(digest(current)!==receipt.snapshot_sha256)throw Error('Project data changed after freeze');
const response=await fetch('http://127.0.0.1:3001/api/projects/'+project+'/conversations');
if(!response.ok)throw Error('Cannot confirm idle project');
if((await response.json()).conversations.some(c=>c.activeRunId))throw Error('Project has an active run');
const at=new Date().toISOString();
state.projectFreezes[project]={at,sha256:receipt.snapshot_sha256,
  documents:data.documents.map(d=>({document_id:d.document_id,status:d.status})),idleAtFreeze:true,
  snapshotFile:folderName+'/material-snapshot.json',receiptFile:folderName+'/freeze-receipt.json'};
const archive=path.join(folder,'experiment-before-admission.json');
await fs.writeFile(archive,before,{flag:'wx'});
if(!(await fs.readFile(file)).equals(before))throw Error('Dispatcher state changed during admission');
await fs.writeFile(file+'.tmp',JSON.stringify(state,null,2)+'\n');await fs.rename(file+'.tmp',file);
await fs.writeFile(path.join(folder,'admission-receipt.json'),JSON.stringify({at,project_id:project,
  snapshot_sha256:receipt.snapshot_sha256,planned_order_unchanged:true,isolation_keys_unchanged:true,
  admitted_positions:state.runs.filter(r=>r.projectId===project).length,participant_requests:0,
  previous_state_sha256:digest(before),state_sha256:digest(await fs.readFile(file))},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({admitted:project,positions:state.runs.filter(r=>r.projectId===project).length,participant_requests:0}));

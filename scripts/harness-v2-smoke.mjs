// One real conversation per authorized feature; preserve the full trace for review.
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
const label=process.argv[2],promptFile=process.argv[3];
if(!label||!promptFile)throw Error('Usage: node scripts/harness-v2-smoke.mjs A0 prompt.txt');
const dir=path.resolve('data/evaluation/harness-v2-smoke-20261007');await fs.mkdir(dir,{recursive:true});
const output=path.join(dir,label+'.json');
try{await fs.access(output);throw Error('This feature already has a smoke record; do not spend twice.');}catch(e){if(e.code!=='ENOENT')throw e;}
const api=async(url,body)=>{const r=await fetch('http://127.0.0.1:3001/api'+url,{method:body?'POST':'GET',headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined});const v=await r.json();if(!r.ok)throw Error(JSON.stringify(v));return v;};
const projects=(await api('/projects')).projects;let project=projects.find(p=>p.name==='Harness v2 冒烟 20261007');
if(!project)project=await api('/projects',{name:'Harness v2 冒烟 20261007'});
const chat=await api(`/projects/${project.id}/conversations`,{}),prompt=await fs.readFile(promptFile,'utf8');
const started=await api(`/conversations/${chat.id}/messages`,{content:prompt});
await fs.writeFile(output,JSON.stringify({label,projectId:project.id,conversationId:chat.id,...started,prompt,status:'running'},null,2));
console.log(JSON.stringify({label,conversationId:chat.id,...started}));
let run;
do{await delay(2000);run=await api('/runs/'+started.runId);}while(['queued','running'].includes(run.status));
const conversation=await api('/conversations/'+chat.id);
await fs.writeFile(output,JSON.stringify({label,projectId:project.id,conversationId:chat.id,...started,prompt,status:run.status,run,conversation},null,2));
await fs.copyFile(path.join('data/active/audit',started.runId+'.jsonl'),path.join(dir,label+'-audit.jsonl'));
console.log(JSON.stringify({label,status:run.status,usage:run.usage,answer:conversation.messages.findLast(m=>m.role==='assistant')?.content}));
if(run.status!=='completed')process.exitCode=1;

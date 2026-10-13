// Continue authorized incomplete preparation only while the product records real progress.
// No model changes, product changes, DB access, or service/process management.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const dir=path.join(root,'data/evaluation/blind-eval-ingestion-20261007');
const key=process.argv[2],instruction=process.argv[3];
if(!key||!instruction)throw Error('finish-ingestion KEY continuation-text-file');
const invoke=(...args)=>execFileSync(process.execPath,[path.join(root,'benchmark/blind-eval/ingest.mjs'),...args],{cwd:root,encoding:'utf8',stdio:'pipe',windowsHide:true});
const read=()=>JSON.parse(fs.readFileSync(path.join(dir,'preparation.json'),'utf8')).jobs.find(j=>j.key===key);
function progress(job){
 const events=job.attempts.flatMap(a=>{
  const file=path.join(dir,'audit',a.runId+'.jsonl');
  return fs.existsSync(file)?fs.readFileSync(file,'utf8').split('\n').filter(Boolean).map(JSON.parse):[];
 });
 const counts=events.filter(e=>e.type==='tool_result').map(e=>e.data.result?.data).filter(d=>d?.coverage);
 const last=counts.at(-1)?.coverage;
 return {tables:last?.tables_completed??null,pages:last?.pages_reviewed??null,facts:job.document?.factCount??null,records:job.document?.researchRecordCount??null};
}
invoke('poll');let job=read();if(!job)throw Error('Unknown preparation');
let before=progress(job);
if(job.status==='completed'&&!job.preparationComplete){console.log(invoke('continue',key,instruction).trim());}
while(true){
 invoke('poll');job=read();const after=progress(job);
 console.log(JSON.stringify({at:new Date().toISOString(),key,runStatus:job.status,preparationComplete:job.preparationComplete,...after}));
 if(job.preparationComplete)break;
 if(['running','queued'].includes(job.status)){await new Promise(r=>setTimeout(r,30000));continue;}
 if(job.status!=='completed')throw Error('Recorded attempt failed or POST is uncertain; inspect preserved state before any continuation');
 if(!Object.keys(after).some(k=>after[k]!=null&&before[k]!=null&&after[k]>before[k]))throw Error('Preparation stopped without recorded progress; inspect the concrete error instead of automatically buying another attempt');
 before=after;console.log(invoke('continue',key,instruction).trim());
}

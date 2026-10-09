// Stop dispatch and standard active runs on observed authentication/quota errors.
// This watcher never starts a model request, changes product configuration, or retries a turn.
import fs from 'node:fs/promises';
import path from 'node:path';
import {accountError,terminal} from './study-v3-formal.mjs';
const root=process.cwd(),dir=path.join(root,'data/evaluation/blind-eval-F21-formal-private-20261009');
const checked=new Map();
for(;;){
 const s=JSON.parse(await fs.readFile(path.join(dir,'experiment.json'),'utf8'));
 for(const r of s.runs.filter(r=>r.runId)){
  if(checked.get(r.runId)==='terminal')continue;
  const audit=await fs.readFile(path.join(root,'data/active/audit',r.runId+'.jsonl'),'utf8');
  const lines=audit.split('\n');if(!audit.endsWith('\n'))lines.pop();
  const events=lines.filter(Boolean).map(JSON.parse);
  const evidence=events.find(e=>(e.type==='provider_response'&&[401,403,429].includes(e.data.status))||(['model_usage','model_error','provider_error'].includes(e.type)&&accountError(e.data.error||e.data.errorMessage)));
  if(evidence){
   const note={at:new Date().toISOString(),reason:'authentication_or_quota',label:r.label,runId:r.runId,evidence};
   await fs.writeFile(path.join(dir,'DRAIN.json'),JSON.stringify(note,null,2)+'\n');
   const cancellations=[];
   for(const active of s.runs.filter(x=>x.runId&&!terminal.has(x.status))){
    const response=await fetch('http://127.0.0.1:3001/api/runs/'+active.runId+'/cancel',{method:'POST',signal:AbortSignal.timeout(20000)});
    cancellations.push({label:active.label,runId:active.runId,status:response.status,body:await response.text()});
   }
   await fs.writeFile(path.join(dir,'account-watch-stop.json'),JSON.stringify({...note,cancellations},null,2)+'\n');
   console.log(JSON.stringify({stopped:true,reason:note.reason,label:r.label}));break;
  }
  checked.set(r.runId,terminal.has(r.status)?'terminal':events.length);
 }
 try{await fs.access(path.join(dir,'account-watch-stop.json'));break;}catch(e){if(e.code!=='ENOENT')throw e;}
 if(s.runs.every(r=>terminal.has(r.status)))break;
 await new Promise(resolve=>setTimeout(resolve,10000));
}

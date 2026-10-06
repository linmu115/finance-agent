// Serial task orchestration only; each agent loop is owned by the running app/Pi.
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const cli=path.join(root,'scripts/run-pi-analysis-comparison.mjs');
const file=path.join(root,'data/evaluation',process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261005-r2','experiment.json');
const state=()=>readFile(file,'utf8').then(JSON.parse);
const call=(...args)=>execFileSync(process.execPath,[cli,...args],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});
const order=(await state()).plannedOrder;
for(const label of order){
 let s=await state(),r=s.runs.find(r=>r.label===label);
 if(!r){console.log(call('start',label));}
 while(true){
  const report=JSON.parse(call('poll','--active'));s=await state();r=s.runs.find(r=>r.label===label);
  if(r.status==='posting')throw Error('Uncertain message POST; inspect before continuing');
  if(!['queued','running'].includes(r.status)){console.log(JSON.stringify({event:'terminal',label,status:r.status,usage:r.usage,error:r.error}));if(r.error&&/402|余额不足/.test(r.error))throw Error('Provider balance exhausted; preserve this model cohort before changing providers');break;}
  const p=report.find(x=>x.label===label);console.log(JSON.stringify({event:'progress',label,status:r.status,stage:p?.stage,calls:p?.usage?.calls,output:p?.usage?.output,lastTools:p?.tools?.map(t=>({name:t.name,status:t.status}))}));
  await new Promise(resolve=>setTimeout(resolve,15000));
 }
}
console.log(call('poll'));console.log(call('verify-data'));console.log(call('freeze-after'));

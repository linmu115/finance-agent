// Read-only HTTP snapshot for comparing a later semantic correction. No model calls.
import fs from 'node:fs/promises';
import path from 'node:path';
import {digest} from './validation_utils.mjs';
const args=process.argv.slice(2),arg=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const base=arg('--base-url','http://127.0.0.1:3001').replace(/\/$/,''),project=arg('--project',null);
if(!project)throw Error('Provide --project PROJECT_ID');
const request=async route=>{const response=await fetch(base+route,{signal:AbortSignal.timeout(90000)});if(!response.ok)throw Error('HTTP '+response.status);return response.json();};
const catalog=await request('/api/projects/'+encodeURIComponent(project)+'/catalog');
const terminal=new Set(['ready','completed','needs_review','failed','cancelled']);
const active=(catalog.processing||[]).filter(p=>!terminal.has(p.state));
if(active.length)throw Error('A document-processing run is active; wait for a stable snapshot.');
const facts=[];
for(let offset=0;;){
 const page=await request('/api/projects/'+encodeURIComponent(project)+'/financial-data?limit=200&offset='+offset);
 facts.push(...page.items);offset+=page.items.length;
 if(offset===page.total)break;
 if(offset>page.total||!page.items.length)throw Error('Financial-data pagination did not cover the reported total.');
}
const snapshot={project_id:project,captured_at:new Date().toISOString(),source:'public_http_read_only',model_calls:0,fact_count:facts.length,facts_sha256:digest(facts),catalog,facts};
const output=path.resolve(arg('--output','benchmark/results/financial-snapshot-'+project+'-'+Date.now()+'.json'));
await fs.mkdir(path.dirname(output),{recursive:true});
await fs.writeFile(output,JSON.stringify(snapshot,null,2),{flag:'wx'});
console.log(JSON.stringify({output,project_id:project,facts:facts.length,facts_sha256:snapshot.facts_sha256}));

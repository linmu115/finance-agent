/** Shared host HTTP/audit helpers for research development runners. No service lifecycle. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';

export const researchHash=value=>createHash('sha256').update(typeof value==='string'?value:JSON.stringify(value)).digest('hex');
export function researchWorkflowIO(root,base='http://127.0.0.1:3001'){
 async function api(route,body){
  const response=await fetch(base+route,{method:body===undefined?'GET':'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(90000)});
  const data=await response.json();if(!response.ok)throw Error(`HTTP ${response.status} ${route}: ${data.error?.message||JSON.stringify(data.error||data)}`);return data;
 }
 async function implementationHashes(){
  const result={};async function walk(directory){for(const item of await fs.readdir(path.join(root,directory),{withFileTypes:true})){const rel=path.join(directory,item.name);if(item.isDirectory()){if(!['__pycache__','tests','staged_temporal','staged-v033'].includes(item.name))await walk(rel);}else if(/\.(py|ts|tsx|json|css)$/.test(item.name))result[rel.replaceAll('\\','/')]=researchHash(await fs.readFile(path.join(root,rel),'utf8'));}}
  for(const folder of ['server','service','web/src'])await walk(folder);return result;
 }
 async function audit(runId){
  const events=(await fs.readFile(path.join(root,'data/audit',runId+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
  return events.filter(event=>['tool_request','tool_result','tool_error','model_usage','evaluation_budget','run_config'].includes(event.type));
 }
 async function artifacts(projectId){
  const list=(await api('/api/projects/'+projectId+'/research/artifacts')).artifacts;
  return Promise.all(list.map(item=>api('/api/projects/'+projectId+'/research/artifacts/'+item.id)));
 }
 return {api,implementationHashes,audit,artifacts};
}

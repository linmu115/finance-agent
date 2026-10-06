// Evaluator-side copies only. No generated code is executed on the host.
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'data/evaluation/pi-pilot-20261005');
const s=JSON.parse(await readFile(path.join(dir,'experiment.json'),'utf8'));
for(const r of s.runs.filter(r=>['completed','failed','cancelled'].includes(r.status))){
 const chat=JSON.parse(await readFile(path.join(dir,r.profile+'-conversation.json'),'utf8'));
 const messages=chat.messages.filter(m=>m.role==='assistant'&&m.runId===r.runId);
 await writeFile(path.join(dir,r.label+'-answer.md'),messages.map(m=>m.content).join('\n\n'));
 const folder=path.join(dir,r.label+'-artifacts');await mkdir(folder,{recursive:true});
 const manifest=[];
 for(const a of messages.flatMap(m=>m.artifacts||[])){
  if(path.basename(a.name)!==a.name||!a.url.startsWith('/api/projects/'+r.projectId+'/'))throw Error('Unexpected artifact location');
  const response=await fetch('http://127.0.0.1:3001'+a.url,{signal:AbortSignal.timeout(15000)});
  const item={...a,httpStatus:response.status,contentType:response.headers.get('content-type')};
  if(response.ok){const bytes=Buffer.from(await response.arrayBuffer());
   item.localFile=createHash('sha256').update(a.url).digest('hex').slice(0,12)+'-'+a.name;
   await writeFile(path.join(folder,item.localFile),bytes);
   if(messages.flatMap(m=>m.artifacts||[]).filter(x=>x.name===a.name).length===1)await writeFile(path.join(folder,a.name),bytes);
   item.bytes=bytes.length;item.sha256=createHash('sha256').update(bytes).digest('hex');}
  else item.error=(await response.text()).slice(0,500);
  manifest.push(item);
 }
 // Copy actual analysis inputs/scripts only when a returned, project-owned
 // analysis ID has a matching host state. These are evaluator evidence, not
 // counted as extra files delivered by the model.
 const audit=(await readFile(path.join(dir,r.label+'-audit.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 const runIds=new Set(audit.filter(e=>e.type==='tool_result'&&e.data.name==='run_analysis').map(e=>e.data.result?.data?.run_id).filter(Boolean));
 const scripts=[];
 for(const id of runIds){
  if(!/^[a-f0-9]{32}$/.test(id))continue;
  const input=path.join(root,'data/active/analysis',id);
  const state=JSON.parse(await readFile(path.join(input,'state.json'),'utf8').catch(e=>{if(e.code==='ENOENT')return '{}';throw e;}));
  if(state.project_id!==r.projectId)continue;
  const name=id+'-executed-evaluator-copy.py';
  const bytes=await readFile(path.join(input,'input/__analysis__.py'));
  const prior=await readFile(path.join(folder,name)).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
  if(prior&&!prior.equals(bytes))throw Error('Recorded analysis script changed');
  if(!prior)await writeFile(path.join(folder,name),bytes);
  scripts.push({runId:id,file:name,status:state.status,containerRemoved:state.container_removed,codeSha256:state.code_sha256});
 }
 await writeFile(path.join(dir,r.label+'-deliverables.json'),JSON.stringify({label:r.label,artifacts:manifest,evaluatorScripts:scripts},null,2)+'\n');
 console.log(JSON.stringify({label:r.label,replyCharacters:messages.reduce((n,m)=>n+m.content.length,0),artifacts:manifest.length,downloadsOk:manifest.filter(a=>a.httpStatus===200).length,executedScripts:scripts.length}));
}

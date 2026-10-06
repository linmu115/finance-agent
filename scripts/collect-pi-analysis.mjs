// Evaluator-side copies only. No generated code is executed on the host.
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'data/evaluation',process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261005-r2');
const s=JSON.parse(await readFile(path.join(dir,'experiment.json'),'utf8'));
for(const r of s.runs.filter(r=>['completed','failed','cancelled'].includes(r.status))){
 const chat=JSON.parse(await readFile(path.join(dir,r.label+'-conversation.json'),'utf8'));
 const messages=chat.messages.filter(m=>m.role==='assistant'&&m.runId===r.runId);
 await writeFile(path.join(dir,r.label+'-answer.md'),messages.map(m=>m.content).join('\n\n'));
 const folder=path.join(dir,r.label+'-artifacts');await mkdir(folder,{recursive:true});
 const manifest=[];
 for(const a of messages.flatMap(m=>m.artifacts||[])){
  if(!a.url.startsWith('/api/projects/'+r.projectId+'/'))throw Error('Unexpected artifact project');
  const response=await fetch('http://127.0.0.1:3001'+a.url,{signal:AbortSignal.timeout(15000)});
  const item={...a,httpStatus:response.status,contentType:response.headers.get('content-type')};
  if(response.ok){const bytes=Buffer.from(await response.arrayBuffer());
   // The application supports subdirectories in /output. Keep the original
   // artifact name in the manifest and flatten only this evaluator-side copy.
   item.localFile=createHash('sha256').update(a.url).digest('hex').slice(0,12)+'-'+path.basename(a.name.replaceAll('\\','/'));
   await writeFile(path.join(folder,item.localFile),bytes);
   if(path.basename(a.name)===a.name&&messages.flatMap(m=>m.artifacts||[]).filter(x=>x.name===a.name).length===1)await writeFile(path.join(folder,a.name),bytes);
   item.bytes=bytes.length;item.sha256=createHash('sha256').update(bytes).digest('hex');}
  else {
   item.error=(await response.text()).slice(0,500);
   // A failed download remains a failed delivery. Inspect a verified local
   // output separately so financial scoring is not replaced by an HTTP error.
   const runId=a.url.split('/').at(-2);
   if(/^[a-f0-9]{32}$/.test(runId||'')){
    const output=path.join(root,'data/active/analysis',runId,'output');
    const candidate=path.resolve(output,a.name);
    if(!candidate.startsWith(output+path.sep))throw Error('Evaluator artifact path escapes run');
    const state=JSON.parse(await readFile(path.join(output,'../state.json'),'utf8'));
    const recorded=state.artifacts?.find(x=>x.name===a.name);
    if(state.project_id!==r.projectId||!recorded)throw Error('Artifact not in run manifest');
    const bytes=await readFile(candidate),hash=createHash('sha256').update(bytes).digest('hex');
    if(hash!==recorded.sha256)throw Error('Evaluator artifact hash mismatch');
    item.evaluatorLocalFile=createHash('sha256').update(a.url).digest('hex').slice(0,12)+'-'+path.basename(a.name);
    item.sha256=hash;item.bytes=bytes.length;
    await writeFile(path.join(folder,item.evaluatorLocalFile),bytes);
   }
  }
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
  const name=id+'-analysis-evaluator-copy.py';
  const bytes=await readFile(path.join(input,'input/analysis.py'));
  const prior=await readFile(path.join(folder,name)).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
  if(prior&&!prior.equals(bytes))throw Error('Recorded analysis script changed');
  if(!prior)await writeFile(path.join(folder,name),bytes);
  scripts.push({runId:id,file:name,status:state.status,containerRemoved:state.container_removed,codeSha256:createHash('sha256').update(bytes).digest('hex'),launcherSha256:state.code_sha256});
 }
 await writeFile(path.join(dir,r.label+'-deliverables.json'),JSON.stringify({label:r.label,artifacts:manifest,evaluatorScripts:scripts},null,2)+'\n');
 console.log(JSON.stringify({label:r.label,replyCharacters:messages.reduce((n,m)=>n+m.content.length,0),artifacts:manifest.length,downloadsOk:manifest.filter(a=>a.httpStatus===200).length,executedScripts:scripts.length}));
}

// User-requested F203 first-turn transport inspection; no model calls or product mutations.
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const name=process.argv[2];
if(!['blind-eval-F203-gate-20261009','blind-eval-F21-gate-20261009'].includes(name))throw Error('Expected authorized gate batch');
const dir=path.resolve('data/evaluation',name),file=path.join(dir,'experiment.json');
const s=JSON.parse(await fs.readFile(file,'utf8'));
if(s.invalidated||!['F2.0.3','F2.1'].includes(s.freeze.version)||s.runs.filter(r=>r.runId).length!==1||s.runs[0].status!=='completed')throw Error('First successful terminal turn alone required');
const health=async()=>{const r=await fetch('http://127.0.0.1:3001/api/health');const h=await r.json();if(!r.ok||h.service!=='connected'||!h.ok)throw Error('Document service disconnected');return h;};
const before=await health();
execFileSync(process.execPath,['benchmark/blind-eval/runner-v3-gate.mjs','verify',name],{windowsHide:true});
const code=await fs.readFile('server/dist/main.js','utf8');
const route=code.slice(code.indexOf("app.get('/api/projects/:projectId/artifacts/:runId/:name'"));
if(!route||!route.slice(0,1800).includes("service.call('get_artifact_metadata'"))throw Error('Compiled artifact route not metadata-only');
const deliveryCode=await fs.readFile('server/dist/research-artifacts.js','utf8');
const delivery=deliveryCode.slice(deliveryCode.indexOf('export async function deliveryFile('));
if(!delivery||!delivery.slice(0,1000).includes("service.call('get_artifact_metadata'"))throw Error('Compiled research delivery route not metadata-only');
const collection=execFileSync(process.execPath,['benchmark/blind-eval/runner-v3-gate.mjs','collect',name],{windowsHide:true,encoding:'utf8',maxBuffer:20*1024*1024});
const manifest=JSON.parse(await fs.readFile(path.join(dir,s.runs[0].label+'-deliverables.json'),'utf8'));
const charts=manifest.artifacts.filter(a=>a.mimeType?.startsWith('image/')||/\.(png|svg|jpe?g)$/i.test(a.name));
if(!charts.length||charts.some(a=>a.httpStatus!==200||!a.localFile))throw Error('First chart download unavailable');
const after=await health();
const receipt={passed:true,at:new Date().toISOString(),runId:s.runs[0].runId,method:'Actual first-turn HTTP chart downloads, frozen compiled route calls get_artifact_metadata, service connected before/after; protocol bytes not independently intercepted.',
 before,after,charts:charts.map(a=>({name:a.name,url:a.url,httpStatus:a.httpStatus,bytes:a.bytes,sha256:a.sha256})),collection,
 compiledMetadataRouteSha256:createHash('sha256').update(code).digest('hex'),compiledDeliveryRouteSha256:createHash('sha256').update(deliveryCode).digest('hex')};
await fs.writeFile(path.join(dir,'first-turn-inspection.json'),JSON.stringify(receipt,null,2)+'\n');
s.firstTurnInspection=receipt;await fs.writeFile(file+'.tmp',JSON.stringify(s,null,2)+'\n');await fs.rename(file+'.tmp',file);
console.log(JSON.stringify({passed:true,charts:charts.length,service:after.service,remaining:17}));

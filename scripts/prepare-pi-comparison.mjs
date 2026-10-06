// Read-only preparation. No project mutation, model request or sandbox startup.
import {createHash} from 'node:crypto';
import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const sha=data=>createHash('sha256').update(data).digest('hex');
const get=async route=>{
 const res=await fetch('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(10000)});
 if(!res.ok)throw new Error(`${route}: HTTP ${res.status}`);
 return res.json();
};
const [settings,health]=await Promise.all([get('/api/settings'),get('/api/health')]);
const files={};
async function walk(dir){
 for(const entry of (await readdir(path.join(root,dir),{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
  if(['dist','__pycache__','tests','node_modules'].includes(entry.name))continue;
  const name=dir+'/'+entry.name;
  if(entry.isDirectory())await walk(name);
  else if(entry.isFile()&&/\.(py|ts|tsx|md|json|css)$/.test(entry.name))files[name]=sha(await readFile(path.join(root,name)));
 }
}
for(const dir of ['server','service','skills','web/src'])await walk(dir);
for(const name of ['package.json','package-lock.json','requirements.lock.txt','sandbox/Dockerfile','sandbox/requirements.lock','sandbox/wheels.lock.json','design/pi-finance-analysis-protocol-20261005.md'])files[name]=sha(await readFile(path.join(root,name)));
const sources=[
 {file:'samples/native-pdf/Ruihe_Data_2025_Interim_57p.pdf',pages:57,sha256:'a40de54658363105b774ac0fba8f9252d85e0106ca9496c22325ebf668031702'},
 {file:'samples/native-pdf/Guosen_Yili_20250716_38p.pdf',pages:38,sha256:'6242c4d8fd51ede40de29391f3b41703f2e9880e62da32b4a2b760ce3cfbfd88'},
];
for(const item of sources){
 const actual=sha(await readFile(path.join(root,item.file)));
 if(actual!==item.sha256)throw new Error('Source hash changed: '+item.file);
}
const llm=Object.fromEntries(['provider','model','contextWindow','maxTokens','inputPricePerMillionUsd','cacheReadPricePerMillionUsd','outputPricePerMillionUsd'].filter(k=>settings.llm?.[k]!==undefined).map(k=>[k,settings.llm[k]]));
// Keep a provider fingerprint without exposing endpoints or credentials.
llm.endpointSha256=sha(settings.llm?.baseUrl||'');
const manifest={status:'prepared_not_run',createdAt:new Date().toISOString(),service:health,
 costProtocol:'ingestion_separate_analysis_only',study:'development_pilot_not_heldout',profiles:['generic','prepared','financial'],sources,
 model:llm,contextCompaction:settings.runtime?.contextCompaction,files,
 codeSha256:sha(JSON.stringify(files)),protocol:'design/pi-finance-analysis-protocol-20261005.md',
 requires:['user_authorized_pilot','equal_available_isolated_python','frozen_task_and_gold','separate_fresh_conversations_frozen_data_versions','record_actual_routing'],
 results:null};
const output=path.join(root,'data','evaluation','pi-prepare-'+manifest.createdAt.replace(/[:.]/g,'-'));
await mkdir(output,{recursive:true});
await writeFile(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
const scorecard={status:'not_scored',arms:['generic','prepared','financial'].map(profile=>({
 profile,projectId:null,conversationIds:[],runs:[],
 tasks:[1,2,3].map(task=>({task,completed:null,correct:null,total:null,financialReview:null,evidenceReview:null,reproducible:null,chartReview:null,interventions:[]})),usage:null,
}))};
await writeFile(path.join(output,'scorecard.json'),JSON.stringify(scorecard,null,2)+'\n');
console.log(JSON.stringify({output,status:manifest.status,model:llm.model,sources:sources.length,sourceHashesVerified:true,codeSha256:manifest.codeSha256,modelCalls:0},null,2));

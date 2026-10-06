// User-approved preparation model; analysis must switch back to Luna.
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {getAgentDir,ModelRuntime} from '@earendil-works/pi-coding-agent';
import {loadSettings} from '../server/config.js';
const id=process.argv[2];
if(!['gpt-6.1-sol','gpt-6-luna'].includes(id))throw Error('Expected an approved CPA model');
const settings=await loadSettings();
if(settings.llm.provider!=='cpa-local'||new URL(settings.llm.baseUrl).hostname!=='127.0.0.1')throw Error('Expected current local CPA settings');
const file=path.join(getAgentDir(),'models.json');
const catalog=JSON.parse(await readFile(file,'utf8'));
const provider=catalog.providers['cpa-local'];
if(!provider.models.some((m:any)=>m.id===id)){
 const runtime=await ModelRuntime.create({allowModelNetwork:false});const m=runtime.getModel('openai',id)!;
 provider.models.push({id,name:id+' · 本机 CPA',reasoning:m.reasoning,input:m.input,contextWindow:m.contextWindow,maxTokens:m.maxTokens,cost:m.cost});
 await writeFile(file,JSON.stringify(catalog,null,2)+'\n');
}
const r=await fetch('http://127.0.0.1:3001/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({llm:{...settings.llm,model:id}})});
if(!r.ok)throw Error('Settings rejected: '+r.status);
const body:any=await r.json();const llm=body.settings?.llm||body.llm;
if(llm.model!==id)throw Error('Readback mismatch');
console.log(JSON.stringify({provider:llm.provider,model:llm.model,baseUrl:llm.baseUrl,hasKey:llm.hasKey}));

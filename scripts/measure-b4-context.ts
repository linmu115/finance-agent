// No inference request: instantiate native Pi sessions against an isolated empty project.
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const root=path.resolve('tmp/b4-context-20261007');process.env.FINANCE_DATA_DIR=root;
const {loadSettings,saveSettings,getSettings}=await import('../server/config.js');
const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'context-measurement-no-inference',apiKey:'not-a-credential',contextWindow:128000,maxTokens:4096}});
const service=new FinanceService();await service.connect();const manager=new RunManager(service);
const snapshots:any={method:'Native sessionFor/createAgentSession, no prompt() and no network model request; empty isolated default project.',profiles:{}};
try{
 await service.call('create_project',{project_id:'b4_measurement',name:'B4 context measurement'});
 for(const profile of ['prepared','financial']){
  const chat:any={id:randomUUID(),projectId:'b4_measurement',messages:[],evaluationProfile:profile};
  const live:any={chat,run:{id:randomUUID(),projectId:chat.projectId,tools:[]},controller:new AbortController(),modelPending:new Set()};
  const entry=await (manager as any).sessionFor(live,getSettings());
  snapshots.profiles[profile]={system:entry.session.systemPrompt,tools:entry.session.agent.state.tools.map((t:any)=>({name:t.name,description:t.description,parameters:t.parameters}))};
 }
 await fs.mkdir('docs/evidence/b4-plan-20261007',{recursive:true});
 await fs.writeFile('docs/evidence/b4-plan-20261007/current-context.json',JSON.stringify(snapshots,null,2));
 console.log(JSON.stringify(Object.fromEntries(Object.entries(snapshots.profiles).map(([k,v]:any)=>[k,{systemChars:[...v.system].length,tools:v.tools.length}]))));
}finally{await manager.shutdown();await service.close();}

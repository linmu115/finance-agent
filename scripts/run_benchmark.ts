import {fork,spawn} from 'node:child_process';
import {mkdir,readFile,writeFile,readdir} from 'node:fs/promises';
import {createWriteStream} from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {ROOT,PYTHON,loadSettings,publicSettings,requireModel} from '../server/config.js';
import {PROMPT_HASH} from '../server/runs.js';
const args=process.argv.slice(2),option=(name:string,fallback:string)=>{const i=args.indexOf('--'+name);return i<0?fallback:args[i+1];};
if(args.includes('--help')){
 console.log('npm run benchmark -- --version 0.1|0.2 --split dev|acceptance|all --runs 1 --concurrency 3 --limit 0 [--case CASE_ID] [--resume RUN_DIRECTORY]\nFresh database, session and allowlisted materials for every case. No gold answers passed to Pi.');
 process.exit(0);
}
const version=option('version','0.1'),split=option('split','dev'),repeat=Number(option('runs','1')),limit=Number(option('limit','0')),caseId=option('case',''),concurrency=Number(option('concurrency','3'));
if(!['0.1','0.2'].includes(version))throw new Error('Unknown benchmark version');
if(!['dev','acceptance','all'].includes(split)||!Number.isInteger(repeat)||repeat<1||repeat>5||!Number.isInteger(limit)||limit<0||!Number.isInteger(concurrency)||concurrency<1||concurrency>4)throw new Error('Invalid benchmark options');
await loadSettings();const settings=requireModel();
const casePath=version==='0.1'?'benchmark/agent_input/cases.jsonl':'benchmark/versions/v0.2/cases.jsonl';
const goldPath=version==='0.1'?'benchmark/evaluator/gold.jsonl':'benchmark/versions/v0.2/gold.jsonl';
const cases=String(await readFile(path.join(ROOT,casePath),'utf8')).trim().split('\n').map(x=>JSON.parse(x));
let selected=cases.filter(c=>(split==='all'||c.split===split)&&(!caseId||c.id===caseId));if(limit)selected=selected.slice(0,limit);
if(!selected.length)throw new Error('No selected cases');
async function codeFingerprint(){
 const files=['package-lock.json','requirements.lock.txt','scripts/run_benchmark.ts','scripts/benchmark_worker.ts','scripts/score_repeatability.py','benchmark/prepare_case.py','benchmark/evaluate.py'];
 for(const directory of ['server','service','sandbox']){
  for(const entry of await readdir(path.join(ROOT,directory),{withFileTypes:true}))if(entry.isFile()&&/\.(ts|py)$/.test(entry.name))files.push(directory+'/'+entry.name);
 }
 const hashes:any={};for(const file of files.sort())hashes[file]=createHash('sha256').update(await readFile(path.join(ROOT,file))).digest('hex');
 return {hash:createHash('sha256').update(JSON.stringify(hashes)).digest('hex'),files:hashes};
}
const code=await codeFingerprint(),frozen=publicSettings();
async function datasetFingerprint(){
 const files=[casePath,goldPath,...new Set<string>(cases.flatMap(c=>c.allowed_assets.map((asset:string)=>'benchmark/agent_input/'+asset)))];
 if(version==='0.2')files.push('benchmark/versions/v0.2/manifest.json');
 const hashes:Record<string,string>={};for(const file of files.sort())hashes[file]=createHash('sha256').update(await readFile(path.join(ROOT,file))).digest('hex');
 return {hash:createHash('sha256').update(JSON.stringify(hashes)).digest('hex'),files:hashes};
}
const dataset=await datasetFingerprint();
const configHash=createHash('sha256').update(JSON.stringify(frozen)+PROMPT_HASH+code.hash+dataset.hash).digest('hex');
const output=path.resolve(option('resume',path.join(ROOT,'benchmark','runs','agent-'+new Date().toISOString().replace(/[:.]/g,'-'))));
await mkdir(output,{recursive:true});await mkdir(path.join(ROOT,'benchmark','results'),{recursive:true});
const manifestFile=path.join(output,'manifest.json');
let manifest:any;
try{
 manifest=JSON.parse(await readFile(manifestFile,'utf8'));
 if(manifest.configHash!==configHash||JSON.stringify(manifest.caseIds)!==JSON.stringify(selected.map(x=>x.id))||manifest.repeat!==repeat)throw new Error('Resume configuration or implementation differs from frozen manifest');
}catch(e:any){
 if(e.code!=='ENOENT')throw e;
 manifest={name:path.basename(output),createdAt:new Date().toISOString(),benchmarkVersion:version,dataset,split,repeat,concurrency,model:settings.llm.model,configHash,promptHash:PROMPT_HASH,code,settings:frozen,caseIds:selected.map(x=>x.id),subset:selected.length!==cases.filter(c=>split==='all'||c.split===split).length,piVersion:'1.0.0',agentInputIsolated:true,status:'running'};
 await writeFile(manifestFile,JSON.stringify(manifest,null,2),'utf8');
}
const command=(program:string,argv:string[],logFile?:string)=>new Promise<{code:number;stdout:string}>((resolve,reject)=>{
 const child=spawn(program,argv,{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});let stdout='';const file=logFile?createWriteStream(logFile,{flags:'a'}):null;
 child.stdout.on('data',b=>{stdout+=b;file?.write(b);});child.stderr.on('data',b=>file?.write(b));
 child.on('error',reject);child.on('close',code=>{file?.end();resolve({code:code??1,stdout});});
});
async function worker(inputDir:string,dataDir:string,logFile:string):Promise<any>{
 return new Promise((resolve,reject)=>{
  const env:NodeJS.ProcessEnv={...process.env,FINANCE_DATA_DIR:dataDir};delete env.FINANCE_LLM_API_KEY;
  const child=fork(path.join(ROOT,'scripts','benchmark_worker.ts'),[],{cwd:ROOT,execArgv:['--import','tsx'],env,stdio:['ignore','pipe','pipe','ipc'],windowsHide:true});
  const log=createWriteStream(logFile,{flags:'a'});child.stdout?.pipe(log,{end:false});child.stderr?.pipe(log,{end:false});
  let result:any,settled=false;
  const watchdog=setTimeout(()=>{
   if(!settled){settled=true;reject(new Error('Benchmark worker exceeded its host timeout'));}
   if(process.platform==='win32')spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
   else child.kill('SIGTERM');
  },22*60000);
  child.on('message',(message:any)=>{if(message.type==='result')result=message.result;if(message.type==='fatal')result={fatal:message.message};});
  child.on('error',error=>{clearTimeout(watchdog);if(!settled){settled=true;reject(error);}});
  child.on('exit',code=>{clearTimeout(watchdog);log.end();if(!settled){settled=true;if(result&&!result.fatal)resolve(result);else reject(new Error(result?.fatal||'Worker exited '+code));}});
  child.send({settings,inputDir});
 });
}
const reports:any[]=[];
for(let round=1;round<=repeat;round++){
 const roundStarted=performance.now(),roundDir=path.join(output,'round-'+round);await mkdir(roundDir,{recursive:true});
 const results:any[]=new Array(selected.length);let cursor=0,completed=0,saveQueue:Promise<void>=Promise.resolve();
 await Promise.all(Array.from({length:Math.min(concurrency,selected.length)},async()=>{
  while(true){
   const index=cursor++;if(index>=selected.length)return;
   if((await codeFingerprint()).hash!==code.hash)throw new Error('Implementation changed during benchmark; stop and start a new frozen run');
   const item=selected[index],base=path.join(roundDir,item.id),resultFile=path.join(base,'result.json');let result:any;
   try{result=JSON.parse(await readFile(resultFile,'utf8'));}
   catch(e:any){
    if(e.code!=='ENOENT')throw e;
    await mkdir(base,{recursive:true});const inputDir=path.join(base,'input');
    try{await readFile(path.join(inputDir,'case.json'));}
    catch{const prepared=await command(PYTHON,[path.join(ROOT,'benchmark','prepare_case.py'),item.id,inputDir,'--version',version],path.join(base,'prepare.log'));if(prepared.code!==0)throw new Error('Could not prepare allowlisted case '+item.id);}
    try{result=await worker(inputDir,path.join(base,'data'),path.join(base,'worker.log'));}
    catch(error){result={id:item.id,prediction:{id:item.id,status:'failed',answer:null,citations:[],error:error instanceof Error?error.message:String(error)}};}
    if(result.run?.id){
     let audit=await readFile(path.join(base,'data','audit',result.run.id+'.jsonl'),'utf8');
     for(const section of [settings.llm,settings.embedding,settings.ocr])if(section.apiKey)audit=audit.split(section.apiKey).join('[REDACTED]');
     const records=audit.trim().split('\n').map(line=>JSON.parse(line,(_key,value)=>/^(?:api[_-]?key|authorization|access[_-]?token|client[_-]?secret)$/i.test(_key)?'[REDACTED]':value));
     audit=records.map(record=>JSON.stringify(record)).join('\n')+'\n';
     await writeFile(path.join(base,'audit.jsonl'),audit,'utf8');
     result.audit={path:'audit.jsonl',sha256:createHash('sha256').update(audit).digest('hex'),records:records.length};
    }
    await writeFile(resultFile,JSON.stringify(result,null,2),'utf8');
   }
   results[index]=result;completed++;
   const snapshot=results.filter(Boolean).map(r=>JSON.stringify(r.prediction)).join('\n')+'\n';
   saveQueue=saveQueue.then(()=>writeFile(path.join(roundDir,'predictions.jsonl'),snapshot,'utf8'));await saveQueue;
   console.log(JSON.stringify({round,completed,total:selected.length,id:item.id,status:result.run?.status||'failed',elapsedMs:result.elapsedMs}));
  }
 }));
 await saveQueue;
 const traces=results.map(result=>({id:result.id,runId:result.run?.id,status:result.run?.status||'failed',elapsedMs:result.elapsedMs,usage:result.run?.usage,toolCalls:result.run?.tools?.filter((t:any)=>t.status==='started').length,configHash:result.run?.configHash}));
 await writeFile(path.join(roundDir,'traces.json'),JSON.stringify(traces,null,2),'utf8');
 const scoreFile=path.join(roundDir,'score.json');
 await command(PYTHON,[path.join(ROOT,'benchmark','evaluate.py'),path.join(roundDir,'predictions.jsonl'),'--split',split,'--version',version,'--output',scoreFile],path.join(roundDir,'scoring.log'));
 const score=JSON.parse(await readFile(scoreFile,'utf8'));
 const report={...score,round,model:settings.llm.model,configHash,promptHash:PROMPT_HASH,codeHash:code.hash,selectedCases:selected.length,subset:manifest.subset,wallTimeMs:Math.round(performance.now()-roundStarted),aggregateCaseTimeMs:traces.reduce((sum,t)=>sum+(t.elapsedMs||0),0),modelCalls:traces.reduce((sum,t)=>sum+(t.usage?.calls||0),0),inputTokens:traces.reduce((sum,t)=>sum+(t.usage?.input||0),0),outputTokens:traces.reduce((sum,t)=>sum+(t.usage?.output||0),0),traces};
 reports.push(report);
 await writeFile(path.join(ROOT,'benchmark','results',manifest.name+'-round-'+round+'.json'),JSON.stringify({...report,name:manifest.name+' round '+round,status:score.dataset_gate_pass?'passed':'failed',mode:'pi_agent_real_model'},null,2),'utf8');
}
let consistent=0;
if(repeat>1){
 const sets=await Promise.all(Array.from({length:repeat},(_,i)=>readFile(path.join(output,'round-'+(i+1),'predictions.jsonl'),'utf8').then(s=>new Map(s.trim().split('\n').map(l=>{const p=JSON.parse(l);return [p.id,JSON.stringify({status:p.status,answer:p.answer,corrected_value:p.corrected_value,unit:p.unit,period:p.period,scope:p.scope,citations:p.citations?.slice().sort()})]})))));
 for(const item of selected)if(sets.every(s=>s.get(item.id)===sets[0].get(item.id)))consistent++;
}
manifest.status='completed';manifest.finishedAt=new Date().toISOString();manifest.repeatConsistency=repeat>1?consistent/selected.length:null;
manifest.exactPredictionConsistency=manifest.repeatConsistency;
if(repeat>1){
 await command(PYTHON,[path.join(ROOT,'scripts','score_repeatability.py'),output],path.join(output,'repeatability.log'));
 const repeated=JSON.parse(await readFile(path.join(output,'repeatability.json'),'utf8'));
 manifest.repeatConsistency=repeated.numericConclusionConsistency;
 manifest.citationSetConsistency=repeated.citationSetConsistency;
}
manifest.codeUnchangedDuringRun=(await codeFingerprint()).hash===code.hash;
manifest.datasetUnchangedDuringRun=(await datasetFingerprint()).hash===dataset.hash;
manifest.datasetGateAllRuns=manifest.codeUnchangedDuringRun&&manifest.datasetUnchangedDuringRun&&reports.every(r=>r.dataset_gate_pass);
manifest.worstGroundedAccuracy=Math.min(...reports.map(r=>r.grounded_accuracy));
await writeFile(manifestFile,JSON.stringify(manifest,null,2),'utf8');
await writeFile(path.join(ROOT,'benchmark','results',manifest.name+'-summary.json'),JSON.stringify({...manifest,runs:reports.map(({cases,traces,...r})=>r)},null,2),'utf8');
console.log(JSON.stringify({output,datasetGateAllRuns:manifest.datasetGateAllRuns,repeatConsistency:manifest.repeatConsistency,codeUnchangedDuringRun:manifest.codeUnchangedDuringRun}));

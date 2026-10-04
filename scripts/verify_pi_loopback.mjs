import {spawn} from 'node:child_process';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {PiModelBridge} from '../server/model-bridge.ts';

const root=path.resolve(import.meta.dirname,'..'),bridge=new PiModelBridge(),controller=new AbortController();
const report={scope:'Private Pi bridge + real LangExtract provider; synthetic response after 125 seconds; no upstream model call',started_at:new Date().toISOString(),status:'running',calls:0};
const destination=path.join(root,'benchmark/results/pi-loopback-direct-v04.json');
await writeFile(destination,JSON.stringify(report,null,2));
const runtime=await bridge.register('long-loopback',controller.signal,async(body,signal)=>{
 report.calls++;report.input_preserved=body.messages.some(m=>m.content?.includes('中文金融证据'));
 await delay(125000,undefined,{signal});
 return {model:'fixture',content:'{"extractions":[]}',input:1,output:1};
});
const program=`import sys,json
from langextract.factory import create_model
from service.pi_provider import pi_model_config
runtime=json.load(sys.stdin)
model=create_model(pi_model_config(runtime,max_workers=1))
try:
 result=list(model.infer(['中文金融证据']))[0][0].output
 print(json.dumps({'output':result,'retries':model._client.max_retries},ensure_ascii=False))
finally: model._client.close()
`;
const started=Date.now();
try{
 const result=await new Promise((resolve,reject)=>{
  const child=spawn(path.join(root,'.venv/Scripts/python.exe'),['-c',program],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
  let out='',err='';const timer=setTimeout(()=>{controller.abort();child.kill();},170000);
  child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);
  child.once('error',reject);child.once('close',code=>{clearTimeout(timer);resolve({code,out,err});});
  child.stdin.end(JSON.stringify({...runtime,model:'fixture'}));
 });
 Object.assign(report,{elapsed_ms:Date.now()-started,exit_code:result.code,result:result.code===0?JSON.parse(result.out):null,error:result.code?result.err.slice(-1200):undefined});
 report.status=result.code===0&&report.calls===1&&report.input_preserved?'passed':'failed';
}catch(error){report.status='failed';report.error=error.message;}
finally{await bridge.close();report.finished_at=new Date().toISOString();await writeFile(destination,JSON.stringify(report,null,2));}
console.log(JSON.stringify(report));if(report.status!=='passed')process.exitCode=1;

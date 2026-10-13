// Offline integration: intercept fetch; no HTTP connection, paid model or service port.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {fileURLToPath,pathToFileURL} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../..');
const name='blind-eval-offline-runner-'+Date.now(),dir=path.join(root,'data/evaluation',name);fs.mkdirSync(dir,{recursive:true});
const config=JSON.parse(fs.readFileSync(path.join(here,'development-config.json'),'utf8'));config.projectId='mock-project';fs.writeFileSync(path.join(dir,'config.json'),JSON.stringify(config));
const hook=path.join(here,'test-transport.mjs');
const call=(command,arg)=>execFileSync(process.execPath,['--import',pathToFileURL(hook).href,path.join(here,'runner.mjs'),command,name,...(arg?[arg]:[])],{cwd:root,env:{...process.env,BLIND_EVAL_MOCK_DIR:dir,NODE_OPTIONS:((process.env.NODE_OPTIONS||'')+' --import='+pathToFileURL(hook).href).trim()},encoding:'utf8',stdio:'pipe',windowsHide:true});
call('plan',path.join(dir,'config.json'));call('freeze');call('start','P1_2');call('poll');call('start','P1_3');call('poll');call('start','F1_2');call('poll');call('start','F1_3');call('poll');call('verify');
const s=JSON.parse(fs.readFileSync(path.join(dir,'experiment.json'),'utf8'));assert.equal(s.runs.length,4);assert.equal(s.runs[0].conversationId,s.runs[1].conversationId);assert.equal(s.runs[2].conversationId,s.runs[3].conversationId);assert.notEqual(s.runs[0].conversationId,s.runs[2].conversationId);assert.ok(s.verification.codeUnchanged&&s.verification.dataUnchanged);
const snapshot=JSON.parse(fs.readFileSync(path.join(dir,'structured-data-before.json'),'utf8'));assert.equal(snapshot.financial.length,2);assert.equal(snapshot.research.length,2);
assert.ok(s.verification.tasksUnchanged&&s.verification.settingsUnchanged&&Object.values(s.verification.referencesUnchanged).every(Boolean));
const calls=fs.readFileSync(path.join(dir,'mock-requests.jsonl'),'utf8').trim().split('\n').map(JSON.parse);const messages=calls.filter(x=>x.route.endsWith('/messages'));assert.equal(messages.length,4);assert.equal(messages[0].body.content,config.tasks[1].prompt);assert.equal(messages[1].body.content,config.tasks[2].prompt);assert.equal(messages[0].body.content,messages[2].body.content);assert.deepEqual(messages.map(m=>m.body.evaluation.profile),['prepared','prepared','financial','financial']);
let duplicateRejected=false;try{call('start','P1_2');}catch{duplicateRejected=true;}assert.ok(duplicateRejected);
fs.writeFileSync(path.join(dir,'verification.json'),JSON.stringify({mode:'mock_transport_no_network',passed:true,checks:['pagination complete','same conversation continuation','exact frozen prompts','prepared profile','frozen code/data unchanged','duplicate POST prevented'],realRequests:0,paidRequests:0},null,2));console.log(JSON.stringify({output:dir,passed:true,realRequests:0}));

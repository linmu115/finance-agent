// Private API subprocess: no network, model, MCP or real workspace writes.
import fs from 'node:fs/promises';
import path from 'node:path';
const args=process.argv.slice(2),arg=n=>args[args.indexOf(n)+1],output=arg('--output'),job=arg('--job-id');
const folder=path.dirname(output),kind=process.env.FIXTURE_MODE||'hold';
if(!path.basename(path.resolve(folder,'../..')).startsWith('finance-benchmark-api-'))throw Error('Temporary root required');
await fs.writeFile(path.join(folder,'runner-started'),String(process.pid),{flag:'wx'});
const lock=path.join(folder,'holdout-v05-financial-first-run.lock.json');
await fs.writeFile(lock,JSON.stringify({job_id:job,runner_pid:process.pid,output,started_at:new Date().toISOString()}),{flag:'wx'});
if(kind==='empty')process.exit(0);
if(kind==='failed'){await fs.writeFile(output,JSON.stringify({status:'failed',error:'Deliberate private fixture failure'}));process.exit(0);}
await fs.writeFile(output,JSON.stringify({status:'running'}));
setInterval(()=>{},1000);

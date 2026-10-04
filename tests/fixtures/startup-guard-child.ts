import {appendFile} from 'node:fs/promises';
import {acquireStartupGuard} from '../../server/startup-guard.js';

try{
 const guard=await acquireStartupGuard({dataDir:process.env.FIXTURE_DATA!,host:'127.0.0.1',port:Number(process.env.FIXTURE_PORT||0)});
 if(process.env.FIXTURE_MARKER)await appendFile(process.env.FIXTURE_MARKER,JSON.stringify({pid:process.pid,port:guard.port})+'\n');
 guard.activate((_req,res)=>res.end('fixture-owned'));
 process.send?.({status:'acquired',port:guard.port,pid:process.pid});
 process.on('message',async message=>{if(message==='close'){await guard.close();process.exit(0);}});
}catch(error:any){process.send?.({status:'rejected',code:error.code,message:error.message});process.exitCode=3;process.disconnect?.();}

// This module imports only Node built-ins. Acquire before loading settings,
// opening the MCP child/Store, or recovering any persisted runs.
import {createServer as createHttpServer,type RequestListener,type Server as HttpServer} from 'node:http';
import {createServer as createIpcServer,type Server as IpcServer,type ListenOptions,type AddressInfo} from 'node:net';
import {mkdir,realpath} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';

export class StartupConflict extends Error {
 constructor(readonly code:'STARTUP_PORT_IN_USE'|'STARTUP_DATA_IN_USE'|'STARTUP_PLATFORM_UNSUPPORTED',message:string,options?:ErrorOptions){super(message,options);this.name='StartupConflict';}
}

function listen(server:IpcServer,options:ListenOptions):Promise<void>{
 return new Promise((resolve,reject)=>{
  const failed=(error:Error)=>{server.off('listening',ready);reject(error);};
  const ready=()=>{server.off('error',failed);resolve();};
  server.once('error',failed);server.once('listening',ready);server.listen(options);
 });
}
async function close(server:IpcServer){
 // closeAllConnections is HTTP-only and closes old keepalive/startup requests.
 const http=server as HttpServer;
 await new Promise<void>(resolve=>{server.close(()=>resolve());http.closeAllConnections?.();});
}

export interface StartupGuard {
 readonly server:HttpServer;
 readonly canonicalData:string;
 readonly port:number;
 /** Swap the initial 503 responder onto the same continuously held listener. */
 activate(handler:RequestListener):void;
 /** Stop new HTTP requests while retaining DATA ownership during shutdown. */
 stopAccepting():void;
 /** Call only after runs and the MCP child have stopped writing. */
 close():Promise<void>;
}

export async function acquireStartupGuard({dataDir,host,port}:{dataDir:string;host:string;port:number}):Promise<StartupGuard>{
 if(!Number.isInteger(port)||port<0||port>65535)throw new Error('本地服务端口必须是 0 到 65535 的整数');
 if(!['127.0.0.1','::1','localhost'].includes(host))throw new Error('启动守卫仅允许本机回环地址');
 const starting:RequestListener=(_req,res)=>{
  res.writeHead(503,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Connection':'close'});
  res.end(JSON.stringify({ok:false,service:'starting',error:{code:'STARTING',message:'应用正在启动，请稍后重试'}}));
 };
 const server=createHttpServer(starting);
 // Claim the public port first. A conflicting launch must not even create DATA.
 try{await listen(server,{host,port,exclusive:true});}
 catch(error:any){await close(server);if(error.code==='EADDRINUSE')throw new StartupConflict('STARTUP_PORT_IN_USE','本地服务端口已被占用；本次启动未连接数据服务或恢复任务。',{cause:error});throw error;}
 let dataLock:IpcServer|undefined;
 try{
  if(!['win32','linux'].includes(process.platform))throw new StartupConflict('STARTUP_PLATFORM_UNSUPPORTED','此启动守卫目前支持 Windows 和 Linux；当前平台不能在未取得安全目录独占权时启动。');
  // mkdir is the sole pre-ownership filesystem mutation. It never opens the DB
  // or settings; realpath coalesces symlinks/junctions before deriving the key.
  await mkdir(path.resolve(dataDir),{recursive:true,mode:0o700});
  const canonicalData=await realpath(path.resolve(dataDir));
  const identity=process.platform==='win32'?canonicalData.toLowerCase():canonicalData;
  const key=createHash('sha256').update(identity).digest('hex');
  const address=process.platform==='win32'?'\\\\.\\pipe\\finance-workspace-'+key:'\0finance-workspace-'+key;
  dataLock=createIpcServer(socket=>socket.destroy());
  // Windows named pipes / Linux abstract sockets belong to this process's OS
  // handle. Crash releases ownership; no stale PID file, unlink, or lease race.
  try{await listen(dataLock,{path:address,exclusive:true});}
  catch(error:any){if(['EADDRINUSE','EACCES'].includes(error.code))throw new StartupConflict('STARTUP_DATA_IN_USE','此数据目录已由另一个金融研究进程使用；换端口也不能重复启动。',{cause:error});throw error;}
  let activated=false,closed=false,closing:Promise<void>|undefined;
  return {
   server,canonicalData,port:(server.address() as AddressInfo).port,
   activate(handler){if(closed||activated)throw new Error('启动 listener 已关闭或已经交给应用');server.off('request',starting);server.on('request',handler);activated=true;},
   stopAccepting(){server.close();},
   close(){return closing??=(async()=>{closed=true;await close(server);await close(dataLock!);})();},
  };
 }catch(error){if(dataLock)await close(dataLock);await close(server);throw error;}
}

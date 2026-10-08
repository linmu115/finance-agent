import {mkdir,readFile,writeFile,realpath} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import type {Transport} from '@modelcontextprotocol/sdk/shared/transport.js';
import {JSONRPCMessageSchema,type JSONRPCMessage} from '@modelcontextprotocol/sdk/types.js';

export const MCP_INLINE_BYTES=2*1024*1024;
const marker='_finance_payload';

/** Shared local files carry full payloads; stdio still uses ordinary bounded JSON-RPC. */
export class PayloadTransport implements Transport {
 onclose?:Transport['onclose'];onerror?:Transport['onerror'];onmessage?:Transport['onmessage'];
 private folder:string;
 constructor(readonly inner:Transport,root:string){
  this.folder=path.join(root,'.mcp-payloads');
  inner.onclose=()=>this.onclose?.();inner.onerror=e=>this.onerror?.(e);
  inner.onmessage=(message,extra)=>{void this.receive(message).then(full=>this.onmessage?.(full,extra)).catch(error=>{
   // A bad handle is one failed response, never a transport-wide close.
   if('id' in message)this.onmessage?.({jsonrpc:'2.0',id:message.id,error:{code:-32603,message:`MCP_PAYLOAD_READ_FAILED: ${error.message}; 检查载荷文件/权限后重读本次调用，写操作先核对状态。`}});
   else this.onerror?.(error);
  });};
 }
 async start(){await mkdir(this.folder,{recursive:true});await this.inner.start();}
 async close(){await this.inner.close();}
 async send(message:JSONRPCMessage){
  const encoded=JSON.stringify(message)+'\n';
  if(Buffer.byteLength(encoded)<=MCP_INLINE_BYTES)return this.inner.send(message);
  const handle=randomUUID().replaceAll('-','');
  try{await writeFile(path.join(this.folder,handle+'.json'),encoded,{flag:'wx',mode:0o600});}
  catch(error){throw new Error(`MCP_PAYLOAD_WRITE_FAILED: 检查数据目录空间和权限；请求尚未发送。${(error as Error).message}`);}
  const wire:any={jsonrpc:'2.0',...('id' in message?{id:message.id}:{})};
  if('method' in message){wire.method=message.method;wire.params={[marker]:handle};}
  else wire.result={[marker]:handle};
  await this.inner.send(wire);
 }
 private async receive(message:JSONRPCMessage){
  const handle=(message as any).result?.[marker]??(message as any).params?.[marker];
  if(handle===undefined)return message;
  if(typeof handle!=='string'||!/^[a-f0-9]{32}$/.test(handle))throw new Error('invalid_mcp_payload_handle');
  const file=await realpath(path.join(this.folder,handle+'.json'));
  if(path.dirname(file)!==await realpath(this.folder))throw new Error('mcp_payload_path_escape');
  const full=JSONRPCMessageSchema.parse(JSON.parse(await readFile(file,'utf8')));
  if(('id' in full?full.id:undefined)!==('id' in message?message.id:undefined)||('method' in full?full.method:undefined)!==('method' in message?message.method:undefined))throw new Error('mcp_payload_response_mismatch');
  return full;
 }
}

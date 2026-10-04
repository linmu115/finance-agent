import { createServer, type Server } from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import type { AddressInfo } from 'node:net';

type Completion = (body: any, signal: AbortSignal) => Promise<{content:string; model:string; input:number; output:number}>;
/** Private run-scoped adapter: LangExtract -> the owning Pi ModelRuntime.
 * Neither the DeepSeek credential nor an independent model client crosses this boundary.
 */
export class PiModelBridge {
 private server?:Server;
 private starting?:Promise<void>;
 private owners=new Map<string,{token:string;complete:Completion;signal:AbortSignal}>();
 private async start(){
  if(this.starting)return this.starting;
  this.starting=new Promise<void>((resolve,reject)=>{
   this.server=createServer(async(req,res)=>{
    const match=/^\/([A-Za-z0-9_-]+)\/v1\/chat\/completions$/.exec(req.url||'');
    const owner=match?this.owners.get(match[1]):undefined;
    const supplied=Buffer.from(String(req.headers.authorization||'').replace(/^Bearer /,''));
    const wanted=Buffer.from(owner?.token||'');
    if(req.method!=='POST'||!owner||supplied.length!==wanted.length||!timingSafeEqual(supplied,wanted)||owner.signal.aborted){res.writeHead(403);res.end();return;}
    const disconnected=new AbortController();
    res.on('close',()=>{if(!res.writableFinished)disconnected.abort(new Error('Extraction client disconnected'));});
    try{
     const chunks:Buffer[]=[];let bytes=0;
     for await(const chunk of req){const buffer=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);bytes+=buffer.length;if(bytes>3*1024*1024)throw new Error('request_too_large');chunks.push(buffer);}
     // Network chunks can end inside a Chinese character. Decode only after
     // joining the bytes, and reject invalid UTF-8 instead of changing evidence.
     const body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks,bytes)));
     if(!Array.isArray(body.messages)||body.tools||body.stream)throw new Error('invalid_extraction_request');
     const result=await owner.complete(body,AbortSignal.any([owner.signal,disconnected.signal]));
     if(res.destroyed)return;
     res.writeHead(200,{'Content-Type':'application/json'});
     res.end(JSON.stringify({id:'pi-extract-'+randomBytes(8).toString('hex'),object:'chat.completion',created:Math.floor(Date.now()/1000),model:result.model,
      choices:[{index:0,message:{role:'assistant',content:result.content},finish_reason:'stop'}],
      usage:{prompt_tokens:result.input,completion_tokens:result.output,total_tokens:result.input+result.output}}));
    }catch(error){
     if(!res.destroyed){
      const permanent=(error as {status?:number})?.status;
      const status=permanent===401||permanent===402||permanent===422?permanent:owner.signal.aborted?499:502;
      const message=status===422?'structured_output_incomplete':status===402?'provider_balance_insufficient':status===401?'provider_authentication_failed':owner.signal.aborted?'session_cancelled':'pi_extraction_request_failed';
      const detail=error as {code?:string;request_id?:string;stop_reason?:string};
      const limit=status===422&&detail.code==='model_output_limit'&&detail.stop_reason==='length'&&typeof detail.request_id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(detail.request_id)
       ?{code:'model_output_limit',request_id:detail.request_id,stop_reason:'length'}:{};
      res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message,type:'runtime_error',...limit}}));
     }
    }
   });
   this.server.once('error',reject);this.server.listen(0,'127.0.0.1',resolve);
  });
  return this.starting;
 }
 async register(runId:string,signal:AbortSignal,complete:Completion){
  await this.start();const token=randomBytes(32).toString('hex');
  this.owners.set(runId,{token,complete,signal});
  return {base_url:`http://127.0.0.1:${(this.server!.address() as AddressInfo).port}/${runId}/v1`,api_key:token};
 }
 unregister(runId:string){this.owners.delete(runId);}
 async close(){this.owners.clear();if(this.server)await new Promise<void>(r=>{this.server!.close(()=>r());this.server!.closeAllConnections();});this.starting=undefined;this.server=undefined;}
}

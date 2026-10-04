import test from 'node:test';
import assert from 'node:assert/strict';
import {request} from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import {PiModelBridge} from '../server/model-bridge.js';

test('private model bridge preserves financial evidence split inside UTF-8 characters',async()=>{
 const bridge=new PiModelBridge();let seen:any;
 try{
  const owner=await bridge.register('utf8',new AbortController().signal,async(body)=>{
   seen=body;return {model:'test',content:'{}',input:1,output:1};
  });
  const expected={messages:[{role:'user',content:'主营业务收入；人民币百万元；上期重述。😀'}]};
  const bytes=Buffer.from(JSON.stringify(expected));
  const completed=new Promise<number>((resolve,reject)=>{
   const req=request(owner.base_url+'/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+owner.api_key,'Content-Type':'application/json'}},res=>{res.resume();res.on('end',()=>resolve(res.statusCode!));});
   req.on('error',reject);
   void(async()=>{for(let i=0;i<bytes.length;i++){req.write(bytes.subarray(i,i+1));await delay(1);}req.end();})().catch(reject);
  });
  assert.equal(await completed,200);assert.deepEqual(seen,expected);
 }finally{await bridge.close();}
});

test('invalid UTF-8 cannot silently replace original source text',async()=>{
 const bridge=new PiModelBridge();let calls=0;
 try{
  const owner=await bridge.register('invalid-utf8',new AbortController().signal,async()=>{calls++;return {model:'test',content:'{}',input:1,output:1};});
  const bytes=Buffer.concat([Buffer.from('{"messages":[{"role":"user","content":"'),Buffer.from([0xe4]),Buffer.from('"}]}')]);
  const response=await fetch(owner.base_url+'/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+owner.api_key,'Content-Type':'application/json'},body:bytes});
  assert.equal(response.status,502);assert.equal(calls,0);
 }finally{await bridge.close();}
});

test('only an audited output limit exposes safe split metadata',async()=>{
 const bridge=new PiModelBridge();
 try{
  for(const [name,error,expected] of [
   ['length',{status:422,code:'model_output_limit',stop_reason:'length',request_id:'original-request'},true],
   ['empty',{status:422},false],
   ['balance',{status:402,code:'model_output_limit',stop_reason:'length',request_id:'wrong'},false],
   ['network',{status:502,code:'model_output_limit',stop_reason:'length',request_id:'wrong'},false],
   ['unsafe',{status:422,code:'model_output_limit',stop_reason:'length',request_id:'bad/secret?token'},false],
  ] as const){
   const owner=await bridge.register(name,new AbortController().signal,async()=>{throw Object.assign(new Error('private upstream credential must not leak'),error);});
   const response=await fetch(owner.base_url+'/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+owner.api_key,'Content-Type':'application/json'},body:JSON.stringify({messages:[{role:'user',content:'fixture'}]})});
   assert.equal(response.status,error.status);
   const body=await response.json() as {error:Record<string,unknown>};
   assert.equal(body.error.code,expected?'model_output_limit':undefined);
   assert.equal(body.error.request_id,expected?'original-request':undefined);
   assert.equal(body.error.stop_reason,expected?'length':undefined);
   assert.doesNotMatch(JSON.stringify(body),/private upstream|secret|token/);
  }
 }finally{await bridge.close();}
});

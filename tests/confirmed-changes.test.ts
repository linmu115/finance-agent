import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { ApprovalQueue } from '../server/approvals.js';
import { ProjectResources } from '../server/project-resources.js';
import { modelInputCsv, parseModelInputCsv } from '../server/model-csv.js';

test('approval is immutable, one use, refuses changed digest and aborts waiting work',async()=>{
 const q=new ApprovalQueue(),abort=new AbortController(),op={sql:'DELETE FROM facts WHERE fact_id=?',parameters:['f1']};
 const waiting=q.request({runId:'run',conversationId:'chat',projectId:'p'},op,abort.signal);
 op.parameters[0]='f2';const pending=q.list()[0];assert.deepEqual((pending.operation as any).parameters,['f1']);
 (pending.operation as any).parameters[0]='tamper';assert.deepEqual((q.list()[0].operation as any).parameters,['f1']);
 assert.throws(()=>q.decide(pending.id,'0'.repeat(64),true));q.decide(pending.id,pending.digest,true);assert.equal((await waiting).id,pending.id);assert.throws(()=>q.decide(pending.id,pending.digest,true));
 const a=q.request({runId:'r',conversationId:'c',projectId:'p'},{sql:'DROP TABLE facts'},abort.signal);abort.abort();await assert.rejects(a,/停止/);assert.equal(q.list().length,0);
 const denied=q.request({runId:'r',conversationId:'c',projectId:'p'},op,new AbortController().signal);const x=q.list()[0];q.decide(x.id,x.digest,false);await assert.rejects(denied,/未授权/);
});

test('CSV round trips precision, newlines, arrays, quoted evidence and path keys',()=>{
 const spec={base:{revenue:'12345678901234567890.00000001'},forecast:[{year:2027,rate:'0.2'}],input_basis:{'forecast.0.rate':{rationale:'a,"b"\n第二行'}},source_refs:{'base/revenue~raw':[]}};
 assert.deepEqual(parseModelInputCsv(modelInputCsv('dcf',spec)),{kind:'dcf',spec});
 for(const csv of ['path,value\n/spec/__proto__/polluted,true\n/kind,"""dcf"""','path,value\n/kind,"""dcf"""\n/spec/a,1\n/spec/a/b,2','path,value\n/kind,"""dcf"""\n/spec/forecast/2/year,2027'])assert.throws(()=>parseModelInputCsv(csv));
 assert.equal(({} as any).polluted,undefined);
});

test('project agent.md and enabled skills persist, remain isolated, and reject stale writes',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-rules-'));
 try{const r=new ProjectResources(dir,path.resolve('skills'));const a=await r.load('alpha'),b=await r.load('beta');assert.equal(a.skills.length,3);assert.ok(a.skills.every(s=>s.enabled));
  const edited=await r.save('alpha',{rules:'金额统一人民币元；不自动推定缺失值。',enabled:['financial-modeling'],revision:a.revision});
  assert.notEqual(edited.revision,a.revision);assert.equal(edited.skills.filter(s=>s.enabled).length,1);assert.equal((await r.load('beta')).rules,b.rules);
  await assert.rejects(()=>r.save('alpha',{rules:'stale',enabled:[],revision:a.revision}),/已被修改/);await assert.rejects(()=>r.load('../outside'));
 }finally{await rm(dir,{recursive:true,force:true});}
});

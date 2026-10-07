import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {ArtifactStore,ARTIFACT_TOOLS} from '../server/research-artifacts.js';

test('artifact-only uses latest; a bad revision names latest without selecting it silently or leaking another project',async()=>{
 const store=new ArtifactStore(await mkdtemp(path.join(tmpdir(),'source-model-')));
 const first=await store.save('p',{kind:'dcf_fcf',title:'Model',dependencies:[],spec:{wacc:'.122'}});
 const last=await store.save('p',{kind:'dcf_fcf',title:'Model',dependencies:[],spec:{wacc:'.127'},parent_revision_id:first.revision_id},first.id);
 assert.equal((await store.get('p',first.id)).revision_id,last.revision_id);
 assert.equal((await store.get('p',first.id,first.revision_id)).spec.wacc,'.122');
 await assert.rejects(store.get('p',first.id,'revision_wrong'),(e:Error)=>e.message.includes(last.revision_id)&&e.message.includes('省略 revision_id'));
 await assert.rejects(store.get('other-project',first.id,'revision_wrong'),(e:Error)=>e.message==='研究成果不存在');
 const tool=ARTIFACT_TOOLS.find(t=>t.name==='run_financial_model')!;
 assert.match((tool.inputSchema.properties.source_model as any).description,/首选只传/);
});

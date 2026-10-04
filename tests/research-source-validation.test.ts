import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {ArtifactStore,ResearchWorkspace} from '../server/research-artifacts.js';
import {ResearchStore} from '../server/research.js';

async function fixture(run:(x:any)=>Promise<void>){
 const directory=await mkdtemp(path.join(tmpdir(),'research-source-validation-'));
 try{
  const artifacts=new ArtifactStore(directory),sources=new ResearchStore(directory),calls:any[]=[];
  const state={documentVersion:'doc_v1',mutateDuringRead:false,readForbidden:false};
  const service:any={call:async(name:string,args:any)=>{
   calls.push({name,args:structuredClone(args)});
   if(name==='get_research_document_version')return {status:'ok',data:{version:state.documentVersion}};
   if(name==='get_source_page'){
    if(state.readForbidden)throw Error('Original citation must not be re-read');
    if(args.page!==1)throw Error('page_not_found');
    if(state.mutateDuringRead)state.documentVersion='doc_v2';
    return {status:'ok',data:{page:1,text:'The disclosed revenue was 120 units.'}};
   }
   if(name==='evaluate_research_model')return {status:'ok',data:{results:{equity_value:'12'},tables:{}}};
   throw Error('Unexpected '+name);
  }};
  const workspace=new ResearchWorkspace(service,artifacts,sources);
  await run({artifacts,sources,calls,state,workspace});
 }finally{const resolved=path.resolve(directory);assert.equal(path.dirname(resolved),path.resolve(tmpdir()));await rm(resolved,{recursive:true,force:true});}
}
const model=(ref:any,basis='disclosed')=>({title:'Synthetic source validation',kind:'dcf',spec:{base:{revenue:'120'},source_refs:{'base.revenue':[ref]},input_basis:{'base.revenue':{basis,rationale:'Model-proposed classification; not a host semantic guarantee'}}}});
const sourceDownload=(text:string)=>async()=>({body:Buffer.from(text),url:'https://example.com/report',contentType:'text/plain',headers:{}});

test('new model webpage citations reject absent paragraph or false quotation before calculation',async()=>fixture(async({workspace,sources,calls}:any)=>{
 const source=await sources.saveSnapshot('p','https://example.com/report',{download:sourceDownload('Revenue 120 units.')});
 for(const ref of [{kind:'source',id:source.source_id,locator:'p99'},{kind:'source',id:source.source_id,locator:'p1',quote:'Revenue 999 units.'}])await assert.rejects(()=>workspace.model('p',model(ref)),/段落不存在|引用文字未在/);
 assert.equal(calls.filter((x:any)=>x.name==='evaluate_research_model').length,0);
 const saved=await workspace.model('p',model({kind:'source',id:source.source_id,locator:'p1',quote:'Revenue 120 units.'}));
 assert.equal(saved.source_validation.references[0].status,'locator_and_quote_match');
 assert.equal(saved.source_validation.semantic_accuracy_verified,false);
 assert.equal(saved.source_validation.references[0].version,source.sha256);
}));

test('model artifact references resolve actual fields and exact requested revision',async()=>fixture(async({workspace,artifacts}:any)=>{
 const old=await artifacts.save('p',{kind:'dcf',title:'Upstream',dependencies:[],result:{results:{equity_value:'120'}}});
 const newer=await artifacts.save('p',{...old,parent_revision_id:old.revision_id,result:{results:{equity_value:'130'}}},old.id);
 for(const ref of [{kind:'artifact',id:old.id,locator:'results.missing'},{kind:'artifact',id:old.id,locator:'results.equity_value',revision_id:old.revision_id,quote:'130'}])await assert.rejects(()=>workspace.model('p',model(ref)),/字段不存在|引用文字未在/);
 const input=model({kind:'artifact',id:old.id,revision_id:old.revision_id,locator:'results.equity_value',quote:'120'}),original=structuredClone(input);
 const saved=await workspace.model('p',input);
 assert.deepEqual(input,original);assert.equal(saved.dependencies[0].version,old.revision_id);
 assert.equal(saved.spec.source_refs['base.revenue'][0].revision_id,old.revision_id);
 assert.equal(saved.changed_dependencies[0].current_version,newer.revision_id);
 assert.equal(saved.source_validation.references[0].status,'locator_and_quote_match');
}));

test('model citation without artifact revision pins first read and does not mutate caller input',async()=>fixture(async({workspace,artifacts}:any)=>{
 const old=await artifacts.save('p',{kind:'dcf',title:'Concurrent upstream',dependencies:[],result:{results:{equity_value:'120'}}});
 const originalGet=artifacts.get.bind(artifacts);let changed=false;
 artifacts.get=async(project:string,id:string,revision?:string)=>{
  const result=await originalGet(project,id,revision);
  if(!changed&&id===old.id&&!revision){changed=true;await artifacts.save('p',{...old,parent_revision_id:old.revision_id,result:{results:{equity_value:'130'}}},old.id);}
  return result;
 };
 const input=model({kind:'artifact',id:old.id,locator:'results.equity_value',quote:'120'});
 const saved=await workspace.model('p',input);
 assert.equal((input.spec.source_refs['base.revenue'][0] as any).revision_id,undefined);
 assert.equal(saved.spec.source_refs['base.revenue'][0].revision_id,old.revision_id);
 assert.equal(saved.dependencies[0].version,old.revision_id);assert.equal(saved.dependency_status,'stale');
}));

test('document model citations reject invalid page and mismatch, and detect state change during source reading',async()=>fixture(async({workspace,state,calls}:any)=>{
 await assert.rejects(()=>workspace.model('p',model({kind:'document',id:'d1',locator:'page:0'})),/物理页码/);
 await assert.rejects(()=>workspace.model('p',model({kind:'document',id:'d1',locator:'page:2'})),/page_not_found/);
 await assert.rejects(()=>workspace.model('p',model({kind:'document',id:'d1',locator:'page:1',quote:'Revenue 999'})),/引用文字未在/);
 state.mutateDuringRead=true;
 await assert.rejects(()=>workspace.model('p',model({kind:'document',id:'d1',locator:'page:1',quote:'120 units.'})),/核验期间发生变化/);
 assert.equal(calls.filter((x:any)=>x.name==='evaluate_research_model').length,0);
}));

test('multiple references to one document share page retrieval and one before/after version check',async()=>fixture(async({workspace,calls}:any)=>{
 const input=model({kind:'document',id:'d1',locator:'page:1',quote:'120 units.'});
 (input.spec.source_refs as any).another=[{kind:'document',id:'d1',locator:'page:1'}];
 const saved=await workspace.model('p',input);
 assert.deepEqual(saved.dependencies,[{kind:'document',id:'d1',version:'doc_v1'}]);
 assert.equal(calls.filter((x:any)=>x.name==='get_source_page').length,1);
 // Includes one final status read, in addition to validation's before/after pair.
 assert.equal(calls.filter((x:any)=>x.name==='get_research_document_version').length,3);
 assert.deepEqual(saved.source_validation.references.map((x:any)=>x.status),['locator_and_quote_match','locator_exists']);
}));

test('legacy dependency-only refs remain explicitly unverified even if model claims disclosed',async()=>fixture(async({workspace,calls}:any)=>{
 const input=model({document_id:'d1',page:1,quote:'Not validated without a locator'});
 const saved=await workspace.model('p',input);
 assert.deepEqual(saved.dependencies,[{kind:'document',id:'d1',version:'doc_v1'}]);
 assert.equal(saved.source_validation.references[0].status,'dependency_only_unverified');
 assert.equal(saved.source_validation.semantic_accuracy_verified,false);
 assert.equal(saved.spec.input_basis['base.revenue'].basis,'disclosed');
 assert.equal(calls.some((x:any)=>x.name==='get_source_page'),false);
}));

test('synthetic annotation refs are preserved without inventing a source or verification',async()=>fixture(async({workspace}:any)=>{
 const input=model({type:'synthetic_example',note:'not a source'},'assumption'),saved=await workspace.model('p',input);
 assert.deepEqual(saved.spec,input.spec);assert.equal(saved.dependencies.length,0);
 assert.deepEqual(saved.source_validation.references,[{path:'/source_refs/base.revenue/0',status:'annotation_unverified'}]);
}));

test('dependency-only artifact revision stays fixed but never implies its contents were checked',async()=>fixture(async({workspace,artifacts}:any)=>{
 const old=await artifacts.save('p',{kind:'dcf',title:'Historical',dependencies:[],result:{results:{equity_value:'120'}}});
 await artifacts.save('p',{...old,parent_revision_id:old.revision_id,result:{results:{equity_value:'130'}}},old.id);
 const saved=await workspace.model('p',model({kind:'artifact',id:old.id,revision_id:old.revision_id,quote:'A false unchecked claim'}));
 assert.equal(saved.dependencies[0].version,old.revision_id);assert.equal(saved.source_validation.references[0].status,'dependency_only_unverified');assert.equal(saved.dependency_status,'stale');
}));

test('source_model import never revalidates or upgrades historical evidence',async()=>fixture(async({workspace,artifacts,state,calls}:any)=>{
 const inheritedSpec=model({kind:'document',id:'d1',locator:'page:1',quote:'Historical unavailable text'}).spec;
 const original=await artifacts.save('p',{kind:'manufacturing_scenario',title:'Legacy scenario',dependencies:[{kind:'document',id:'d1',version:'doc_v1'}],result:{results:{scenario_dcf_spec:inheritedSpec}}});
 state.documentVersion='doc_v2';state.readForbidden=true;
 const saved=await workspace.model('p',{title:'Exact import',kind:'dcf',source_model:{artifact_id:original.id,variant:'scenario'}});
 assert.deepEqual(saved.spec,inheritedSpec);assert.equal(saved.dependencies.find((d:any)=>d.id==='d1').version,'doc_v1');
 assert.equal(saved.source_validation.mode,'inherited_unverified');assert.equal(saved.source_validation.inherited_from.revision_id,original.revision_id);
 assert.equal(calls.some((x:any)=>x.name==='get_source_page'),false);
}));

test('source_model refuses an unpinned inherited reference rather than treating latest as its old source',async()=>fixture(async({workspace,artifacts,calls}:any)=>{
 const original=await artifacts.save('p',{kind:'manufacturing_scenario',title:'Incomplete legacy metadata',dependencies:[],result:{results:{scenario_dcf_spec:model({kind:'document',id:'d1',locator:'page:1'}).spec}}});
 await assert.rejects(()=>workspace.model('p',{title:'Cannot rebind',kind:'dcf',source_model:{artifact_id:original.id,variant:'scenario'}}),/未记录固定版本/);
 assert.equal(calls.length,0);
}));

test('validated-scenario imports reference the original audit without claiming new semantic validation',async()=>fixture(async({workspace,artifacts}:any)=>{
 const input=model({kind:'document',id:'d1',locator:'page:1',quote:'120 units.'});
 const checked=await workspace.model('p',input);
 const original=await artifacts.save('p',{kind:'manufacturing_scenario',title:'Recorded audit',dependencies:checked.dependencies,source_validation:checked.source_validation,result:{results:{scenario_dcf_spec:checked.spec}}});
 const imported=await workspace.model('p',{title:'Inherited audit',kind:'dcf',source_model:{artifact_id:original.id,variant:'scenario'}});
 assert.equal(imported.source_validation.mode,'inherited');assert.equal(imported.source_validation.inherited_from.original_mode,'checked');
 assert.equal(imported.source_validation.semantic_accuracy_verified,false);assert.equal(imported.source_validation.references,undefined);
 assert.deepEqual(imported.spec,checked.spec);
}));

test('inconsistent historical artifact citation and dependency revisions cannot be silently imported',async()=>fixture(async({workspace,artifacts,calls}:any)=>{
 const upstream=await artifacts.save('p',{kind:'dcf',title:'Historical upstream',dependencies:[],result:{results:{equity_value:'120'}}});
 const original=await artifacts.save('p',{kind:'manufacturing_scenario',title:'Contradictory historical provenance',dependencies:[{kind:'artifact',id:upstream.id,version:upstream.revision_id}],result:{results:{scenario_dcf_spec:model({kind:'artifact',id:upstream.id,revision_id:'different_revision',locator:'results.equity_value'}).spec}}});
 await assert.rejects(()=>workspace.model('p',{title:'Cannot hide conflict',kind:'dcf',source_model:{artifact_id:original.id,variant:'scenario'}}),/引用版本与原依赖不一致/);
 assert.equal(calls.length,0);
}));

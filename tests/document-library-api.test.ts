import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDocumentLibraryApi} from '../server/document-library-api.js';

async function invoke(body:any,active=false){
 let handler:any,result:any,error:any,status=200;const calls:any[]=[];
 installDocumentLibraryApi({delete:(_path:string,fn:any)=>{handler=fn;}} as any,{call:async(...args:any[])=>{calls.push(args);return {data:{removed:{facts:2}}};}} as any,()=>active);
 const response={status:(s:number)=>{status=s;return response;},json:(v:any)=>{result=v;}};
 await handler({params:{projectId:'p',documentId:'d'},body},response,(e:any)=>{error=e;});
 return {calls,result,error,status};
}
test('attachment deletion requires confirmation for the exact document',async()=>{
 for(const body of [{},{confirm_document_id:'other'}]){const r=await invoke(body);assert.ok(r.error);assert.equal(r.calls.length,0);}
 const r=await invoke({confirm_document_id:'d'});assert.deepEqual(r.calls,[['delete_library_document',{project_id:'p',document_id:'d'}]]);assert.equal(r.result.removed.facts,2);
});
test('active project cannot race deletion against agent writes',async()=>{
 const r=await invoke({confirm_document_id:'d'},true);assert.equal(r.status,409);assert.equal(r.calls.length,0);
});
test('purge is host-only and benchmark navigation is replaced',async()=>{
 const [runs,app]=await Promise.all(['server/runs.ts','web/src/App.tsx'].map(file=>readFile(file,'utf8')));
 assert.ok(!runs.includes('delete_library_document'));
 assert.ok(app.includes('<span>附件看板</span>'));assert.ok(!app.includes('数据集与测试'));assert.ok(!app.includes('DatasetView'));
});

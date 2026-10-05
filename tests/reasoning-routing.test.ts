import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTaskRoute,initialEffort,fallbackRoute} from '../server/reasoning-routing.js';
import {resolveCompactionPolicy} from '../server/context-compaction.js';
import {projectToolHistory} from '../server/model-context.js';

test('mixed ingestion and modeling stays low until extraction finishes; router output is validated',()=>{
 const route=parseTaskRoute('{"task":"modeling","afterIngestion":"low","reason":"DCF"}');
 assert.equal(initialEffort(route,true),'low');assert.equal(route.afterIngestion,'high');assert.equal(initialEffort(route,false),'high');
 assert.equal(initialEffort(fallbackRoute,true),'low');assert.throws(()=>parseTaskRoute('{"task":"override","afterIngestion":"max"}'));
});
test('legacy default follows a million-token model; deliberate custom settings stay manual',()=>{
 const legacy={enabled:true,targetTokens:96000,keepRecentTokens:24000,summaryMaxTokens:8192};
 assert.equal(resolveCompactionPolicy(legacy,1048576,32768).targetTokens,838860);
 assert.equal(resolveCompactionPolicy({...legacy,targetTokens:16000},1048576,32768).targetTokens,16000);
 assert.equal(resolveCompactionPolicy({...legacy,mode:'manual'},1048576,32768).targetTokens,96000);
});
test('history keeps old and fresh source payloads until Pi performs pressure-based compaction',()=>{
 const messages=Array.from({length:60},(_,i)=>[{role:'assistant',content:[{type:'toolCall',id:'call-'+i,name:'get_source_page',arguments:{document_id:'d',page:i+1}}]},{role:'toolResult',toolCallId:'call-'+i,toolName:'get_source_page',content:[{type:'text',text:JSON.stringify({status:'ok',data:{document_id:'d',page:i+1,text:'source evidence '.repeat(1800)}})}]}]).flat();
 const original=JSON.stringify(messages),result=projectToolHistory({messages});
 assert.equal(JSON.stringify(messages),original);assert.equal(result.context.messages.length,messages.length);
 assert.equal(JSON.parse(result.context.messages[1].content[0].text!).data.text,'source evidence '.repeat(1800));
 assert.equal(JSON.parse(result.context.messages.at(-1)!.content[0].text!).data.text,'source evidence '.repeat(1800));
 assert.deepEqual(result.context.messages,messages);assert.equal(result.context.messages[0],messages[0]);
});

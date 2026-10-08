import {test} from 'node:test';
import assert from 'node:assert/strict';
import {modelContext,projectToolHistory} from '../server/model-context.js';

test('analysis tools and native history retain partial document availability',()=>{
 const doc={document_id:'d',original_name:'年报',state:'partial',fact_count:100,
  status_label:'核心表已完成 / 12 张待处理 / 3 张搁置',
  ingestion:{availability:'partial',analysis_available:true,tables_completed:20,tables_pending:12,tables_deferred:3,core_complete:true}};
 for(const tool of ['list_documents','get_document','get_data_catalog']){
  const data=tool==='get_document'?doc:tool==='list_documents'?{items:[doc]}:{documents:[doc]};
  const actual=modelContext(tool,{status:'ok',data}).data;
  const visible=tool==='get_document'?actual:tool==='list_documents'?actual.items[0]:actual.documents[0];
  assert.equal(visible.state,'partial');assert.equal(visible.status_label,doc.status_label);
  assert.deepEqual(visible.ingestion,doc.ingestion);
 }
 const context:any={messages:[{role:'toolResult',toolName:'get_data_catalog',content:[{type:'text',text:JSON.stringify({status:'ok',data:{documents:[doc]}})}]}]};
 const history=projectToolHistory(context).context;
 const visible=JSON.parse(history.messages[0].content[0].text).data.documents[0];
 assert.equal(visible.status_label,doc.status_label);
 assert.equal(visible.ingestion.analysis_available,true);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {ingestionRemaining,madeIngestionProgress} from '../server/ingestion-continuation.js';
import {modelContext} from '../server/model-context.js';

const snapshot=(id:string,done:number[],facts=0)=>({processing_id:id,pending_tables:{d:[1,2,3].filter(t=>!done.includes(t))},pending_pages:{d:[]},document_progress:[{document_id:'d',completed_tables:done,fact_count:facts,table_statuses:{}}]});

test('only committed document progress advances continuation',()=>{
 const a=ingestionRemaining([snapshot('p',[1],2)]);
 const failed=ingestionRemaining([{...snapshot('p',[1],2),unattempted_tables:{d:[]}}]);
 assert.equal(madeIngestionProgress(a.progress,failed.progress),false);
 assert.equal(madeIngestionProgress(a.progress,ingestionRemaining([snapshot('p',[1,2],2)]).progress),true);
 assert.equal(madeIngestionProgress(a.progress,ingestionRemaining([snapshot('p',[1],4)]).progress),true);
 assert.equal(madeIngestionProgress(a.progress,ingestionRemaining([snapshot('p',[1],1)]).progress),false);
});

test('duplicate refreshed checkpoints use one stable processing ID regardless of order',()=>{
 const a=snapshot('a',[1,2],4),b=snapshot('b',[1,2],4);
 const before=ingestionRemaining([snapshot('b',[1],4)]),after=ingestionRemaining([b,a]);
 assert.equal(after.work.length,1);assert.equal(after.work[0].processing_id,'a');
 assert.deepEqual(after,ingestionRemaining([a,b]));
 assert.equal(madeIngestionProgress(before.progress,after.progress),true);
 assert.equal(madeIngestionProgress(after.progress,ingestionRemaining([a]).progress),false);
 assert.equal(ingestionRemaining([snapshot('a',[1,2,3],4)]).keys.size,0);
});

test('source projection preserves every raw row, merged geometry and distinct text',()=>{
 const rows=[['Revenue','100','40%']],merged={merged_range:'A1:A2',bbox:[1,2,3,4]};
 const original={status:'ok',data:{items:[{document_id:'d',table_id:'d:t1',page:2,rows,cells:{A1:merged,B1:{text:'100',bbox:[2,3,4,5]}},row_source_refs:[{row:1,source_id:'s',text:'Revenue 100 40%'}]}]}};
 const result=modelContext('get_source_table',original);
 assert.deepEqual(result.data.items[0].rows,rows);assert.deepEqual(result.data.items[0].merged_cells.A1,merged);
 const page=modelContext('get_source_page',{status:'ok',data:{text:'Annual report',segments:[{source_id:'a',text:'Annual report'},{source_id:'b',text:'Extra footnote'}]}});
 assert.equal(page.data.text,'Annual report');assert.equal(page.data.segments[0].text,undefined);assert.equal(page.data.segments[1].text,'Extra footnote');
});

test('commit projection keeps new doubts and failures without repeating prior cumulative issues',()=>{
 const input={status:'partial',data:{committed_tables:[2],failed_tables:[{index:3,issues:[{reason:'missing column'}]}],review_issues:[{table:1,raw_value:'old'},{table:2,raw_value:'new'}],pending_tables:{d:[3,4]},next_batch:{tables:[3,4]}}};
 const out=modelContext('commit_cleaning_result',input);
 assert.deepEqual(out.data.review_issues,[{table:2,raw_value:'new'}]);assert.deepEqual(out.data.failed_tables,input.data.failed_tables);
 assert.deepEqual(out.data.pending_table_counts,{d:2});assert.deepEqual(out.data.next_batch,{tables:[3,4]});
 assert.deepEqual(modelContext('commit_cleaning_result',out),out);
});

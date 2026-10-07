import test from 'node:test';
import assert from 'node:assert/strict';
import {ingestionRemaining,madeIngestionProgress} from '../server/ingestion-continuation.js';
import {modelContext} from '../server/model-context.js';

test('continuation uses remaining tables, research pages and pending repairs without a turn limit',()=>{
 const a={processing_id:'old',pending_tables:{d:[1,2]},pending_pages:{d:[3]},pending_scripts:[]};
 const b={processing_id:'new',pending_tables:{d:[2]},pending_pages:{d:[]},pending_scripts:[{document_id:'d',table:4,run_id:'repair'}]};
 const first=ingestionRemaining([a]),next=ingestionRemaining([a,b]);
 assert.equal(next.work.length,1);assert.equal(next.work[0].processing_id,'new');
 assert.equal(madeIngestionProgress(first.keys,next.keys),true);
 assert.equal(madeIngestionProgress(next.keys,ingestionRemaining([b]).keys),false);
 assert.equal(ingestionRemaining([{...b,pending_tables:{d:[]},pending_scripts:[]}]).keys.size,0);
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

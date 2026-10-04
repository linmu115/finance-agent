import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
// @ts-expect-error The independent scorer is intentionally executable plain ESM.
import {checkFact,scoreNormalization} from '../scripts/score_normalization.mjs';
// @ts-expect-error Plain ESM utilities shared by executable acceptance scripts.
import {decimalKey,extractionEvidence,extractionSignature,collectNormalizationPages} from '../scripts/validation_utils.mjs';
const expected={id:'x',file:'fixture.csv',cell:'B5',metric:'revenue',period:'2025-FY',value:'347625000',currency:'CNY',scope:'consolidated_CAS',restatement:'original'};
const actual={document_id:'doc1',metric:'revenue',period:'2025-FY',value:'347625000.00',currency:'CNY',scope:'consolidated_CAS',source_ref:{document_id:'doc1',table_id:'doc1:t0',row:5,column:2,cell:'B5',page:1,normalization:{engine:'LangExtract',label:'营业收入',restatement:'original',char_interval:[1,10]}}};
test('independent scorer rejects wrong magnitude, version, source, period and fabricated engine',()=>{
 assert.deepEqual(checkFact(expected,actual),[]);
 assert.ok(checkFact(expected,{...actual,value:'3476250'}).includes('value'));
 assert.ok(checkFact(expected,{...actual,period:'2024-FY'}).includes('period'));
 assert.ok(checkFact(expected,{...actual,source_ref:{...actual.source_ref,cell:'C5'}}).includes('source_cell'));
 assert.ok(checkFact(expected,{...actual,source_ref:{...actual.source_ref,normalization:{...actual.source_ref.normalization,restatement:'restated'}}}).includes('restatement'));
 assert.ok(checkFact(expected,{...actual,source_ref:{...actual.source_ref,normalization:{...actual.source_ref.normalization,engine:'rule'}}}).includes('not_langextract'));
 assert.ok(checkFact(expected,{...actual,label:'2025年度'}).includes('semantic_metric_label'),'a period header must not replace the metric display label');
});
test('duplicate facts cannot satisfy another source cell and missing values cannot become zero',()=>{
 const result=scoreNormalization([expected,{...expected,id:'y',cell:'C5'}],[{file:'fixture.csv',cell:'B6',reason:'missing'}],[actual,{...actual,value:'0',source_ref:{...actual.source_ref,cell:'B6'}}],[{id:'doc1',file:'fixture.csv'}]);
 assert.equal(result.passed_facts,1);assert.equal(result.failed_facts,1);assert.equal(result.failed_forbidden_checks,1);
 const contradictory=scoreNormalization([expected],[],[actual,{...actual,value:'999'}],[{id:'doc1',file:'fixture.csv'}]);
 assert.equal(contradictory.passed_facts,0);assert.ok(contradictory.checks[0].errors.includes('conflicting_source_facts'));
});
test('decimal comparison preserves cents above Number safe precision and cache evidence requires matching original Pi output',()=>{
 assert.notEqual(decimalKey('9007199254740992.01'),decimalKey('9007199254740992.02'));
 assert.equal(decimalKey('000123.4500'),decimalKey('123.45'));assert.equal(decimalKey('-0.000'),'0');
 const extraction={class:'financial_row',text:'[[T1:R2]]',attributes:{metric:'revenue',label:'营业收入'}};
 const events=[{type:'extraction_request',data:{requestId:'a',ownerRunId:'run1',runtime:'Pi.ModelRuntime'}},{type:'extraction_result',data:{requestId:'a',ownerRunId:'run1',stopReason:'stop',content:JSON.stringify({extractions:[{financial_row:extraction.text,financial_row_attributes:extraction.attributes}]})}}];
 const proof=extractionEvidence(events,'run1');assert.equal(proof.successful_results,1);assert.ok(proof.signatures.has(extractionSignature(extraction)));
 assert.ok(!proof.signatures.has(extractionSignature({...extraction,attributes:{metric:'assets',label:'资产'}})));
 assert.equal(extractionEvidence(events,'different-run').signatures.size,0);
});
test('normalization pagination rejects a server that silently returns the first page again',async()=>{
 const result=await collectNormalizationPages(async(url:string)=>{const offset=Number(new URL(url,'http://local').searchParams.get('offset'));return {total:3,offset,batches:offset===0?[{batch_key:'a'},{batch_key:'b'}]:[{batch_key:'c'}]};},'/normalization');
 assert.equal(result.batches.length,3);assert.equal(result.pagination.requests,2);
 await assert.rejects(collectNormalizationPages(async()=>({total:3,offset:0,batches:[{batch_key:'a'},{batch_key:'b'}]}),'/normalization'),/ignored pagination/);
});
test('gold revision 2 accepts equivalent PPE purchase cash outflows and rejects receipts, non-cash items and other asset concepts',async()=>{
 const dir=new URL('../benchmark/versions/v0.3.1-normalization/',import.meta.url);
 const gold=(await readFile(new URL('gold.jsonl',dir),'utf8')).trim().split('\n').map(line=>JSON.parse(line));
 const cases=JSON.parse(await readFile(new URL('label-equivalence-tests.json',dir),'utf8'));
 const expected=gold.find(g=>g.id===cases.gold_id);assert.ok(expected);
 const fact={...actual,metric:'payments_for_acquisition_of_property_plant_and_equipment',currency:'USD',value:'-2375000',scope:'parent_IFRS',source_ref:{...actual.source_ref,cell:'B6',row:6}};
 for(const label of cases.positive)assert.deepEqual(checkFact(expected,{...fact,label}),[],label);
 for(const label of cases.negative)assert.ok(checkFact(expected,{...fact,label}).includes('metric_label'),'different concept must fail: '+label);
 const old=(await readFile(new URL('../v0.3-normalization/gold.jsonl',dir),'utf8')).trim().split('\n').map(line=>JSON.parse(line)).find(g=>g.id===cases.gold_id);
 assert.equal(old.label_regex,'购建|购置|固定资产|资本.*支出','the published original gold must remain unchanged');
 assert.ok(checkFact(old,{...fact,label:'购买物业、厂房及设备支付的现金'}).includes('metric_label'),'retain evidence of the old false negative');
});

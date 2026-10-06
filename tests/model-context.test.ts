import {test} from 'node:test';
import assert from 'node:assert/strict';
import {modelContext,projectToolHistory} from '../server/model-context.js';
test('uncertainty and incomplete extraction remain actionable in model-facing views',()=>{
 const source={document_id:'d',page:3,normalization:{review_warnings:['unknown_unit'],semantic_review_note:'单位未明确；需读上页表头',definition_review:{audits:['duplicate audit']}}};
 const fact={value:'1234',raw_value:'1,234',raw_unit:'unknown',quality:'needs_review',source_ref:source};
 const result=modelContext('query_financial_data',{status:'ok',data:{items:[fact]},source_refs:[source]});
 assert.equal(result.data.items[0].raw_value,'1,234');
 assert.equal(result.data.items[0].source_ref.normalization.semantic_review_note,source.normalization.semantic_review_note);
 assert.deepEqual(result.data.items[0].source_ref.normalization.review_warnings,['unknown_unit']);
 assert.deepEqual(result.source_refs,[{document_id:'d',page:3}]);
 const review={document_id:'d',state:'needs_review',review_issues:[{table:2,reason:'unreadable_chart',detail:'留存原图'}],text_coverage:{review_issues:[{page:3,reason:'unreadable_chart'}]}};
 const catalog=modelContext('get_data_catalog',{status:'ok',data:{processing:[{state:'needs_review',documents:[review]}]}});
 assert.deepEqual(catalog.data.processing[0].documents[0].review_issues,review.review_issues);
 assert.deepEqual(catalog.data.processing[0].documents[0].text_coverage,review.text_coverage);
});
test('research query removes duplicate sources without losing quotes, financial meaning or review warnings',()=>{
 const source={document_id:'doc',page:2,cell:'B3',quote:'精确来源'.repeat(300),start:10,end:1210,normalization:{period_start:'2025-01-01',period_end:'2025-12-31',scale:'1000000',review_warnings:['unresolved_currency'],numeric_span:{text:'68.64',start:3,end:8}}};
 const record={record_id:'r',value:'68.64',raw_value:'68.64',raw_unit:'元/股',data_kind:'analyst_forecast',publisher:'Broker',published_at:'2025-07-23',scenario:'base',dimensions:{product:'milk'},quality:'needs_review',source,source_ref:source,source_json:JSON.stringify(source)};
 const original={status:'ok',data:{items:[record],total:1,next_offset:null},source_refs:[source],warnings:['needs_review']};
 const before=JSON.stringify(original),projected=modelContext('query_research_records',original),item=projected.data.items[0];
 assert.equal(JSON.stringify(original),before);assert.deepEqual(item.source_ref,source);
 for(const key of ['record_id','value','raw_value','raw_unit','data_kind','publisher','published_at','scenario','dimensions','quality'])assert.deepEqual(item[key],(record as any)[key]);
 assert.equal(item.source,undefined);assert.equal(item.source_json,undefined);assert.equal(projected.source_refs![0].document_id,'doc');assert.equal(projected.data.next_offset,null);assert.deepEqual(projected.warnings,original.warnings);
 assert.ok(JSON.stringify(projected).length<before.length/2);
 const context={messages:[{role:'toolResult',toolName:'query_research_records',content:[{type:'text',text:before}]}]};
 const once=projectToolHistory(context);assert.equal(once.projection.modified_tool_results,1);assert.equal(projectToolHistory(once.context).projection.modified_tool_results,0);
});
test('model catalog removes repeated audits but preserves all metrics, dimensions and paths',()=>{
 const original={status:'ok',data:{database_path:'data/finance.sqlite',metrics:Array.from({length:500},(_,i)=>({metric:'m'+i,label:'指标'+i})),dimensions:{scope:['a','b']},processing:[{processing_id:'p',state:'completed',catalog_review:{status:'complete',audits:Array(500).fill({text:'source'.repeat(200)})}}],metric_aliases:[{source_metric:'old',canonical_metric:'new',canonical_label:'归一',evidence:{payload:'large'.repeat(10000)}}]}};
 const projected=modelContext('get_data_catalog',original);
 assert.deepEqual(projected.data.metrics,original.data.metrics);assert.deepEqual(projected.data.dimensions,original.data.dimensions);assert.equal(projected.data.database_path,original.data.database_path);assert.equal(projected.data.metric_aliases[0].canonical_metric,'new');assert.ok(original.data.metric_aliases[0].evidence);assert.ok(JSON.stringify(projected).length<JSON.stringify(original).length/10);
});

test('legacy Pi tool history is projected without altering persisted messages or financial fields',()=>{
 const envelope={status:'ok',data:{database_path:'data/finance.sqlite',metrics:[{metric:'revenue',label:'营业收入'}],processing:[{state:'completed',definition_review:{status:'reviewed',audits:Array(30).fill({raw:'历史原文'.repeat(100)})}}]}};
 const message={role:'toolResult',toolName:'get_data_catalog',toolCallId:'original-call',content:[{type:'text',text:JSON.stringify(envelope)}]},user={role:'user',content:JSON.stringify(envelope)};
 const context={systemPrompt:'original system',messages:[user,message,{role:'toolResult',toolName:'calculate_financial_metrics',content:[{type:'text',text:'{"data":{"value":"123.456"}}'}]}]};
 const original=JSON.stringify(context),projected=projectToolHistory(context);
 assert.equal(JSON.stringify(context),original);assert.equal(projected.context.messages[0],user);assert.equal(projected.context.messages[2],context.messages[2]);
 assert.equal(projected.context.messages[1].toolCallId,'original-call');assert.equal(projected.projection.modified_tool_results,1);
 assert.ok(projected.projection.after_chars<projected.projection.before_chars/10);
 const data=JSON.parse(projected.context.messages[1].content[0].text).data;
 assert.deepEqual(data.metrics,envelope.data.metrics);assert.equal(data.database_path,envelope.data.database_path);
 assert.equal(data.processing[0].definition_review.status,'reviewed');
 const again=projectToolHistory(projected.context);assert.equal(again.projection.modified_tool_results,0);
});
test('fact values and financial meaning remain while duplicated raw audit is removed',()=>{
 const fact={fact_id:'f',value:'123.4567',period:'2024',scope:'consolidated',unit_kind:'percentage_points',dimensions:{segment:'a'},source_ref:{document_id:'d',page:2,cell:'B3',text:'减少2.5个百分点'},definition:'商品销售',definition_scope:'不含租金',definition_review:{status:'reviewed',after:{definition:'商品销售'},audits:Array(100).fill({reason:'x'})},source_json:'large'};
 const p=modelContext('query_financial_data',{status:'ok',data:{total:1,items:[fact]}}).data.items[0];
 for(const k of ['value','period','scope','unit_kind','source_ref','definition','definition_scope','dimensions'])assert.deepEqual(p[k],(fact as any)[k]);assert.equal(p.definition_review.after.definition,'商品销售');assert.equal(p.source_json,undefined);
});

test('metric lookup keeps exact amounts, dimensions, conflicts and every source while removing duplicate raw reviews',()=>{
 const source={document_id:'d',page:12,table_id:'d:t3',row:2,column:4,text:'租赁负债 123.4500',bbox:[1,2,3,4],normalization:{source_key:'source-key',source_fingerprint:'fingerprint',original_extraction_hash:'model-hash',char_interval:[2,8],definition_review:{audits:'原始审计'.repeat(5000)}}};
 const fact={fact_id:'fact',value:'123.4500',raw_value:'12.345',raw_unit:'万元',period:'2025H1',scope:'consolidated_CAS',unit_kind:'amount',definition:'长期部分',definition_scope:'不含一年内到期',dimensions:{maturity:'noncurrent'},source_ref:source,alternative_sources:[{...source,page:13}],quality:'conflict',conflicting_values:['123.4600']};
 const input={status:'ok',data:{items:[fact],available_metrics:['lease_liabilities']},source_refs:[source],warnings:['conflicting_financial_values_require_review']},original=JSON.stringify(input);
 const projected=modelContext('get_financial_metrics',input),actual=projected.data.items[0];
 for(const key of ['value','raw_value','raw_unit','period','scope','unit_kind','definition','definition_scope','dimensions','quality','conflicting_values'])assert.deepEqual(actual[key],(fact as any)[key]);
 for(const ref of [actual.source_ref,actual.alternative_sources[0]]){
  assert.deepEqual(ref.normalization.char_interval,[2,8]);assert.equal(ref.text,source.text);assert.deepEqual(ref.bbox,source.bbox);assert.equal(ref.normalization.definition_review,undefined);
 }
 assert.equal(projected.source_refs![0].table_id,source.table_id);assert.equal(projected.source_refs![0].column,source.column);
 assert.equal(actual.alternative_sources[0].page,13);assert.deepEqual(projected.warnings,input.warnings);assert.equal(JSON.stringify(input),original);assert.ok(JSON.stringify(projected).length<original.length/10);
});

test('large legacy and paginated indexes remain readable until native context compaction',()=>{
 const legacy={status:'ok',data:{document_id:'doc',index_path:'indexes/p/catalog.yaml',index_yaml:'pages:\n'+'  - heading: 原文索引\n'.repeat(3000)}};
 const original=JSON.stringify(legacy),projected=modelContext('get_document_index',legacy);
 assert.deepEqual(projected,legacy);assert.equal(JSON.stringify(legacy),original);
 const paginated={...legacy,data:{...legacy.data,pagination:{pages:{total:200,offset:0,limit:40,has_more:true,next_offset:40}}}};
 assert.deepEqual(modelContext('get_document_index',paginated),paginated);
});

test('long tool loops never evict exact evidence based on its age or tool count',()=>{
 const evidenceTools=['get_source_table','get_source_page','search_evidence','read_research_artifact','get_document_index','get_processing_checkpoint','query_financial_data','get_financial_metrics'];
 const evidence=evidenceTools.map(toolName=>({role:'toolResult',toolName,toolCallId:toolName,content:[{type:'text',text:JSON.stringify({status:'ok',data:{document_id:'annual-2024',table_id:'t1',items:[{value:'123456.7800',period:'2023',scope:'consolidated',unit:'CNY'}],text:'完整可核验原文'.repeat(2500)}})}]}));
 const calculations=Array.from({length:150},(_,i)=>({role:'toolResult',toolName:'calculate_financial_metrics',content:[{type:'text',text:JSON.stringify({data:{value:String(i)}})}]}));
 const context={messages:[...evidence,...calculations]},before=JSON.stringify(context),projected=projectToolHistory(context);
 assert.equal(JSON.stringify(context),before);assert.deepEqual(projected.context.messages,evidence.concat(calculations as any));
 assert.ok(!JSON.stringify(projected.context).includes('context_released'));
});

test('saved financial model returns exact calculation and revision; full input remains explicitly retrievable',()=>{
 const data={id:'research-a',revision_id:'revision-1',kind:'dcf',spec:{source_refs:[{document_id:'d',page:9,quote:'原始披露'}]},result:{equity_value:'-123.456',sensitivity:[{value:'1.2300'}]},dependencies:[{kind:'artifact',id:'research-parent',version:'revision-old'}],dependency_status:'stale',changed_dependencies:[{reason:'changed'}],source_validation:{semantic_accuracy_verified:false,references:[{status:'unverified'}]}};
 const original=JSON.stringify(data),projected=modelContext('run_financial_model',{status:'ok',data});
 for(const key of ['result','dependencies','dependency_status','changed_dependencies','source_validation'])assert.deepEqual(projected.data[key],(data as any)[key]);
 assert.equal(projected.data.spec,undefined);assert.equal(projected.data.saved_input.read_tool,'read_research_artifact');assert.equal(projected.data.saved_input.artifact_id,data.id);assert.equal(projected.data.saved_input.revision_id,data.revision_id);assert.equal(JSON.stringify(data),original);
 assert.deepEqual(modelContext('read_research_artifact',{status:'ok',data}),{status:'ok',data});
 assert.equal(projected.data.saved_input.spec_saved,true);
 assert.deepEqual(modelContext('run_financial_model',projected),projected);
 const history={messages:[{role:'toolResult',toolName:'run_financial_model',content:[{type:'text',text:JSON.stringify(projected)}]}]};
 assert.equal(projectToolHistory(history).projection.modified_tool_results,0);
});

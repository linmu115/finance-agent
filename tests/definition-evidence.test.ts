import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent host-only ESM validator.
import {validateDefinitionCache} from '../scripts/definition_evidence.mjs';
test('definition acceptance requires the exact owning Pi decision and quotes in its own source group',()=>{
 const quote={evidence_id:'own',text:'普通股股本'},decision={group_id:'g',metric:'ordinary_share_capital',label:'普通股股本',definition:'普通股份面值合计',definition_scope:'普通股',reason:'原表明确分类',grounded_quotes:[quote]};
 const ex={class:'definition_decision',text:'[[DEFINITION:g]]',attributes:{metric:decision.metric,label:decision.label,definition:decision.definition,definition_scope:decision.definition_scope,reason:decision.reason,grounded_quotes_json:JSON.stringify([quote])}};
 const cache={decisions:[decision],extractions:[ex],_review_provenance:{owner_run_id:'owner',processing_id:'processing'}};
 const content='[[EVIDENCE_CONTEXT:E1]] '+JSON.stringify({text:'本表为普通股股本明细'})+'\n[[DEFINITION:g]] '+JSON.stringify({group_id:'g',evidence:[{evidence_id:'own',text_ref:'E1'}]});
 const request={type:'extraction_request',data:{requestId:'r',ownerRunId:'owner',runtime:'Pi.ModelRuntime',messages:[{role:'user',content}]}};
 const result={type:'extraction_result',data:{requestId:'r',ownerRunId:'owner',stopReason:'stop',content:JSON.stringify({extractions:[{extraction_class:ex.class,extraction_text:ex.text,attributes:ex.attributes}]})}};
 assert.equal(validateDefinitionCache(cache,[request,result]).status,'passed');
 assert.equal(validateDefinitionCache({...cache,decisions:[{...decision,metric:'preferred_share_capital'}]},[request,result]).status,'failed');
 assert.equal(validateDefinitionCache(cache,[{...request,data:{...request.data,ownerRunId:'another'}},result]).status,'failed');
 assert.equal(validateDefinitionCache(cache,[{...request,data:{...request.data,messages:[{role:'user',content:content.replace('本表为普通股股本明细','本表为优先股明细')}] }},result]).status,'failed');
 assert.equal(validateDefinitionCache(cache,[request,{...result,data:{...result.data,stopReason:'length'}}]).status,'failed');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {hasValuationJudgment,valuationSections} from '../server/answer-semantics.js';

const fixture=(name:string)=>readFileSync(new URL('./fixtures/v3-delivery/'+name,import.meta.url),'utf8');
test('actual F2_X7 and P2_X7 first and repair responses do not assert a valuation',()=>{
 for(const name of ['F2_X7-1.md','F2_X7-2.md','P2_X7-1.md','P2_X7-2.md']){
  assert.equal(hasValuationJudgment(fixture(name)),false,name);
  assert.deepEqual(valuationSections(fixture(name)),[],name);
 }
 // Their actual bullet sections also satisfy the contract when an affirmative conclusion is appended.
 for(const name of ['F2_X7-2.md','P2_X7-2.md'])assert.deepEqual(valuationSections(fixture(name)+'\n我们的目标价为20元。'),[],name);
});
test('negations and attributed quotes do not hide a separate actual recommendation',()=>{
 for(const s of ['本文不做估值或投资建议。','未作估值或投资判断。','估值或投资判断：无。',
  '机构给出目标价20元。','管理层认为合理价值为30元。','引用“目标价20元”。','> 目标价20元。',
  'This is not a target price or investment recommendation.','DCF方法需要预测现金流。',
  '估值日2024年12月31日。','DCF模型所需输入：现金流100。','目标价不是20元。'])assert.equal(hasValuationJudgment(s),false,s);
 for(const s of ['目标价20元。','估值为{{model.x.value}}。','建议持有。','我们认为估值偏高。',
  '不提供估值。但建议买入。','研报认为目标价20元。但我们测算目标价15元。',
  'Our target price is 20.','We recommend buy.'])assert.equal(hasValuationJudgment(s),true,s);
});
test('substantive sections accept Markdown structures but not empty labels',()=>{
 const layouts=[
  '- **假设：**收入保持。\n- **风险**：需求下降。\n- **适用范围：**当前情景。',
  '**假设**\n收入保持。\n**风险**\n需求下降。\n**适用范围**\n当前情景。',
  '| 项目 | 内容 |\n|---|---|\n|假设|收入保持|\n|风险|需求下降|\n|适用范围|当前情景|',
  '|假设|风险|适用范围|\n|---|---|---|\n|收入保持|需求下降|当前情景|',
  '## 假设 / 风险 / 适用范围\n假设收入保持；风险为需求下降；适用范围为本次输入情景。',
  '## 假设 / 风险 / 适用范围\n收入保持，关注需求下降，仅适用于本次情景。',
 ];
 for(const body of layouts)assert.deepEqual(valuationSections('目标价20元。\n'+body),[],body);
 for(const body of ['## 假设 / 风险 / 适用范围','- **假设：**\n- **风险：**\n- **适用范围：**',
  '|假设|风险|适用范围|\n|---|---|---|','假设、风险、适用范围：待补充'])
  assert.deepEqual(valuationSections('目标价20元。\n'+body),['假设','风险','适用范围'],body);
 assert.deepEqual(valuationSections('目标价20元。\n## 假设\n## 风险\n需求下降。\n## 适用范围\n当前情景。'),['假设']);
});

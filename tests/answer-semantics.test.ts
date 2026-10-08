import test from 'node:test';
import assert from 'node:assert/strict';
import {annotateAnswer,valuationSections} from '../server/answer-semantics.js';

test('facts need bindings or known locators, inference and opinion remain model judgments',()=>{
 const sources=[{documentId:'doc-1',page:8,url:'https://example.test/report'}];
 assert.match(annotateAnswer('收入 {{income.2024.value}}。',sources),/^【事实\/数据】/);
 assert.match(annotateAnswer('【事实】收入增长。',sources),/^【推论·缺少绑定或来源】/);
 assert.match(annotateAnswer('收入增长（doc-1 第8页）。',sources),/^【事实\/数据】/);
 assert.equal(annotateAnswer('doc-1 第9页：收入增长。',sources),'doc-1 第9页：收入增长。');
 assert.match(annotateAnswer('【事实】见 https://unread.test。',sources),/^【推论·/);
 assert.equal(annotateAnswer('【观点】现金值得关注。'),'【观点】现金值得关注。');
 assert.equal(annotateAnswer('【推论】基于 {{income.x.v}}，增长或与提价有关。'),'【推论】基于 {{income.x.v}}，增长或与提价有关。');
 assert.equal(annotateAnswer('原因未知。'),'原因未知。');
 assert.match(annotateAnswer('【事实】值 {{t.r.c}}。原因确定为提价。'),/。\u3010推论·缺少绑定或来源\u3011原因/);
 assert.equal(annotateAnswer('{{table:income}}'),'【事实/数据】\n\n{{table:income}}');
 assert.equal(annotateAnswer('```\n【事实】示例\n```'),'```\n【事实】示例\n```');
});
test('valuation needs substantive headings, ordinary financial analysis does not',()=>{
 assert.deepEqual(valuationSections('收入同比下降。'),[]);
 assert.deepEqual(valuationSections('目标价 20 元；风险是宏观。'),['假设','风险','适用范围']);
 assert.deepEqual(valuationSections('目标价 20 元。\n## 假设\n\n## 风险\n增长不及预期。\n## 适用范围\n本次情景。'),['假设']);
 assert.deepEqual(valuationSections('估值 20 元。\n## 假设\n保持资本结构。\n## 风险\n增长不及预期。\n## 适用范围\n本次输入情景。'),[]);
});

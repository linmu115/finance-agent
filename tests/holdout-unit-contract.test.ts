import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent read-only scorer correction.
import {correctPublishedPercentUnit} from '../scripts/rescore_holdout_unit_contract.mjs';
test('percent unit contract correction never pardons wrong values, currency or other failed checks',()=>{
 const source={checks:[{name:'30个独立源格逐项核对',status:'failed'},{name:'执行失败',status:'failed'}],normalization:{checks:[{id:'onlyunit',status:'failed',expected:{currency:'percent'},actual:{currency:'percent',normalized_unit:'%'},errors:['normalized_unit']},{id:'badvalue',status:'failed',expected:{currency:'percent'},actual:{currency:'percent',normalized_unit:'%'},errors:['normalized_unit','value']},{id:'badcurrency',status:'failed',expected:{currency:'percent'},actual:{currency:'CNY',normalized_unit:'%'},errors:['normalized_unit','currency']},{id:'badunit',status:'failed',expected:{currency:'percent'},actual:{currency:'percent',normalized_unit:'元'},errors:['normalized_unit']} ]}};
 const {report,changes}=correctPublishedPercentUnit(source);assert.equal(changes.length,2);assert.equal(report.score.passed,1);assert.equal(report.score.failed,3);assert.equal(report.status,'failed');assert.equal(report.checks[1].status,'failed');assert.deepEqual(report.normalization.checks[1].errors,['value']);assert.deepEqual(source.normalization.checks[0].errors,['normalized_unit'],'original is preserved');
});

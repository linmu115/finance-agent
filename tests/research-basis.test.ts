import test from 'node:test';
import assert from 'node:assert/strict';
import {inputBasisRows, markDraftInputEdits} from '../web/src/research-basis.js';

const example = () => ({base: {revenue: '100'}, forecast: [{year: 2025, revenue: '110'}, {year: 2026, revenue: '110'}],
 input_basis: {'base.revenue': {basis: 'disclosed', rationale: '已读披露'}, 'forecast.0.revenue': {basis: 'derived', rationale: '基期乘增速'}},
 source_refs: {'base.revenue': [{kind: 'source', id: 'web_1', locator: 'p1'}], 'forecast.0.revenue': [{kind: 'document', id: 'doc_1', locator: 'page:3'}]}});

test('citations alone do not turn unknown inputs into disclosed facts', () => {
 const spec = example(); delete (spec as any).input_basis;
 assert.equal(inputBasisRows(spec).find(row => row.path === 'base.revenue')?.basis, 'unknown');
 assert.equal(inputBasisRows(spec).find(row => row.path === 'base.revenue')?.refs.length, 1);
});
test('editing a sourced value creates an assumption draft and preserves original metadata and source', () => {
 const old = example(), changed = structuredClone(old); changed.base.revenue = '130';
 const next = markDraftInputEdits(old, changed);
 assert.equal(next.input_basis['base.revenue'].basis, 'assumption');
 assert.match(next.input_basis['base.revenue'].rationale, /界面中修改/);
 assert.deepEqual(next.source_refs, old.source_refs);
 assert.equal(old.input_basis['base.revenue'].basis, 'disclosed');
 assert.equal(old.base.revenue, '100');
 assert.equal(next.input_basis['forecast.0.revenue'].basis, 'derived');
});
test('advanced JSON cannot change a value and still claim its old disclosure', () => {
 const old = example(), changed = structuredClone(old); changed.base.revenue = '170';
 changed.input_basis['base.revenue'] = {basis: 'disclosed', rationale: '手写仍称披露'};
 assert.equal(markDraftInputEdits(old, changed).input_basis['base.revenue'].basis, 'assumption');
});
test('typing more digits does not repeatedly nest the original rationale', () => {
 const old = example(), changed = structuredClone(old); changed.base.revenue = '170';
 const first = markDraftInputEdits(old, changed), second = structuredClone(first); second.base.revenue = '1700';
 assert.equal(markDraftInputEdits(first, second).input_basis['base.revenue'].rationale, first.input_basis['base.revenue'].rationale);
});
test('deleting/reindexing years does not inherit source status for an equal-valued different-year row', () => {
 const old = example(), changed = structuredClone(old); changed.forecast.splice(0, 1);
 const next = markDraftInputEdits(old, changed);
 assert.equal(next.input_basis['forecast.0.revenue'].basis, 'assumption');
 assert.match(next.input_basis['forecast.0.revenue'].rationale, /原引用仅供对照/);
 assert.equal(next.input_basis['forecast.1.revenue'], undefined);
});
test('path matching accepts bracket source references without creating another source store', () => {
 const spec = example() as any;
 spec.source_refs = {'forecast[0].revenue': [{kind: 'source', id: 'web_1', locator: 'p7'}]};
 const row = inputBasisRows(spec).find(item => item.path === 'forecast.0.revenue')!;
 assert.equal(row.basis, 'derived'); assert.equal(row.refs[0].locator, 'p7');
 assert.equal(inputBasisRows(spec).some(item => item.path.startsWith('source_refs')), false);
});

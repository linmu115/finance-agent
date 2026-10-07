import test from 'node:test';
import assert from 'node:assert/strict';
import {numericTableView} from '../server/numeric-tables.js';
import {modelContext} from '../server/model-context.js';
test('model budget lists every table, exact cells and explicit continuation without mutating host tables',()=>{
 const data={run_id:'run',numeric_tables:{a:{columns:{v:{unit:'%'}},rows:[{v:'33.6462645995'},{v:'41.378'}],row_keys:['2025','2024'],display_rows:[{v:'33.65 %'},{v:'41.38 %'}],artifact:'a.csv',origin:'csv'},b:{columns:{x:{unit:'元/股',currency:'HKD'}},rows:[{x:'11.2304285827'}],row_keys:['low'],artifact:'b.csv',origin:'csv'}}};
 const full=numericTableView(data);assert.deepEqual(full.numeric_tables.a.rows,data.numeric_tables.a.rows);
 const limited=numericTableView(data,50);assert.equal(limited.numeric_tables.a.truncation.remaining_rows,2);assert.equal(limited.numeric_tables.b.truncation.read.name,'b.csv');assert.equal(data.numeric_tables.a.rows.length,2);
 const result=modelContext('get_analysis_status',{status:'ok',data,source_refs:[],warnings:[],trace_id:'trace'});assert.equal(result.data.numeric_tables.a.rows[0].v,'33.6462645995');
});

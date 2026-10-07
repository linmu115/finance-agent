import test from 'node:test';
import assert from 'node:assert/strict';
import {numericTableView,registerNumericTables} from '../server/numeric-tables.js';
import {modelContext} from '../server/model-context.js';
test('model budget lists every table, exact cells and explicit continuation without mutating host tables',()=>{
 const data={run_id:'run',numeric_tables:{a:{columns:{v:{unit:'%'}},rows:[{v:'33.6462645995'},{v:'41.378'}],row_keys:['2025','2024'],display_rows:[{v:'33.65 %'},{v:'41.38 %'}],artifact:'a.csv',origin:'csv'},b:{columns:{x:{unit:'元/股',currency:'HKD'}},rows:[{x:'11.2304285827'}],row_keys:['low'],artifact:'b.csv',origin:'csv'}}};
 const full=numericTableView(data);assert.deepEqual(full.numeric_tables.a.rows,data.numeric_tables.a.rows);
 const limited=numericTableView(data,50);assert.equal(limited.numeric_tables.a.truncation.remaining_rows,2);assert.equal(limited.numeric_tables.b.truncation.read.name,'b.csv');assert.equal(data.numeric_tables.a.rows.length,2);
 const result=modelContext('get_analysis_status',{status:'ok',data,source_refs:[],warnings:[],trace_id:'trace'});assert.equal(result.data.numeric_tables.a.rows[0].v,'33.6462645995');
});

test('repairs replace plain names; scenarios retire ambiguous names and retain baseline continuation',()=>{
 const table=(v:string)=>({columns:{value:{unit:'元/股'}},rows:[{value:v}],row_keys:['price']});
 const registry:any={};registerNumericTables(registry,{numeric_tables:{t:table('10')}});registerNumericTables(registry,{numeric_tables:{t:table('11')}});
 assert.equal(registry.t.rows[0].value,'11');
 const data={id:'new',revision_id:'new_rev',changes:{from:{artifact_id:'old',revision_id:'old_rev'}},scenario_context:{unqualified_names:['t']},numeric_tables:{基准_old__t:{...table('11'),scenario_role:'baseline'},情景_new__t:{...table('9'),scenario_role:'scenario'}}};
 registerNumericTables(registry,data);assert.equal(registry.t,undefined);assert.equal(registry['基准_old__t'].rows[0].value,'11');
 const view=numericTableView(data,1);assert.equal(view.numeric_tables['基准_old__t'].truncation.read.revision_id,'old_rev');
});

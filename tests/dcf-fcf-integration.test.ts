import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';

test('FCF model host path saves, updates with operators, publishes reports, binds and projects without losing numbers',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-dcf-fcf-'));process.env.FINANCE_DATA_DIR=dir;
 const {FinanceService}=await import('../server/mcp.js');const {ResearchWorkspace,ArtifactStore,deliveryFile}=await import('../server/research-artifacts.js');
 const {modelContext}=await import('../server/model-context.js');const {registerNumericTables}=await import('../server/numeric-tables.js');
 const service=new FinanceService();await service.connect();
 try{
  await service.call('create_project',{project_id:'dcf',name:'FCF test'});
  const workspace=new ResearchWorkspace(service,new ArtifactStore(path.join(dir,'research')));
  const base=await workspace.model('dcf',{title:'Frozen values',kind:'dcf_fcf',spec:{currency:'CNY',amount_scale:'1000000',valuation_date:'2023-12-31',discount:{cashflow_timing:'year_end'},fcf:['288','512','591','594','626'],wacc:'.122',g:'.02',net_cash:'320',shares:{count:'555',scale:'1000000'},price_currency:'HKD',fx:'1.07'}});
  assert.ok(base.result.results.value_per_share.startsWith('10.8912980269'));assert.equal(base.result.tables.sensitivity.length,25);
  await assert.rejects(workspace.model('dcf',{title:'Bad reference',kind:'dcf_fcf',source_model:{artifact_id:base.id,revision_id:'mistyped/revision'},overrides:{wacc:{'+':.005}}}),(e:Error)=>e.message.includes(base.revision_id)&&e.message.includes('省略 revision_id'));
  const changed=await workspace.model('dcf',{title:'Updated',kind:'dcf_fcf',source_model:{artifact_id:base.id,revision_id:base.revision_id},overrides:{wacc:{'+':.005},fcf:{'*':.9}},order:['wacc','fcf']});
  assert.equal(changed.spec.wacc,'0.127');assert.deepEqual(changed.spec.fcf,['259.2','460.8','531.9','534.6','563.4']);
  assert.ok(changed.result.results.value_per_share.startsWith('9.4076395415'));assert.equal(changed.changes.decomposition.steps.length,2);
  assert.ok(changed.delivery.files.some((f:any)=>f.name.endsWith('report.md')));assert.ok(changed.numeric_tables.dcf_update_contributions);
  const registry:any={};registerNumericTables(registry,base);registerNumericTables(registry,changed);
  const baselineTable=changed.scenario_context.baseline.tables.dcf_summary,scenarioTable=changed.scenario_context.scenario.tables.dcf_summary;
  assert.equal(registry.dcf_summary,undefined);
  const rendered=(await service.call('render_answer',{project_id:'dcf',body:`基准 {{${baselineTable}.value_per_share.value}}；情景 {{${scenarioTable}.value_per_share.value}}\n{{table:基准_情景_差额}}\n{{table:dcf_update_contributions}}`,tables:registry,charts:{}})).data;
  assert.ok(JSON.stringify(rendered).includes('基准 10.89 HKD 元/股'));
  assert.ok(JSON.stringify(rendered).includes('9.41 HKD 元/股'));
  assert.ok(JSON.stringify(rendered).includes('差额（情景减基准）'));
  assert.equal(registry['基准_情景_差额'].evidence[0].old.version_id,base.revision_id);
  const raw=JSON.stringify(changed);const projected=modelContext('run_financial_model',{status:'ok',data:changed}).data;
  assert.equal(JSON.stringify(changed),raw);assert.equal(projected.result.report,undefined);assert.equal(projected.changes.report,undefined);
  assert.equal(projected.numeric_tables[scenarioTable].rows.find((r:any)=>r.metric==='value_per_share').value,changed.result.results.value_per_share);
  assert.ok(JSON.stringify(projected).length<raw.length/2);
  const manifest=JSON.parse(await readFile(path.join(dir,'research/dcf/deliveries',changed.delivery.id,'delivery.json'),'utf8'));
  assert.ok(manifest.attachments.includes('saved_report.md'));
  assert.ok(manifest.attachments.includes('基准_情景_差额_report.md'));
  const comparison=await deliveryFile('dcf',changed.delivery.id,'基准_情景_差额_report.md',service);
  assert.match(comparison.bytes.toString('utf8'),/10.89 HKD 元\/股/);assert.match(comparison.bytes.toString('utf8'),/9.41 HKD 元\/股/);
  const downloaded=await deliveryFile('dcf',changed.delivery.id,'saved_report.md',service);assert.ok(downloaded.bytes.toString('utf8').includes('9.41 HKD 元/股'));
  assert.equal((await workspace.get('dcf',base.id,base.revision_id)).spec.wacc,'.122');
 }finally{await service.close();}
});

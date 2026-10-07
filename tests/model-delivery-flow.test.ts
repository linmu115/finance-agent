import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const sha = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');
const csv = (text: string) => { const [head, ...rows] = text.replace(/^﻿/, '').trim().split(/\r?\n/).map(line => line.split(',')); return rows.map(row => Object.fromEntries(head.map((key, i) => [key, row[i]]))); };

test('saving or updating a model delivers its tables, differences and calculator in the same call', { timeout: 120000 }, async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-model-delivery-'));
  process.env.FINANCE_DATA_DIR = dir;
  const { loadSettings } = await import('../server/config.js');
  const { FinanceService } = await import('../server/mcp.js');
  const { ResearchWorkspace } = await import('../server/research-artifacts.js');
  const { installResearchApi } = await import('../server/research-api.js');
  const { RunManager } = await import('../server/runs.js');
  const { modelContext } = await import('../server/model-context.js');
  const { default: express } = await import('express');
  await loadSettings();
  const service = new FinanceService(); await service.connect();
  const app = express(); app.use(express.json());
  installResearchApi(app, async id => { if (!['valuation', 'other'].includes(id)) throw Object.assign(new Error('项目不存在'), { status: 404 }); return id; }, service);
  app.use((error: any, _req: any, res: any, _next: any) => res.status(error.status || 400).json({ error: error.message }));
  const server = app.listen(0, '127.0.0.1'); await new Promise<void>(resolve => server.once('listening', resolve));
  const origin = 'http://127.0.0.1:' + (server.address() as any).port;
  const manager: any = new RunManager(service);
  try {
    for (const id of ['valuation', 'other']) await service.call('create_project', { project_id: id, name: id });
    const example = (await service.call('get_research_model_schema', { project_id: 'valuation', kind: 'dcf' })).data.synthetic_example;
    const spec = structuredClone(example.spec ?? example); spec.amount_scale = '1000000'; delete spec.sensitivity;
    const workspace = new ResearchWorkspace(service);

    // 1. A new model: one call, files already attached.
    const base: any = await workspace.model('valuation', { title: '估值：基准/情景', kind: 'dcf', spec });
    assert.equal(base.changes, undefined);
    const names = (model: any) => model.delivery.files.map((file: any) => file.name).sort();
    assert.deepEqual(names(base), ['估值：基准_情景_forecast.csv', '估值：基准_情景_inputs.csv', '估值：基准_情景_model_bundle.zip', '估值：基准_情景_sensitivity.csv', '估值：基准_情景_units.csv']);
    const fetched = async (file: any) => { const response = await fetch(origin + file.url); assert.equal(response.status, 200, file.name); return { response, bytes: Buffer.from(await response.arrayBuffer()) }; };
    const inputs = csv((await fetched(base.delivery.files.find((f: any) => f.name.endsWith('_inputs.csv')))).bytes.toString('utf8'));
    const unitOf = Object.fromEntries(inputs.map(row => [row.path, row.unit]));
    assert.equal(unitOf['discount.wacc'], 'ratio');
    assert.equal(unitOf['base.revenue'], spec.currency + ' 百万元');
    assert.equal(inputs.find(row => row.path === 'discount.wacc')!.value, spec.discount.wacc);

    // 2. An update of that model: differences against the version it replaces, with ordered contributions.
    const order = ['discount.wacc', 'terminal.growth'];
    const updated: any = await workspace.model('valuation', { title: '估值：基准/情景', kind: 'dcf', artifact_id: base.id, source_model: { artifact_id: base.id }, overrides: { 'discount.wacc': '0.12', 'terminal.growth': '0.01' }, order });
    assert.equal(updated.id, base.id);
    assert.equal(updated.parent_revision_id, base.revision_id);
    assert.deepEqual(updated.changes.from, { artifact_id: base.id, revision_id: base.revision_id });
    assert.deepEqual(updated.changes.changed_inputs, [{ path: 'discount.wacc', before: spec.discount.wacc, after: '0.12' }, { path: 'terminal.growth', before: spec.terminal.growth, after: '0.01' }]);
    const value = updated.changes.result_changes.value_per_share;
    assert.equal(value.before, String(base.result.results.value_per_share));
    assert.equal(value.after, String(updated.result.results.value_per_share));
    assert.notEqual(value.before, value.after);
    assert.deepEqual(updated.changes.decomposition.steps.map((step: any) => step.path), order);
    const total = updated.changes.decomposition.steps.reduce((sum: number, step: any) => sum + Number(step.contribution), 0);
    assert.ok(Math.abs(total - Number(value.change)) < 1e-9);
    assert.deepEqual(names(updated), ['forecast.csv', 'inputs.csv', 'model_bundle.zip', 'sensitivity.csv', 'units.csv', 'update_decomposition.csv', 'update_forecast_changes.csv', 'update_inputs_changed.csv', 'update_results_changed.csv'].map(name => '估值：基准_情景_' + name).sort());
    const folder = path.join(dir, 'research', 'valuation', 'deliveries', updated.delivery.id), manifest = JSON.parse(await readFile(path.join(folder, 'delivery.json'), 'utf8'));
    for (const file of updated.delivery.files) {
      const { response, bytes } = await fetched(file), stored = decodeURIComponent(new URL(origin + file.url).pathname.split('/').pop()!);
      const listed = manifest.files.find((item: any) => item.name === stored);
      assert.equal(sha(bytes), listed.sha256, file.name);
      assert.match(response.headers.get('content-disposition')!, /^attachment/);
    }
    const changed = csv((await fetched(updated.delivery.files.find((f: any) => f.name.endsWith('update_inputs_changed.csv')))).bytes.toString('utf8'));
    assert.deepEqual(changed.map(row => [row.path, row.before, row.after]), [['discount.wacc', spec.discount.wacc, '0.12'], ['terminal.growth', spec.terminal.growth, '0.01']]);

    // A complete spec saved onto the same model (how the workspace editor saves) reports what it changed as well.
    const edited: any = await workspace.model('valuation', { title: '估值：基准/情景', kind: 'dcf', artifact_id: base.id, parent_revision_id: updated.revision_id, spec: { ...updated.spec, discount: { ...updated.spec.discount, wacc: '0.125' } } });
    assert.deepEqual(edited.changes.from, { artifact_id: base.id, revision_id: updated.revision_id });
    assert.deepEqual(edited.changes.changed_inputs, [{ path: 'discount.wacc', before: '0.12', after: '0.125' }]);
    assert.ok(names(edited).includes('估值：基准_情景_update_inputs_changed.csv'));

    // 3. An order that does not match the actual changes saves nothing.
    const revisions = async () => (await readdir(path.join(dir, 'research', 'valuation', 'artifacts'))).length;
    const before = await revisions();
    await assert.rejects(workspace.model('valuation', { title: '错误顺序', kind: 'dcf', artifact_id: base.id, source_model: { artifact_id: base.id }, overrides: { 'discount.wacc': '0.13' }, order: ['terminal.growth'] }), /decomposition_order_must_cover_changed_inputs_once/);
    await assert.rejects(workspace.model('valuation', { title: '缺少来源', kind: 'dcf', spec, order }), /order用于更新已保存模型/);
    assert.equal(await revisions(), before);
    assert.equal((await workspace.get('valuation', base.id)).revision_id, edited.revision_id);

    // 4. Only listed files of this project's delivery are served, and only while unchanged.
    const url = (name: string, project = 'valuation', id = updated.delivery.id) => `${origin}/api/projects/${project}/research/deliveries/${id}/${encodeURIComponent(name)}`;
    assert.equal((await fetch(url('saved_inputs.csv'))).status, 200);
    for (const target of [url('delivery.json'), url('../delivery.json'), url('..\\..\\artifacts\\' + base.revision_id + '.json'), url('missing.csv'), url('saved_inputs.csv', 'other'), url('saved_inputs.csv', 'unknown'), url('saved_inputs.csv', 'valuation', 'f'.repeat(32)), url('saved_inputs.csv', 'valuation', '..')])
      assert.equal((await fetch(target)).status, 404, target);
    await writeFile(path.join(folder, 'saved_units.csv'), 'table,column,unit\nforecast,revenue,USD 亿元\n');
    const tampered = await fetch(url('saved_units.csv'));
    assert.equal(tampered.status, 400);
    assert.match((await tampered.json() as any).error, /与清单不一致/);

    // 5. In a conversation the files appear as downloads; a newer version of the same model replaces the older one's files.
    const live = { run: { id: 'run', projectId: 'valuation' }, answer: { artifacts: [] as any[] } };
    const first = await manager.artifactTool(live, 'run_financial_model', { title: '对话模型', kind: 'dcf', spec });
    assert.equal(live.answer.artifacts.filter(a => a.id.startsWith('delivery:')).length, 5);
    const second = await manager.artifactTool(live, 'run_financial_model', { title: '对话模型', kind: 'dcf', artifact_id: first.data.id, source_model: { artifact_id: first.data.id }, overrides: { 'discount.wacc': '0.11' } });
    const attached = live.answer.artifacts.filter(a => a.id.startsWith('delivery:'));
    assert.equal(attached.length, 8);
    assert.equal(new Set(attached.map(a => a.name)).size, attached.length);
    assert.ok(attached.every(a => a.url.includes('/deliveries/' + second.data.delivery.id + '/') && a.id.startsWith('delivery:' + first.data.id + ':')));
    assert.deepEqual(attached.map(a => a.mimeType).sort().filter((type, i, all) => all.indexOf(type) === i), ['application/octet-stream', 'text/csv']);
    const download = await fetch(origin + attached.find(a => a.name.endsWith('_inputs.csv')).url);
    assert.equal(decodeURIComponent(download.headers.get('content-disposition')!.split("''")[1]), '对话模型_inputs.csv');
    // No order was given, so the differences are reported without a contribution split.
    assert.equal(second.data.changes.decomposition, null);
    assert.deepEqual(second.data.changes.changed_inputs.map((c: any) => c.path), ['discount.wacc']);

    // 6. What the model reads back: names of what the user already has, and no instruction to export again.
    const seen: any = modelContext('run_financial_model', second).data;
    assert.deepEqual(seen.delivery, { delivered_to_user: second.data.delivery.files.map((file: any) => file.name) });
    assert.match(seen.analysis.delivery, /delivery.delivered_to_user/);
    assert.deepEqual(seen.analysis.model_refs, { model: { artifact_id: second.data.id, revision_id: second.data.revision_id } });
    assert.deepEqual(seen.changes.changed_inputs, second.data.changes.changed_inputs);
    assert.equal(seen.spec, undefined);
    // Projecting an already projected result (older history) keeps the same content.
    assert.deepEqual(modelContext('run_financial_model', { status: 'ok', data: structuredClone(seen) } as any).data.delivery, seen.delivery);
  } finally {
    await manager.shutdown(); await service.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    await rm(dir, { recursive: true, force: true });
  }
});

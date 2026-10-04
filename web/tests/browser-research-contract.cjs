/* Controlled UI contracts only. No actual company, model inference or live data writes. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const python = path.resolve('.venv/Scripts/python.exe');
const py = (code, input) => JSON.parse(execFileSync(python, ['-c', code], { cwd: path.resolve('.'), input: JSON.stringify(input), encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }));
const fixture = py("import json; from service.research_schema import SCHEMAS,get_model_schema,get_model_example; from service.research_models import evaluate_model; print(json.dumps({k:{'schema':get_model_schema(k),'synthetic_example':get_model_example(k),'result':evaluate_model(k,get_model_example(k))} for k in SCHEMAS},ensure_ascii=False))", null);
const evidence = [{ kind: 'source', id: 'source-1', locator: 'p1', quote: '这是受控界面测试使用的合成资料。' }];
fixture.dcf.synthetic_example.input_basis['base.revenue'] = { basis: 'disclosed', rationale: '受控界面夹具中的披露标签，用于检验手改后的性质变化。' };
fixture.dcf.synthetic_example.source_refs['base.revenue'] = evidence;
delete fixture.dcf.synthetic_example.input_basis['shares.count'];
const now = '2026-10-04T10:00:00.000Z';
const source = { source_id: 'source-1', title: '合成公司的研究来源（界面测试）', url: 'https://example.org/source', published_at: '2026-01-01', retrieved_at: now, sha256: '1'.repeat(64), paragraphs: [{ id: 'p1', text: '这是受控界面测试使用的合成资料。所有数值均为演示，不是公司事实。' }, { id: 'p2', text: '传导率和弹性是明确的研究假设，不是已披露数据。' }] };
const common = { created_at: now, dependencies: evidence, dependency_status: 'current', changed_dependencies: [] };
let artifacts = [
  { ...common, id: 'model-1', revision_id: 'revision-1', kind: 'dcf', title: '合成企业 DCF', spec: fixture.dcf.synthetic_example, result: fixture.dcf.result, dependency_status: 'stale', changed_dependencies: [{ kind: 'source', id: 'source-1', reason: 'changed' }] },
  { ...common, id: 'chain-1', revision_id: 'revision-chain', kind: 'industry_chain', title: '合成产业传导', content: { industry: '合成制造', as_of: '2026-10-04', nodes: [{ id: 'raw', label: '原材料', role: 'upstream' }, { id: 'firm', label: '制造企业', role: 'company' }, { id: 'buyers', label: '采购客户', role: 'downstream' }], edges: [{ from: 'raw', to: 'firm', mechanism: '成本变化在价格调整前影响利润。', direction: 'conditional', evidence, assumptions: [{ name: '传导率', value: '0.5', unit: '小数比率', basis: 'analyst_assumption', rationale: '合成测试假设' }] }], claims: [{ id: 'c1', text: '敞口为研究假设。', type: 'assumption', evidence }], scenario_model_id: 'model-1' } },
  { ...common, id: 'memo-1', revision_id: 'revision-memo', kind: 'investment_memo', title: '合成企业投资备忘录', content: { company: '合成企业', as_of: '2026-10-04', thesis: '经营现金流必须与增长假设一致。', claims: [{ id: 'c2', type: 'fact', text: '该文件标明是合成数据。', evidence }], catalysts: ['合成催化因素'], risks: ['需求假设可能不成立'], falsification_conditions: [{ indicator: '经营利润率', condition: '低于假设区间', horizon: '两个财年', action: '重做估值' }], conclusion: '演示结论，不构成实际公司分析。', valuation_artifact_id: 'model-1' } },
  { ...common, id: 'correction-1', revision_id: 'revision-correction', kind: 'report_correction', title: '合成报告纠错', content: { original_text: '增速为20%。', revised_text: '增速为10%。', issues: [{ id: 'i1', start: 3, end: 5, original: '20', replacement: '10', category: 'formula', reason: '公式核算结果与原文不符。', evidence }], verified_claims: [] } },
];
const checked = []; const requests = []; const exportsRequested = []; let interceptedApiRequests = 0;
const check = name => { checked.push({ name, status: 'passed', evidence: 'controlled browser API fixtures + deterministic synthetic calculator' }); console.log('PASS', name); };
const output = path.resolve('web/test-results'); fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1512, height: 1100 }, acceptDownloads: true, serviceWorkers: 'block' });
  const page = await context.newPage(); const errors = []; page.on('pageerror', error => errors.push(error.message));
  await context.route('**/api/**', async route => {
    interceptedApiRequests++;
    const request = route.request(), url = new URL(request.url()), uri = url.pathname;
    const respond = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (uri === '/api/projects') return respond({ projects: [{ id: 'synthetic-project', name: '研究交互测试（合成数据）' }] });
    if (uri === '/api/settings') return respond({ llm: { model: 'configured-model', hasKey: true }, runtime: {}, ocr: {}, embedding: {}, search: {} });
    if (uri === '/api/health') return respond({ status: 'ok' });
    if (uri.endsWith('/conversations')) return respond({ conversations: [] });
    if (uri.endsWith('/documents')) return respond({ documents: [] });
    if (uri.endsWith('/research/sources')) return respond({ sources: [source] });
    if (uri.endsWith('/research/sources/source-1')) return respond(source);
    if (uri.endsWith('/research/artifacts')) return respond({ artifacts });
    if (uri.includes('/models/schema/')) return respond(fixture[uri.split('/').at(-1)]);
    if (uri.endsWith('/research/models') && request.method() === 'POST') {
      const input = request.postDataJSON(); requests.push(input);
      if (input.artifact_id && artifacts.find(a => a.id === input.artifact_id)?.revision_id !== input.parent_revision_id) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ message: '该成果已有新版本，请刷新后再修改' }) });
      let result;
      try { result = py("import json,sys; from service.research_models import evaluate_model; v=json.load(sys.stdin); print(json.dumps(evaluate_model(v['kind'],v['spec']),ensure_ascii=False))", input); }
      catch { return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ message: 'discount/terminal: require WACC > 0 and 0 <= terminal growth < WACC' }) }); }
      const item = { ...common, id: input.artifact_id || 'new-model', revision_id: `revision-${requests.length + 1}`, parent_revision_id: input.parent_revision_id, title: input.title, kind: input.kind, spec: input.spec, result, dependencies: input.dependencies };
      artifacts = [...artifacts.filter(a => a.id !== item.id), item]; return respond(item);
    }
    if (uri.includes('/research/artifacts/')) {
      const id = uri.split('/research/artifacts/')[1].split('/')[0]; const item = artifacts.find(a => a.id === id);
      if (uri.endsWith('/export')) { exportsRequested.push(url.search); return route.fulfill({ contentType: url.searchParams.get('format') === 'csv' ? 'text/csv' : 'application/json', headers: { 'Content-Disposition': 'attachment; filename="research-export.csv"' }, body: 'year,fcff\n2025,150\n' }); }
      return respond(item);
    }
    return respond({});
  });
  try {
    await page.goto(process.env.WEB_TEST_URL || 'http://127.0.0.1:3001/');
    await page.getByRole('button', { name: '研究成果', exact: true }).click();
    await page.getByRole('heading', { name: source.title }).click();
    await page.getByRole('dialog', { name: '研究来源原文' }).waitFor();
    await page.getByText(source.paragraphs[0].text, { exact: true }).waitFor();
    assert.equal(await page.getByRole('link', { name: '原始网址' }).getAttribute('href'), source.url);
    assert.equal(await page.getByRole('link', { name: '下载原始快照' }).getAttribute('href'), '/api/projects/synthetic-project/research/sources/source-1/raw');
    await page.getByRole('button', { name: '关闭来源原文' }).click(); check('来源原文、段落、原始网址与下载入口');
    source.content_representation = 'provider_extracted_text';
    await page.getByRole('heading', { name: source.title }).click();
    await page.getByText('网页正文（由读取服务提取）', { exact: true }).waitFor();
    assert.equal(await page.getByRole('link', { name: '下载正文快照' }).getAttribute('href'), '/api/projects/synthetic-project/research/sources/source-1/raw');
    assert.equal(await page.getByRole('link', { name: '下载原始快照' }).count(), 0);
    await page.getByRole('button', { name: '关闭来源原文' }).click(); check('服务提取正文明确区分原始快照');
    source.content_representation = 'original_response_bytes';

    await page.getByRole('button', { name: /估值与分析/ }).click();
    await page.getByRole('button', { name: /合成企业 DCF/ }).click();
    await page.getByText('该成果依赖的资料已有变化', { exact: true }).waitFor();
    const revenueBasis = page.locator('[data-input-path="base.revenue"]');
    await revenueBasis.getByText('披露值', { exact: true }).waitFor();
    await page.locator('[data-input-path="shares.count"]').getByText('未注明', { exact: true }).waitFor();
    await revenueBasis.getByRole('button', { name: '来源 · p1' }).click();
    await page.locator('.rw-source-highlight').filter({ hasText: source.paragraphs[0].text }).waitFor();
    await page.getByRole('button', { name: '关闭来源原文' }).click();
    await page.getByRole('textbox', { name: 'base.revenue', exact: true }).fill('1001');
    await revenueBasis.getByText('研究假设', { exact: true }).waitFor();
    await revenueBasis.getByText(/在界面中修改/).waitFor();
    await page.getByRole('textbox', { name: 'base.revenue', exact: true }).fill('1000');
    await revenueBasis.getByText('研究假设', { exact: true }).waitFor();
    await page.getByText('DCF 价值时点：2024 年 12 月 31 日（基年年末）', { exact: true }).first().waitFor();
    await page.locator('.rw-parameter-basis').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'research-parameter-basis-desktop.png'), fullPage: true });
    check('逐参数依据、原文入口、未注明状态与手改后假设性质');
    assert.equal(await page.getByRole('textbox', { name: 'discount.wacc', exact: true }).inputValue(), '0.1');
    await page.getByRole('textbox', { name: 'forecast.0.ebit_margin', exact: true }).fill('0.25');
    await page.getByText('未保存的修改', { exact: true }).waitFor();
    await page.getByRole('button', { name: '重算并保存新版本', exact: true }).click();
    await page.getByText('已完成重算并保存新版本；原版本保留。', { exact: true }).waitFor();
    assert.equal(requests[0].artifact_id, 'model-1'); assert.equal(requests[0].parent_revision_id, 'revision-1');
    assert.equal(requests[0].spec.forecast[0].ebit_margin, '0.25');
    assert.equal(requests[0].spec.input_basis['base.revenue'].basis, 'assumption');
    assert.equal(requests[0].spec.source_refs['base.revenue'][0].locator, 'p1');
    assert.equal(requests[0].dependencies[0].id, 'source-1'); check('参数表编辑、依赖保留、乐观版本链与确定性重算');

    await page.getByRole('img', { name: '自由现金流 FCFF趋势图' }).waitFor();
    await page.getByRole('combobox', { name: '选择图表纵轴' }).selectOption('revenue');
    await page.getByRole('img', { name: '营业收入趋势图' }).waitFor();
    const csvUrl = await page.getByRole('link', { name: '导出本表 CSV' }).getAttribute('href');
    const csvBody = await page.evaluate(async url => (await fetch(url)).text(), csvUrl);
    assert.equal(csvBody, 'year,fcff\n2025,150\n');
    assert(exportsRequested.at(-1).includes('revision=revision-2'));
    check('计算表、可切换纵轴的趋势图、敏感性与 CSV 链接响应');
    await page.locator('.research-workspace').evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: path.join(output, 'research-model-desktop.png'), fullPage: true });

    await page.getByRole('textbox', { name: 'discount.wacc', exact: true }).fill('0');
    await page.getByRole('button', { name: '重算并保存新版本', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'WACC' }).waitFor();
    assert.equal(artifacts.find(a => a.id === 'model-1').revision_id, 'revision-2');
    await page.getByRole('textbox', { name: 'discount.wacc', exact: true }).fill('0.1'); check('非法假设显示实际错误，不覆盖已保存结果');

    await page.getByRole('combobox', { name: '新模型类型' }).selectOption('comparables');
    await page.getByRole('button', { name: '载入合成示例' }).click();
    await page.getByRole('textbox', { name: 'subject.earnings', exact: true }).waitFor();
    await page.getByRole('combobox', { name: 'method', exact: true }).selectOption('ev_ebitda');
    assert.equal(await page.getByRole('textbox', { name: 'subject.ebitda', exact: true }).inputValue(), '');
    assert.equal(await page.getByRole('textbox', { name: 'peers.0.multiple', exact: true }).inputValue(), '');
    await page.getByRole('textbox', { name: 'subject.bridge.net_debt', exact: true }).waitFor(); check('切换 P/E 与 EV/EBITDA 不混用分母和旧倍数');

    await page.getByRole('button', { name: /^产业链/ }).click();
    await page.getByRole('button', { name: /合成产业传导/ }).click();
    await page.getByText('成本变化在价格调整前影响利润。', { exact: true }).waitFor();
    await page.getByRole('button', { name: '来源 · p1' }).first().click();
    await page.getByRole('dialog', { name: '研究来源原文' }).waitFor();
    await page.locator('.rw-source-highlight').filter({ hasText: source.paragraphs[0].text }).waitFor();
    await page.getByRole('button', { name: '关闭来源原文' }).click(); check('产业链关系、参数性质与原文证据');
    await page.screenshot({ path: path.join(output, 'research-chain-desktop.png'), fullPage: true });

    await page.getByRole('button', { name: /备忘录与纠错/ }).click();
    await page.getByRole('button', { name: /合成企业投资备忘录/ }).click();
    await page.getByRole('heading', { name: '什么情况会推翻判断' }).waitFor();
    await page.getByText('低于假设区间', { exact: true }).waitFor();
    await page.getByRole('button', { name: /合成报告纠错/ }).click();
    await page.getByText('增速为20%。', { exact: true }).waitFor();
    await page.getByText('增速为10%。', { exact: true }).waitFor();
    await page.getByText('公式核算结果与原文不符。', { exact: true }).waitFor(); check('备忘录证伪条件与纠错原文、修订、证据');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.research-workspace').evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: path.join(output, 'research-mobile.png'), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile document must not overflow');
    check('移动布局无整页横向溢出');
    await page.setViewportSize({ width: 1512, height: 1100 });
    await page.getByRole('button', { name: /估值与分析/ }).click();
    await page.getByRole('button', { name: /合成企业 DCF/ }).click();
    const oldRevision = artifacts.find(a => a.id === 'model-1').revision_id;
    artifacts = artifacts.map(a => a.id === 'model-1' ? { ...a, revision_id: 'revision-concurrent', parent_revision_id: oldRevision } : a);
    await page.getByRole('button', { name: '刷新', exact: true }).click();
    await page.getByText('其他会话已保存更新版本', { exact: true }).waitFor();
    assert((await page.getByRole('link', { name: '完整模型 JSON' }).getAttribute('href')).includes(`revision=${oldRevision}`));
    await page.getByRole('button', { name: '重算并保存新版本', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: '该成果已有新版本' }).waitFor();
    await page.getByRole('button', { name: '载入最新版本', exact: true }).click();
    await page.getByText('其他会话已保存更新版本', { exact: true }).waitFor({ state: 'hidden' });
    check('并行会话更新提示、旧版定向导出与冲突拒绝');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.rw-parameter-basis').scrollIntoViewIfNeeded();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.screenshot({ path: path.join(output, 'research-parameter-basis-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []); check('无浏览器运行错误');
    fs.writeFileSync(path.join(output, 'research-contract.json'), JSON.stringify({ mode: 'controlled_ui_fixture_only', passed: checked.length, checks: checked, real_model_calls: 0, intercepted_api_requests: interceptedApiRequests, network_policy: 'All /api routes fulfilled by fixture, including unknown paths; service workers blocked; no route.continue to API' }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

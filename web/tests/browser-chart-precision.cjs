/* Browser regression with isolated fixtures: no live data writes or model calls. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:5174';
const output = path.resolve('web/test-results');
const project = { id: 'precision', name: '财报精度与单位验收', documentCount: 1 };
const doc = { id: 'report', document_id: 'report', name: '原文精度测试.pdf', original_name: '原文精度测试.pdf', status: 'ready', state: 'ready', pageCount: 140 };
const fact = (id, metric, label, value, raw, scale, other = {}) => ({ fact_id: id, document_id: 'report', metric, label, statement: 'income', company: '贵州茅台酒股份有限公司', period: '2024-FY', scope: 'consolidated_CAS', currency: 'CNY', normalized_unit: 'CNY', value, raw_value: raw, raw_unit: scale === '10000' ? '万元' : '元', version: 'original', dimensions: {}, source_ref: { document_id: 'report', page: id === 'exact' ? 90 : 5, table_id: 'table-' + id, row: 2, column: 2, normalization: { scale } }, ...other });
const facts = [
  fact('rounded', 'revenue', '营业收入', '170899152300', '17089915.23', '10000'),
  fact('exact', 'revenue', '营业收入', '170899152276.34', '170,899,152,276.34', '1'),
  fact('payout', 'cash_dividend_per_ten_shares', '每10股现金分红', '276.24', '276.24', '1', { currency: 'CNY/10shares', normalized_unit: 'CNY/10shares', raw_unit: '元/10股', statement: 'ratios' }),
  fact('conflict1', 'other_income', '其他收益', '100.00', '100.00', '1'),
  fact('conflict2', 'other_income', '其他收益', '101.00', '101.00', '1'),
];
const catalog = { database_path: 'fixture/finance.sqlite', documents_path: 'fixture/documents', index_path: 'fixture/catalog.yaml', counts: { documents: 1, pages: 140, tables: 5, facts: facts.length }, companies: [facts[0].company], periods: ['2024-FY'], scopes: ['consolidated_CAS'], currencies: ['CNY', 'CNY/10shares'], metrics: [...new Map(facts.map(f => [f.metric, { metric: f.metric, label: f.label, statement: f.statement }])).values()] };
const settings = { llm: { baseUrl: 'https://api.deepseek.com', model: 'deepseek-flash', hasKey: true }, embedding: { enabled: false }, ocr: { mode: 'local' }, runtime: { maxToolCalls: 24 } };
const chats = ['年度财报清洗', '分红分析'].map((title, i) => ({ id: 'chat-' + i, projectId: project.id, title, messages: [{ id: 'message-' + i, role: 'user', content: title }] }));
const checks = [], mutations = [], errors = [], sourceReads = [];
const check = name => { checks.push({ name, passed: true }); console.log('PASS', name); };
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), uri = url.pathname;
    const json = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (!['GET', 'HEAD'].includes(req.method())) { mutations.push(req.method() + ' ' + uri); return route.abort(); }
    if (uri === '/api/health') return json({ ok: true });
    if (uri === '/api/settings') return json(settings);
    if (uri === '/api/projects') return json({ projects: [project] });
    if (uri.endsWith('/conversations')) return json({ conversations: chats });
    if (uri.startsWith('/api/conversations/')) return json(chats.find(c => uri.endsWith(c.id)));
    if (uri.endsWith('/documents')) return json({ documents: [doc] });
    if (uri.endsWith('/dashboard')) return json({ documents: [doc], facts, catalog, total: facts.length });
    if (uri.endsWith('/financial-data')) {
      const filters = JSON.parse(url.searchParams.get('filters') || '{}');
      const items = facts.filter(f => Object.entries(filters).every(([key, value]) => key === 'metrics' ? value.includes(f.metric) : f[key] === value));
      return json({ items, total: items.length, limit: 5000, offset: 0 });
    }
    if (/\/documents\/report\/pages\/\d+$/.test(uri)) { sourceReads.push(uri); return json({ text: uri.endsWith('/90') ? '第90页原文：营业收入 170,899,152,276.34 元。' : '第5页原文：营业收入 17,089,915.23 万元。' }); }
    if (uri.endsWith('/tables')) return json({ items: [] });
    if (uri.endsWith('/documents/report')) return json(doc);
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Unmatched isolated fixture: ' + uri } }) });
  });
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    await page.waitForFunction(() => document.querySelectorAll('.chat-item').length === 2);
    assert.equal(await page.locator('.chat-item').count(), 2);
    await page.locator('.chat-item').filter({ hasText: '分红分析' }).click();
    await page.getByRole('log').getByText('分红分析', { exact: true }).waitFor();
    await page.locator('.chat-item').filter({ hasText: '年度财报清洗' }).click();
    await page.getByRole('log').getByText('年度财报清洗', { exact: true }).waitFor();
    check('侧边栏显示独立会话，切换读取各自历史');
    await page.getByRole('button', { name: '财报看板', exact: true }).click();
    await page.locator('.financial-chart-wrap rect[role=button]').waitFor();
    assert.equal(await page.locator('.financial-chart-wrap rect[role=button]').count(), 1);
    await page.getByText('同口径披露存在舍入差异，图表采用更精确的原值；全部来源保留在明细中。', { exact: true }).waitFor();
    assert.equal(await page.locator('.dashboard-data tbody tr').count(), 2);
    await page.locator('.financial-chart-wrap rect[role=button]').click();
    await page.locator('.selected-fact b').getByText('170,899,152,276.34', { exact: false }).waitFor();
    check('万元舍入与元级精确披露共存时只绘一个点，采用元级原值且保留两条明细');
    await page.locator('.selected-fact').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'workbench-precision-exact.png') });
    await page.getByRole('button', { name: '查看原文', exact: true }).click();
    await page.locator('.page-text').getByText(/第90页原文/).waitFor();
    assert.ok(sourceReads.some(uri => uri.endsWith('/90')));
    await page.getByLabel('关闭附件流向').click();
    check('精确图点定位到精确来源第90页，而非舍入披露页');
    await page.getByLabel('纵轴指标 1').selectOption('other_income');
    await page.getByText(/同一横轴位置存在不同数值/).waitFor();
    assert.equal(await page.getByRole('button', { name: 'PNG', exact: true }).isEnabled(), false);
    assert.equal(await page.locator('.dashboard-data tbody tr').count(), 2);
    check('同精度冲突值不会被合并或导出为单点，原明细保留');
    await page.getByLabel('纵轴指标 1').selectOption('cash_dividend_per_ten_shares');
    await page.locator('.financial-chart-wrap rect[role=button]').waitFor();
    assert.equal(await page.getByLabel('币种', { exact: true }).locator('option[value="CNY/10shares"]').textContent(), '人民币 / 10 股');
    await page.locator('.chart-title').getByText(/人民币 \/ 10 股/).waitFor();
    await page.locator('.financial-chart-wrap rect[role=button]').click();
    await page.locator('.selected-fact b').getByText('276.24', { exact: false }).waitFor();
    assert.ok(!(await page.locator('.selected-fact b').innerText()).includes('27.624'));
    check('CNY/10shares 显示人民币 / 10 股，276.24保持原分母数值');
    const download = page.waitForEvent('download'); await page.getByRole('button', { name: 'SVG', exact: true }).click();
    const svgPath = path.join(output, 'workbench-per-ten-shares.svg'); await (await download).saveAs(svgPath);
    const svgText = fs.readFileSync(svgPath, 'utf8'); assert.match(svgText, /人民币 \/ 10 股/); assert.match(svgText, /276.24/);
    await page.screenshot({ path: path.join(output, 'workbench-per-ten-shares.png') });
    check('每10股 SVG 导出保存相同单位、金额和指标名');
    await page.getByRole('button', { name: '在对话中添加财报', exact: true }).click();
    await page.getByLabel('发送给金融 Agent 的消息').waitFor();
    await page.getByRole('button', { name: 'API 配置', exact: true }).click();
    await page.getByText(/DeepSeek 通过 Pi/).waitFor();
    assert.equal(await page.locator('#llm-key').inputValue(), '');
    await page.screenshot({ path: path.join(output, 'workbench-precision-api-entry.png') });
    check('看板可进入对话，API设置入口可见且不显示密钥');
    assert.deepEqual(errors, []); assert.deepEqual(mutations, []);
    check('隔离浏览器验收无模型调用、生产写入或页面异常');
    fs.writeFileSync(path.join(output, 'browser-chart-precision-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Isolated HTTP fixtures; browser behavior only, not live model accuracy.', passed: checks.length, checks, mutations, errors }, null, 2));
  } catch (error) { await page.screenshot({ path: path.join(output, 'workbench-precision-failure.png') }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

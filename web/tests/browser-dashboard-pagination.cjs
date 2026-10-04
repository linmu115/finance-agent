/* Regression: catalog metrics and chart data must not be limited to the first 5,000 rows. */
const { chromium } = require('playwright'); const assert = require('node:assert/strict'); const fs = require('node:fs'); const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001'; const out = path.resolve('web/test-results'); const requests = [];
const make = (id, metric, period, value) => ({ fact_id: id, document_id: 'report', company: '跨分页测试公司', metric, label: metric === 'revenue' ? '营业收入' : '后续页才出现的指标', statement: 'income', period, scope: 'consolidated_CAS', currency: 'CNY', normalized_unit: 'CNY', value: String(value), dimensions: {}, version: 'original' });
const initial = Array.from({ length: 5000 }, (_, i) => make(`initial-${i}`, 'revenue', '2024-FY', 100));
const tail = Array.from({ length: 6001 }, (_, i) => make(`tail-${i}`, 'tail_metric', i === 6000 ? '2025-FY' : '2024-FY', i === 6000 ? 777 : 111));
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true }); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url()); const uri = url.pathname; const json = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (uri === '/api/projects') return json({ projects: [{ id: 'p', name: '跨分页测试', documentCount: 1 }] });
    if (uri === '/api/health') return json({ ok: true });
    if (uri === '/api/settings') return json({ llm: { model: 'fixture', baseUrl: '', provider: 'openai-compatible' }, embedding: { enabled: false }, ocr: { mode: 'local' }, runtime: { maxToolCalls: 24, timeoutSeconds: 120 } });
    if (uri.endsWith('/conversations')) return json({ conversations: [] });
    if (uri.endsWith('/documents')) return json({ documents: [] });
    if (uri.endsWith('/dashboard')) return json({ documents: [], facts: initial, total: 11001, truncated: true, catalog: { counts: { documents: 1, pages: 300, tables: 100, facts: 11001 }, companies: ['跨分页测试公司'], periods: ['2024-FY', '2025-FY'], scopes: ['consolidated_CAS'], currencies: ['CNY'], metrics: [{ metric: 'revenue', label: '营业收入', statement: 'income' }, { metric: 'tail_metric', label: '后续页才出现的指标', statement: 'income' }] } });
    if (uri.endsWith('/financial-data')) {
      const filters = JSON.parse(url.searchParams.get('filters') || '{}'), offset = Number(url.searchParams.get('offset') || 0);
      requests.push({ filters, offset }); const source = filters.metrics?.includes('tail_metric') ? tail : initial;
      // Server may return less than requested; client must advance by actual rows.
      return json({ items: source.slice(offset, offset + 1000), total: source.length, limit: 1000, offset });
    }
    return json({});
  });
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor(); await page.getByRole('button', { name: '财报看板', exact: true }).click();
    await page.getByLabel('纵轴指标 1').selectOption('tail_metric');
    await page.getByRole('button', { name: /后续页才出现的指标.*2025-FY.*777/ }).waitFor();
    assert.ok(requests.filter(item => item.filters.metrics?.includes('tail_metric')).every(item => item.filters.metrics.length === 1));
    assert.ok(requests.some(item => item.filters.metrics?.includes('tail_metric') && item.offset === 6000));
    assert.equal(await page.locator('.financial-chart-wrap rect[role=button]').count(), 2);
    await page.locator('.data-pagination').getByText('1–30 / 6001', { exact: true }).waitFor(); assert.deepEqual(errors, []);
    await page.screenshot({ path: path.join(out, 'workbench-pagination.png') });
    const report = { checkedAt: new Date().toISOString(), passed: 1, scope: 'Controlled browser regression, not real model evidence.', checks: [{ name: '指标从完整目录发现；服务端按指标筛选；完整获取超过 5000 条的全部分页；第 6001 条参与图表', passed: true }], totalSelectedFacts: tail.length, pageOffsets: [...new Set(requests.filter(item => item.filters.metrics?.includes('tail_metric')).map(item => item.offset))], pageErrors: errors };
    fs.writeFileSync(path.join(out, 'browser-dashboard-pagination-results.json'), JSON.stringify(report, null, 2)); console.log('PASS 跨分页指标发现、服务器筛选、6001条完整读取与制图');
  } catch (error) { await page.screenshot({ path: path.join(out, 'workbench-pagination-failure.png') }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

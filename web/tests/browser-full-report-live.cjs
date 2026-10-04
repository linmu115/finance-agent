const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Read-only verification of the complete annual-report project. No model calls. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001';
const projectId = process.env.WORKBENCH_LIVE_PROJECT || '3b4c43c9-51b8-432c-807d-2a15323f7a80';
const expectedFacts = Number(process.env.WORKBENCH_EXPECTED_FACTS || 3298);
const output = path.resolve('web/test-results');
const checks = [], errors = [], mutations = [], financialRequests = [], sourceRequests = [];
const report = { checkedAt: new Date().toISOString(), projectId, scope: 'Read-only UI/API verification of persisted full-report data; no model calls, not a claim of correctness for every extracted fact.' };
const check = (name, detail) => { checks.push({ name, passed: true, ...(detail ? { detail } : {}) }); console.log('PASS', name); };
function csvRows(text) {
  const rows = []; let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') { if (quoted && text[i + 1] === '"') { field += '"'; i++; } else quoted = !quoted; }
    else if (c === ',' && !quoted) { row.push(field); field = ''; }
    else if ((c === '\n' || c === '\r') && !quoted) { if (c === '\r' && text[i + 1] === '\n') i++; row.push(field); rows.push(row); row = []; field = ''; }
    else field += c;
  }
  assert.equal(quoted, false, 'CSV quotes must close');
  if (row.length || field) { row.push(field); rows.push(row); }
  if (rows.length) rows[0][0] = rows[0][0].replace(/^\uFEFF/, '');
  return rows;
}
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', route => {
    const req = route.request(), url = new URL(req.url());
    if (!['GET', 'HEAD'].includes(req.method())) { mutations.push(req.method() + ' ' + url.pathname); return route.abort(); }
    if (url.pathname.endsWith('/financial-data')) financialRequests.push({ project: url.pathname.split('/')[3], offset: Number(url.searchParams.get('offset') || 0), filters: JSON.parse(url.searchParams.get('filters') || '{}') });
    if (/\/pages\/\d+$/.test(url.pathname)) sourceRequests.push(url.pathname);
    return route.continue();
  });
  async function get(endpoint) {
    const result = await context.request.get(base + endpoint);
    assert.equal(result.status(), 200, endpoint + ' should return HTTP 200');
    return result.json();
  }
  async function allFacts(filters = {}) {
    const items = [], limits = []; let total;
    do {
      const data = await get(`/api/projects/${projectId}/financial-data?limit=5000&offset=${items.length}&filters=${encodeURIComponent(JSON.stringify(filters))}`);
      assert.ok(data.items.length <= 200, 'API page cap must be respected');
      if (total !== undefined) assert.equal(data.total, total, 'Data changed during readonly pagination');
      total = data.total; limits.push(data.items.length);
      assert.ok(data.items.length || items.length >= total, 'Pagination stopped before all records were received');
      items.push(...data.items);
    } while (items.length < total);
    assert.equal(items.length, total); assert.equal(new Set(items.map(item => item.fact_id)).size, total);
    return { items, total, pages: limits.length, sizes: limits };
  }
  async function waitTable(items, pageNumber, total) {
    const wanted = items.map(f => ({ label: f.label || f.metric, company: f.company, period: f.period, value: f.value }));
    await page.waitForFunction(({ wanted, pageNumber, total }) => {
      const rows = [...document.querySelectorAll('.dashboard-data tbody tr')].map(row => ({
        label: row.querySelector('.data-label b')?.textContent, company: row.querySelector('.data-label small')?.textContent,
        period: row.children[1]?.textContent, value: row.querySelector('.numeric')?.getAttribute('title'),
      }));
      const pagination = document.querySelector('.data-pagination span')?.textContent || '';
      return JSON.stringify(rows) === JSON.stringify(wanted) && pagination.includes(`/ ${total}`)
        && pagination.startsWith(String(pageNumber * 30 + 1) + '–');
    }, { wanted, pageNumber, total });
  }
  try {
    const dashboard = await get(`/api/projects/${projectId}/dashboard`);
    report.counts = dashboard.catalog.counts;
    assert.equal(dashboard.catalog.counts.pages, 143);
    assert.equal(dashboard.catalog.counts.facts, expectedFacts);
    assert.equal(dashboard.documents.length, 1);
    assert.ok(dashboard.facts.length <= 200); assert.equal(dashboard.truncated, true);
    check('完整年报项目为143页，概览200条分页窗口与全库事实总数一致', report.counts);
    const full = await allFacts(); report.apiPagination = { pages: full.pages, sizes: full.sizes, total: full.total };
    assert.equal(full.total, expectedFacts);
    assert.ok(full.items.every(f => f.normalization_engine === 'LangExtract'));
    check('逐页读取全部事实，无遗漏、重复或机械清洗记录', { pages: full.pages, records: full.total });

    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    await chooseProject(page, projectId);
    await page.getByRole('button', { name: '财报看板', exact: true }).click();
    await page.getByRole('heading', { name: '财报看板', exact: true }).waitFor();
    const expectedIds = [...new Set(dashboard.catalog.metrics.map(metric => metric.metric))].sort();
    await page.waitForFunction(n => document.querySelectorAll('select[aria-label="纵轴指标 1"] option').length === n, expectedIds.length);
    const actualIds = await page.getByLabel('纵轴指标 1').locator('option').evaluateAll(options => options.map(option => option.value).sort());
    assert.deepEqual(actualIds, expectedIds);
    assert.ok(expectedIds.length > 100);
    report.metricCount = expectedIds.length;
    check('纵轴动态指标选项覆盖全项目目录，包含概览200条以外的指标', { metrics: expectedIds.length });

    const frequency = new Map(); for (const fact of full.items) frequency.set(fact.metric, (frequency.get(fact.metric) || 0) + 1);
    const top = [...frequency].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([metric]) => metric);
    await page.getByLabel('纵轴指标 1').selectOption(top[0]);
    for (let i = 1; i < top.length; i++) { await page.getByRole('button', { name: '+ 添加指标', exact: true }).click(); await page.getByLabel('纵轴指标 ' + (i + 1)).selectOption(top[i]); }
    const selected = await allFacts({ metrics: top });
    let uiPages = 0;
    for (let offset = 0; offset < selected.total; offset += 30) {
      const pageNumber = offset / 30; await waitTable(selected.items.slice(offset, offset + 30), pageNumber, selected.total); uiPages++;
      if (offset + 30 < selected.total) await page.getByRole('button', { name: '下一页', exact: true }).click();
    }
    assert.equal(await page.getByRole('button', { name: '下一页', exact: true }).isEnabled(), false);
    if (selected.total > 200) assert.ok(financialRequests.some(req => req.project === projectId && req.offset > 0 && top.every(metric => req.filters.metrics?.includes(metric))));
    report.uiPagination = { selectedMetrics: top, records: selected.total, uiPages, apiPages: selected.pages };
    await page.screenshot({ path: path.join(output, 'full-report-pagination.png') });
    check('三项高频指标明细逐页核对至最后一页，值与顺序均吻合API', report.uiPagination);

    for (let i = top.length; i >= 2; i--) await page.getByLabel('移除指标 ' + i).click();
    await page.getByRole('button', { name: '利润表', exact: true }).click();
    await page.getByLabel('纵轴指标 1').selectOption('revenue');
    const company = '贵州茅台酒股份有限公司';
    await page.getByLabel('公司', { exact: true }).selectOption(company);
    await page.getByLabel('币种', { exact: true }).selectOption('CNY');
    await page.getByLabel('期间类型', { exact: true }).selectOption('annual');
    await page.getByLabel('会计口径', { exact: true }).selectOption('consolidated_CAS');
    await page.getByLabel('数据版本', { exact: true }).selectOption('original');
    const filters = { statement: 'income', company, currency: 'CNY', periods: dashboard.catalog.periods.filter(period => /FY|^\d{4}$/.test(period)), scope: 'consolidated_CAS', version: 'original', metrics: ['revenue'] };
    const annual = await allFacts(filters);
    assert.ok(annual.items.some(item => item.value === '170899152276.34'), 'Exact 2024 annual revenue must remain queryable');
    await waitTable(annual.items.slice(0, 30), 0, annual.total);
    await page.waitForFunction(() => !document.querySelector('.chart-empty')?.textContent.includes('正在读取'));
    const issue = await page.locator('.chart-empty').textContent().catch(() => null);
    assert.equal(issue, null, 'Annual-revenue chart is blocked: ' + issue);
    await page.locator('.financial-chart-wrap svg').waitFor();
    assert.ok(await page.locator('.financial-chart-wrap rect[role=button]').count() >= 2);
    const target = page.locator('.financial-chart-wrap rect[role=button]').filter({ has: page.locator('title').filter({ hasText: '170,899,152,276.34' }) }).first();
    await target.click(); await page.locator('.selected-fact').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'full-report-revenue-dashboard.png') });
    check('利润表分类下完整年报年度合并营收图可用，2024采用170899152276.34精确原值', { records: annual.total });

    const pngPromise = page.waitForEvent('download'); await page.getByRole('button', { name: 'PNG', exact: true }).click();
    const pngPath = path.join(output, 'full-report-revenue-chart.png'); await (await pngPromise).saveAs(pngPath);
    assert.ok(fs.statSync(pngPath).size > 3000);
    const csvPromise = page.waitForEvent('download'); await page.getByRole('link', { name: '导出当前筛选 CSV' }).click();
    const csvPath = path.join(output, 'full-report-revenue-data.csv'); await (await csvPromise).saveAs(csvPath);
    const rows = csvRows(fs.readFileSync(csvPath, 'utf8')), headers = rows.shift();
    assert.equal(rows.length, annual.total);
    const exported = rows.map(row => Object.fromEntries(headers.map((header, i) => [header, row[i]])));
    assert.ok(exported.some(item => item.value === '170899152276.34'));
    assert.ok(exported.every(item => item.metric === 'revenue' && item.currency === 'CNY' && item.scope === 'consolidated_CAS' && item.version === 'original' && /FY/.test(item.period)));
    check('营收PNG与CSV实际下载，CSV包含全部筛选记录及精确值', { csvRows: rows.length });

    await page.getByRole('button', { name: '查看原文', exact: true }).click();
    await page.locator('.page-text').getByText(/营业收入/).waitFor();
    assert.ok(sourceRequests.length > 0);
    const sourcePage = Number(sourceRequests[sourceRequests.length - 1].split('/').pop());
    assert.ok(sourcePage >= 1 && sourcePage <= 143);
    await page.screenshot({ path: path.join(output, 'full-report-revenue-source.png') });
    await page.getByLabel('关闭附件流向').click();
    check('图中精确营收能够打开完整PDF的实际来源页', { page: sourcePage });
    assert.deepEqual(errors, []); assert.deepEqual(mutations, []);
    check('全程GET只读，无模型调用、生产写入及浏览器异常');
    fs.writeFileSync(path.join(output, 'browser-full-report-live-results.json'), JSON.stringify({ ...report, passed: checks.length, checks, errors, mutations }, null, 2));
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'full-report-failure.png') }).catch(() => {});
    fs.writeFileSync(path.join(output, 'browser-full-report-live-failure.json'), JSON.stringify({ ...report, error: String(error.stack || error), checks, errors, mutations }, null, 2));
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

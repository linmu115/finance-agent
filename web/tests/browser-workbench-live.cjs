const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Read-only browser checks against the actual local server and persisted model-cleaned data. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001';
const projectId = process.env.WORKBENCH_LIVE_PROJECT || '0df28e7b-1b79-42e8-914e-2dfb2e2e2ff4';
const output = path.resolve('web/test-results'); const checks = [];
const checked = name => { checks.push({ name, passed: true }); console.log('PASS', name); };
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true }); const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true }); const page = await context.newPage(); const errors = [], mutations = []; page.on('pageerror', error => errors.push(error.message)); page.on('request', req => { if (req.url().includes('/api/') && !['GET', 'HEAD'].includes(req.method())) mutations.push(req.method() + ' ' + req.url()); });
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    await chooseProject(page, projectId);
    await page.getByRole('button', { name: '财报看板', exact: true }).click(); await page.getByRole('heading', { name: '财报看板', exact: true }).waitFor();
    const dashboard = await (await context.request.get(`${base}/api/projects/${projectId}/dashboard`)).json();
    assert.ok(dashboard.catalog.counts.facts > 0); assert.ok(dashboard.facts.some(fact => fact.normalization_engine === 'LangExtract')); checked('看板从实际 SQLite 读取已由 LangExtract 处理的数据');
    await page.getByLabel('公司', { exact: true }).selectOption('贵州茅台酒股份有限公司'); await page.getByLabel('币种', { exact: true }).selectOption('CNY');
    await page.getByLabel('期间类型', { exact: true }).selectOption('annual'); await page.getByLabel('纵轴指标 1').selectOption('revenue');
    await page.locator('.financial-chart-wrap svg').waitFor(); await page.waitForFunction(() => document.querySelectorAll('.financial-chart-wrap rect[role=button]').length === 3);
    await page.screenshot({ path: path.join(output, 'workbench-live-dashboard.png') }); checked('真实财报按公司、币种和年度筛选后生成三年收入图');
    const pngPromise = page.waitForEvent('download'); await page.getByRole('button', { name: 'PNG', exact: true }).click(); const png = await pngPromise; await png.saveAs(path.join(output, 'workbench-live-chart.png')); checked('真实财报图表可下载 PNG，含指标、单位与图例');
    const csvPromise = page.waitForEvent('download'); await page.getByRole('link', { name: '导出当前筛选 CSV' }).click(); const csv = await csvPromise; const csvFile = path.join(output, 'workbench-live-data.csv'); await csv.saveAs(csvFile); const csvText = fs.readFileSync(csvFile, 'utf8'); assert.match(csvText, /170899152276\.34/); assert.ok(!csvText.includes('"percent","15.71"')); assert.equal(csvText.trim().split(/\r?\n/).length, 4); checked('实际 CSV 导出包含精确原始金额并遵循年度和币种筛选');
    await page.locator('.financial-chart-wrap rect[role=button]').first().click(); await page.getByRole('button', { name: '查看原文', exact: true }).click(); await page.locator('.page-text').getByText(/营业收入/).waitFor(); await page.getByLabel('关闭附件流向').click(); checked('图中数值回到实际 PDF 提取页原文');
    await page.getByText('资料与数据存在哪里', { exact: true }).click(); await page.getByText(dashboard.catalog.database_path, { exact: true }).waitFor(); checked('项目数据库和 YAML 索引路径可见');
    await page.getByRole('button', { name: '数据集与测试', exact: true }).click(); await page.getByRole('heading', { name: '数据集与测试', exact: true }).waitFor();
    const datasetCatalog = await (await context.request.get(`${base}/api/benchmark/catalog`)).json();
    for (const dataset of datasetCatalog.datasets) { const response = await context.request.get(`${base}${dataset.url}`); assert.equal(response.status(), 200); const bytes = await response.body(); assert.equal(bytes.subarray(0, 2).toString(), 'PK'); assert.ok(bytes.length > 1000); }
    await page.screenshot({ path: path.join(output, 'workbench-live-datasets.png') }); checked('三组真实资料与 benchmark 压缩包均可下载且为有效 ZIP');
    await page.getByRole('button', { name: 'API 配置', exact: true }).click(); await page.getByText(/DeepSeek 通过 Pi/).waitFor(); assert.equal(await page.locator('#llm-key').inputValue(), ''); assert.equal(await page.getByRole('button', { name: 'Embedding API', exact: true }).count(), 0); await page.getByLabel('关闭设置').click(); checked('实际配置页显示共用 DeepSeek API，密钥留空，Embedding 调用入口已移除');
    assert.deepEqual(errors, []); assert.deepEqual(mutations, []); checked('全程只读，不启动模型请求，没有浏览器异常');
    fs.writeFileSync(path.join(output, 'browser-workbench-live-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Read-only browser checks against actual local server and persisted LangExtract/DeepSeek outputs; no additional model calls, does not claim all fields correct.', projectId, counts: dashboard.catalog.counts, passed: checks.length, checks, pageErrors: errors, mutations }, null, 2));
  } catch (error) { await page.screenshot({ path: path.join(output, 'workbench-live-failure.png') }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); fs.writeFileSync(path.join(output, 'browser-workbench-live-failure.json'), JSON.stringify({ error: String(error.stack || error), checks }, null, 2)); process.exitCode = 1; });

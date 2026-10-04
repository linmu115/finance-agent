const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Read-only filter/chart checks on the separately validated full semantic dataset. */
const { chromium } = require('playwright'); const assert = require('node:assert/strict'); const fs = require('node:fs'); const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001'; const id = process.env.WORKBENCH_LIVE_PROJECT || 'fa4bfede-5ddf-453d-93e2-b4afa1fb4092'; const out = path.resolve('web/test-results'); const checks = [];
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true }); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); const writes = [], errors = [];
  page.on('pageerror', error => errors.push(error.message)); page.on('request', req => { if (req.url().includes('/api/') && !['GET', 'HEAD'].includes(req.method())) writes.push(req.method() + ' ' + req.url()); });
  const check = name => { checks.push({ name, passed: true }); console.log('PASS', name); };
  async function choose(label, value) { await page.getByLabel(label, { exact: true }).selectOption(value); }
  async function amount(value) { await page.locator('.dashboard-data .numeric').getByText(value, { exact: true }).waitFor(); }
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor(); await chooseProject(page, id); await page.getByRole('button', { name: '财报看板', exact: true }).click();
    await choose('公司', '远帆国际股份有限公司'); await choose('会计口径', 'parent_IFRS'); await choose('币种', 'USD'); await choose('纵轴指标 1', 'operating_cash_flow');
    await amount('8125000.000'); await page.locator('.financial-chart-wrap svg').waitFor(); assert.equal(await page.getByLabel('会计口径', { exact: true }).locator('option:checked').textContent(), '母公司 · 国际准则'); check('母公司 IFRS 与美元筛选返回已验证的百万美元换算数据');
    await choose('纵轴指标 1', 'purchase_of_property_plant_and_equipment'); await amount('-2375000.000'); await page.locator('.financial-chart-wrap rect[role=button]').first().waitFor(); check('负金额按零基线绘制，保留现金流支出符号');
    await choose('公司', '星海商贸股份有限公司'); await choose('币种', 'HKD'); await choose('期间类型', 'point'); await choose('纵轴指标 1', 'assets'); await amount('86425750.00'); check('港元与时点数据筛选保持千港元转换后的金额');
    await choose('会计口径', ''); await choose('币种', 'CNY'); await choose('期间类型', 'all'); await choose('公司', '启航制造股份有限公司'); await choose('期间类型', 'interim'); await choose('纵轴指标 1', 'revenue'); await amount('12347000.0');
    assert.equal(await page.locator('.dashboard-data tbody tr').count(), 2); assert.ok(!(await page.locator('.dashboard-data tbody').textContent()).includes('2025-Q3')); check('累计 / 中期筛选将九个月累计与单季度分开');
    await choose('期间类型', 'all'); await choose('公司', '云岚设备股份有限公司'); await choose('数据版本', 'restated'); await choose('纵轴指标 1', 'revenue'); await amount('46250000'); assert.equal(await page.locator('.dashboard-data tbody tr').count(), 1); check('重述版本单独查询，不混入原披露数值');
    await choose('数据版本', ''); await choose('公司', '明川消费股份有限公司'); await choose('分部 / 维度', 'region=华东分部'); await choose('纵轴指标 1', 'revenue'); await page.locator('.financial-chart-wrap svg').waitFor();
    await page.locator('.dashboard-data tbody').getByText('region=华东分部', { exact: true }).first().waitFor(); const detail = await page.locator('.dashboard-data tbody').textContent(); assert.ok(detail.includes('华东分部')); assert.ok(!detail.includes('华南分部')); assert.ok(!detail.includes('合计')); await page.screenshot({ path: path.join(out, 'workbench-live-segment.png') }); check('分部维度筛选不会把分部数值与合计叠加');
    assert.deepEqual(writes, []); assert.deepEqual(errors, []); check('完整筛选流程无浏览器异常且没有数据写入');
    fs.writeFileSync(path.join(out, 'browser-dashboard-dimensions-live-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), projectId: id, passed: checks.length, checks, writes, errors, scope: 'Readonly UI checks of persisted full benchmark outputs; benchmark accuracy is independently reported.' }, null, 2));
  } catch (error) { await page.screenshot({ path: path.join(out, 'workbench-dimensions-failure.png') }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

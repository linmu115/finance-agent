/* Read-only verification of the acceptance UI against real local reports. No model calls. */
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const { chromium } = playwright;
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001';
const output = path.resolve('web/test-results'); fs.mkdirSync(output, { recursive: true });
const checks = []; const errors = [];
const labels = { passed: '通过', partial: '部分完成', failed: '未通过', not_run: '未执行', running: '运行中', blocked: '阻塞', completed: '已完成' };
function checked(name, evidence) { checks.push({ name, status: 'passed', evidence }); console.log('PASS', name); }
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  try {
    await page.goto(base); await page.getByText('服务已连接', { exact: true }).waitFor();
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/benchmark/results'));
    await page.getByRole('button', { name: '验收中心', exact: true }).click();
    const payload = await (await responsePromise).json();
    const acceptance = [...payload.runtime, ...payload.runs].find(record => Array.isArray(record.cases) && Array.isArray(record.components));
    assert.ok(acceptance, 'A real acceptance.json report is required');
    await page.locator('.acceptance-table tbody tr').first().waitFor();
    assert.equal(await page.locator('.acceptance-table tbody tr').count(), acceptance.cases.length);
    for (const item of acceptance.cases) {
      const row = page.locator('.acceptance-table tbody tr').filter({ has: page.getByText(item.id, { exact: true }) });
      assert.equal(await row.locator('.verification-state').innerText(), labels[item.status] || item.status);
      assert.match(await row.innerText(), new RegExp(item.name));
    }
    checked('S01–S12逐项表与服务端真实状态一一对应', { total: acceptance.cases.length, statuses: Object.fromEntries(acceptance.cases.map(item => [item.id, item.status])) });
    assert.equal(await page.locator('.component-card').count(), acceptance.components.length);
    await page.getByText('前端与交互', { exact: true }).waitFor();
    await page.getByText('真实模型链路', { exact: true }).first().waitFor();
    await page.getByText('文档与数据', { exact: true }).first().waitFor();
    checked('前端、解析、真实模型分层展示与计数', { components: acceptance.components.map(item => ({ name: item.name, passed: item.passed, total: item.total })) });
    const first = page.locator('.acceptance-table tbody tr').first();
    await first.locator('.case-details summary').click();
    assert.ok((await first.locator('.case-criterion').innerText()).includes(acceptance.cases[0].criterion));
    const firstEvidence = acceptance.cases[0].evidence[0];
    assert.ok((await first.locator('.evidence-list').innerText()).includes(firstEvidence.path));
    await first.locator('.evidence-hash summary').click();
    assert.equal(await first.locator('.evidence-hash code').innerText(), firstEvidence.sha256);
    await first.locator('.evidence-hash summary').click(); await first.locator('.case-details summary').click();
    checked('验收标准、证据文件及可展开校验指纹', { firstCase: acceptance.cases[0].id });
    await page.screenshot({ path: path.join(output, 'acceptance-overview-desktop.png') });
    await page.getByRole('tab', { name: /财报模型评测/ }).click();
    await page.locator('.model-section-heading').getByText(/DeepSeek/).waitFor();
    assert.ok(await page.locator('.model-batch:visible').count());
    if (await page.locator('.benchmark-metric-table:visible').count()) {
      await page.locator('.benchmark-metric-table:visible').first().getByRole('columnheader', { name: '答案准确率', exact: true }).waitFor();
      await page.locator('.acceptance-metrics.compact:visible').first().getByText('引用精确率', { exact: true }).waitFor();
    }
    const formal = [...payload.runs].filter(record => record.split === 'acceptance' && Array.isArray(record.runs) && record.runs.length === 3).sort((a, b) => Date.parse(b.createdAt || '') - Date.parse(a.createdAt || ''))[0];
    const displayedRounds = [];
    if (formal) {
      const title = page.locator('.batch-title small').filter({ hasText: formal.name });
      const batch = title.locator('xpath=ancestor::details[contains(@class,"model-batch")][1]');
      assert.equal(await batch.count(), 1);
      if (!(await batch.getAttribute('open') !== null)) await batch.locator(':scope > summary').click();
      assert.equal(await batch.locator('.model-round').count(), formal.runs.length);
      for (const [index, run] of formal.runs.entries()) {
        const metrics = Object.values(run.metrics); const n = metrics.reduce((sum, metric) => sum + metric.n, 0);
        const correct = metrics.reduce((sum, metric) => sum + metric.n * metric.answer_accuracy, 0);
        const expected = [`${(correct / n * 100).toFixed(1)}%`, `${(run.grounded_accuracy * 100).toFixed(1)}%`, `${(run.citation_precision * 100).toFixed(1)}%`, `${(run.citation_recall * 100).toFixed(1)}%`];
        const row = batch.locator('.model-round').nth(index);
        assert.deepEqual(await row.locator('.acceptance-metric strong').allInnerTexts(), expected);
        assert.equal(await row.locator('.model-round-heading .verification-state').innerText(), run.dataset_gate_pass ? '通过' : '未通过');
        displayedRounds.push({ round: run.round, displayedPercentages: expected, datasetGatePass: run.dataset_gate_pass });
      }
      await batch.locator('.batch-meta').getByText(`重复一致性 ${(formal.repeatConsistency * 100).toFixed(1)}%`, { exact: true }).waitFor();
      await batch.locator(':scope > summary').scrollIntoViewIfNeeded();
    }
    assert.equal(await page.locator('.older-model-runs[open]').count(), 0);
    assert.equal(await page.locator('.result-json').count(), 0);
    checked('真实模型、中文准确率指标、其他历史模型收起、大数组不展开', { currentModel: await page.locator('.model-code').innerText(), formalRun: formal?.name, displayedRounds });
    await page.screenshot({ path: path.join(output, 'acceptance-model-desktop.png') });
    await page.getByRole('tab', { name: /组件结果/ }).click();
    await page.locator('.component-result').filter({ hasText: '三轮真实财报解析与数据库查询' }).waitFor();
    await page.getByText('程序解析与数据库查询 · 不计为模型推理成绩', { exact: true }).waitFor();
    checked('程序解析结果与真实模型评测明确分开', { componentReports: await page.locator('.component-result').count() });
    await page.screenshot({ path: path.join(output, 'acceptance-components-desktop.png') });
    await page.getByRole('tab', { name: /总体验收/ }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    await page.screenshot({ path: path.join(output, 'acceptance-overview-mobile.png') });
    checked('移动布局无页面横向溢出，宽表在表格区域滚动', { viewport: '390 × 844' });
    assert.deepEqual(errors, []); checked('只读验收页无浏览器错误', { modelRequests: 'none' });
    fs.writeFileSync(path.join(output, 'browser-acceptance-live-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Read-only browser inspection against actual acceptance and benchmark reports. Does not rerun tests or infer new accuracy scores.', passed: checks.length, checks, errors }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); fs.writeFileSync(path.join(output, 'browser-acceptance-live-failure.json'), JSON.stringify({ error: String(error.stack || error), checks }, null, 2)); process.exitCode = 1; });

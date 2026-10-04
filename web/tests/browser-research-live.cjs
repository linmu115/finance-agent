/* Real local API + browser. Creates only its own explicitly synthetic QA project.
   Zero model inference. Run only after the host confirms the new deployment is ready. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.RESEARCH_QA_URL || 'http://127.0.0.1:3001';
const output = path.resolve('web/test-results'); fs.mkdirSync(output, { recursive: true });
const checks = []; const report = { mode: 'live_local_api_synthetic_project', started_at: new Date().toISOString(), real_model_calls: 0, checks };
const check = (name, detail) => { checks.push({ name, status: 'passed', ...(detail ? { detail } : {}) }); console.log('PASS', name); };
async function request(uri, body) { const response = await fetch(base + uri, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined); const value = await response.json(); if (!response.ok) throw new Error(`${response.status}: ${value.message || value.error?.message || 'API request failed'}`); return value; }
(async () => {
  let browser;
  try {
    const project = await request('/api/projects', { name: `研究功能验收（合成数据） ${new Date().toISOString().slice(0, 16)}` });
    report.project_id = project.id;
    const prefix = `/api/projects/${project.id}/research`;
    const models = {};
    for (const kind of ['dcf', 'comparables', 'manufacturing_scenario', 'financial_quality']) {
      const info = await request(`${prefix}/models/schema/${kind}`);
      assert(info.schema && info.synthetic_example);
      const artifact = await request(`${prefix}/models`, { kind, title: `合成验收 · ${kind}`, spec: info.synthetic_example, dependencies: [] });
      assert.equal(artifact.kind, kind); assert.equal(artifact.result.kind, kind); assert.equal(artifact.dependency_status, 'current');
      models[kind] = artifact;
    }
    check('四种模型经真实宿主与 Python 服务计算保存', Object.fromEntries(Object.entries(models).map(([key, value]) => [key, { id: value.id, revision: value.revision_id }])));
    assert.equal(Number(models.dcf.result.results.value_per_share), 13);
    assert.equal(Number(models.comparables.result.results.value_per_share), 14);
    assert.equal(Number(models.manufacturing_scenario.result.tables.scenario[1].scenario_ebit), 222.4);
    check('独立手算 DCF13、PE14、情景 EBIT222.4 与真实服务一致');
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1512, height: 1080 }, acceptDownloads: true });
    await context.addInitScript(id => localStorage.setItem('finance.project', id), project.id);
    const page = await context.newPage(), pageErrors = []; page.on('pageerror', error => pageErrors.push(error.message));
    await page.goto(base); await page.getByRole('button', { name: '研究成果', exact: true }).click();
    await page.getByRole('button', { name: /估值与分析/ }).click();
    await page.getByRole('button', { name: /合成验收 · dcf/ }).click();
    await page.getByRole('textbox', { name: 'discount.wacc', exact: true }).fill('0.11');
    await page.getByRole('button', { name: '重算并保存新版本', exact: true }).click();
    await page.getByText('已完成重算并保存新版本；原版本保留。', { exact: true }).waitFor();
    const revised = await request(`${prefix}/artifacts/${models.dcf.id}`);
    assert.equal(revised.parent_revision_id, models.dcf.revision_id); assert.equal(revised.spec.discount.wacc, '0.11');
    assert(Number(revised.result.results.value_per_share) < 13);
    check('浏览器参数编辑调用真实重算并保留版本链');
    const prior = await request(`${prefix}/artifacts/${models.dcf.id}?revision=${models.dcf.revision_id}`);
    assert.equal(prior.spec.discount.wacc, '0.1');
    assert.equal(Number(prior.result.results.value_per_share), 13);
    check('旧版本假设与结果仍可按 revision 读取');

    for (const [format, name] of [['csv', '导出本表 CSV'], ['json', '完整模型 JSON']]) {
      const event = page.waitForEvent('download'); await page.getByRole('link', { name }).click();
      const download = await event; assert.equal(await download.failure(), null, `${format} download failed`);
      const filename = path.join(output, `research-live-export.${format}`); await download.saveAs(filename);
      const content = fs.readFileSync(filename, 'utf8');
      if (format === 'json') { const value = JSON.parse(content); assert.equal(value.revision_id, revised.revision_id); assert.equal(value.spec.discount.wacc, '0.11'); }
      else { assert(content.includes('fcff')); assert(content.includes(String(revised.result.tables.forecast[0].fcff))); }
    }
    check('真实浏览器 CSV/JSON 下载成功且内容对应显示版本');
    await page.getByRole('combobox', { name: '选择图表纵轴' }).selectOption('revenue');
    await page.getByRole('img', { name: '营业收入趋势图' }).waitFor();
    await page.locator('.rw-results').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'research-live-results.png'), fullPage: true });
    check('真实结果趋势图与敏感性表正常渲染');

    const parallelSpec = structuredClone(revised.spec); parallelSpec.discount.wacc = '0.12';
    const parallel = await request(`${prefix}/models`, { kind: 'dcf', title: revised.title, spec: parallelSpec, artifact_id: revised.id, parent_revision_id: revised.revision_id, dependencies: [] });
    await page.getByRole('button', { name: '刷新', exact: true }).click();
    await page.getByText('其他会话已保存更新版本', { exact: true }).waitFor();
    assert((await page.getByRole('link', { name: '完整模型 JSON' }).getAttribute('href')).includes(revised.revision_id));
    const conflictResponse = page.waitForResponse(response => response.url().endsWith('/research/models') && response.request().method() === 'POST');
    await page.getByRole('button', { name: '重算并保存新版本', exact: true }).click();
    assert.equal((await conflictResponse).status(), 409);
    await page.getByRole('button', { name: '载入最新版本', exact: true }).click();
    assert.equal(await page.getByRole('textbox', { name: 'discount.wacc', exact: true }).inputValue(), '0.12');
    const current = await request(`${prefix}/artifacts/${parallel.id}`); assert.equal(current.revision_id, parallel.revision_id);
    check('真实并行更新提示、409冲突拒绝与最新版本载入');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.research-workspace').evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: path.join(output, 'research-live-mobile.png'), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(pageErrors, []);
    check('真实页面移动端无整页横向溢出、无浏览器运行错误');
    report.status = 'passed';
  } catch (error) { report.status = 'failed'; report.error = String(error); throw error; }
  finally { report.finished_at = new Date().toISOString(); fs.writeFileSync(path.join(output, 'research-live-api.json'), JSON.stringify(report, null, 2)); if (browser) await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

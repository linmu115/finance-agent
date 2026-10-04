const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Read-only active-run UI verification: no prompt submission, cancellation, or model call. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs'); const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001';
const id = process.env.WORKBENCH_LIVE_PROJECT || '3b4c43c9-51b8-432c-807d-2a15323f7a80';
const output = path.resolve('web/test-results'); const checks = [];
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true }); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); const writes = [], errors = [];
  page.on('request', req => { if (req.url().includes('/api/') && !['GET', 'HEAD'].includes(req.method())) writes.push(req.method() + ' ' + req.url()); }); page.on('pageerror', error => errors.push(error.message));
  const checked = name => { checks.push({ name, passed: true }); console.log('PASS', name); };
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor(); await chooseProject(page, id);
    const response = await (await page.request.get(`${base}/api/projects/${id}/conversations`)).json(); const active = response.conversations.find(chat => chat.activeRunId); assert.ok(active, 'An actual in-progress Pi session is required for this check.');
    await page.locator('.chat-item').filter({ hasText: active.title }).click(); await page.getByLabel('停止生成').waitFor(); await page.locator('.progress-line').getByText(/DeepSeek|清洗|批表格/).waitFor();
    await page.screenshot({ path: path.join(output, 'workbench-live-active-session.png') }); checked('实际完整年报会话显示所属 Pi 运行与清洗批次进度');
    await page.reload(); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor(); assert.equal(await selectedProject(page), id);
    await page.locator('.chat-item').filter({ hasText: active.title }).click(); await page.getByLabel('停止生成').waitFor(); await page.locator('.progress-line').getByText(/DeepSeek|清洗|批表格/).waitFor(); checked('刷新浏览器后从持久 activeRunId 恢复实际运行进度');
    await page.getByRole('button', { name: /^新对话/ }).click(); await page.getByLabel('发送给金融 Agent 的消息').fill('另一个会话的待发送草稿'); assert.equal(await page.getByLabel('发送消息', { exact: true }).isEnabled(), true); checked('长任务运行时新对话仍可输入和发送，检查未实际发送');
    await page.getByRole('button', { name: '财报看板', exact: true }).click(); await page.getByText('会话正在处理财报，已入库的数据会逐步显示', { exact: true }).waitFor();
    const dashboard = await (await page.request.get(`${base}/api/projects/${id}/dashboard`)).json(); assert.ok(dashboard.catalog.counts.facts > 0); assert.ok(dashboard.catalog.processing.length > 0);
    await page.screenshot({ path: path.join(output, 'workbench-live-progress-dashboard.png') }); checked('真实看板在整份财报完成前展示已分批入库的事实和处理状态');
    assert.deepEqual(writes, []); assert.deepEqual(errors, []); checked('没有发送、取消或其他写入请求，没有浏览器异常');
    fs.writeFileSync(path.join(output, 'browser-active-session-live-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), projectId: id, runId: active.activeRunId, countsAtCheck: dashboard.catalog.counts, passed: checks.length, checks, writes, errors, scope: 'Readonly view of existing live Pi run; not full-document correctness evidence.' }, null, 2));
  } catch (error) { await page.screenshot({ path: path.join(output, 'active-session-live-failure.png') }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

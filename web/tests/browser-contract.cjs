/* Client contract tests. API responses below are fixtures, not model or parser evidence. */
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const { chromium } = playwright;
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:5173';
const output = path.resolve('web/test-results');
fs.mkdirSync(output, { recursive: true });
const checks = [];
const checked = (name) => { checks.push({ name, status: 'passed', evidence: 'browser with controlled API fixtures' }); console.log('PASS', name); };

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage();
  const pageErrors = []; page.on('pageerror', error => pageErrors.push(error.message));
  let settings = { llm: { provider: 'openai-compatible', baseUrl: '', model: '', hasKey: false, contextWindow: 128000, maxTokens: 8192 }, embedding: { enabled: false, baseUrl: '', model: '', hasKey: false }, ocr: { mode: 'local', baseUrl: '', model: '', hasKey: false }, runtime: { maxToolCalls: 24, timeoutSeconds: 120 } };
  const projects = [{ id: 'p1', name: '金融研究工作空间' }];
  const documents = []; const conversations = []; const messageRequests = []; const settingsRequests = [];
  let runCounter = 0; let mode = 'normal'; let releaseCancelled; let cancelled = 0;
  let benchmarkTab = false;
  await page.route('**/api/**', async route => {
    const request = route.request(); const url = new URL(request.url()); const uri = url.pathname; const method = request.method();
    const respond = data => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
    if (uri === '/api/health') return respond({ status: 'ok' });
    if (uri === '/api/projects') {
      if (method === 'POST') { const item = { id: `p${projects.length + 1}`, name: request.postDataJSON().name }; projects.push(item); return respond(item); }
      return respond({ projects });
    }
    if (uri === '/api/settings') {
      if (method === 'PUT') {
        const value = request.postDataJSON(); settingsRequests.push(structuredClone(value));
        for (const section of ['llm', 'embedding', 'ocr']) { value[section].hasKey = value[section].apiKey === '' ? false : Boolean(value[section].apiKey || settings[section].hasKey); delete value[section].apiKey; }
        settings = value;
      }
      return respond(settings);
    }
    if (uri === '/api/settings/test') return respond({ ok: true, message: '连接成功（客户端契约测试服务）', latencyMs: 8 });
    if (uri === '/api/benchmark/catalog') return respond({ datasets: [], reports: [] });
    if (uri === '/api/benchmark/results') { benchmarkTab = true; return respond({ runs: [{ id: 'contract-fixture', name: '客户端展示契约记录', mode: 'fixture', status: 'completed', total: 2, passed: 1, failed: 1, summary: { accuracy: 0.5 }, note: '界面测试数据，不是财报 benchmark 成绩' }], runtime: [{ id: 'upload-contract', name: '上传交互测试', status: 'passed', evidence: 'fixture only' }, { id: 'model-run', name: '真实模型运行', status: 'not_run' }] }); }
    if (/\/projects\/[^/]+\/conversations$/.test(uri)) {
      const projectId = uri.split('/')[3];
      if (method === 'POST') { const item = { id: `c${conversations.length + 1}`, projectId, title: request.postDataJSON().title, messages: [] }; conversations.push(item); return respond(item); }
      return respond({ conversations: conversations.filter(item => item.projectId === projectId) });
    }
    if (/\/projects\/[^/]+\/uploads$/.test(uri)) {
      const doc = { id: `d${documents.length + 1}`, name: '财务样表.csv', status: 'parsing', pageCount: 1 };
      documents.push(doc); return respond({ documents: [doc] });
    }
    if (/\/projects\/[^/]+\/documents$/.test(uri)) { documents.forEach(item => { item.status = 'ready'; }); return respond({ documents }); }
    if (/\/documents\/[^/]+\/file$/.test(uri)) return route.fulfill({ contentType: 'text/csv', headers: { 'content-disposition': 'attachment; filename="report.csv"' }, body: 'year,revenue\n2023,100\n2024,110' });
    if (/\/documents\/[^/]+\/pages\/\d+$/.test(uri)) return respond({ text: '契约测试原文：2023 年收入 100，2024 年收入 110。<img src=x onerror=alert(1)>' });
    if (/\/documents\/[^/]+\/tables$/.test(uri)) return respond({ items: [{ sheet: 'Sheet1', preview: [['年度', '收入'], [2023, 100], [2024, 110]], row_count: 3 }] });
    if (/\/documents\/[^/]+$/.test(uri)) return respond({ ...documents[0], status: 'ready', tables: [{ name: 'Sheet1', columns: ['年度', '收入'], rows: [[2023, 100], [2024, 110]], rowCount: 2 }] });
    if (/\/conversations\/[^/]+\/messages$/.test(uri)) {
      const conversation = conversations.find(item => item.id === uri.split('/')[3]);
      const body = request.postDataJSON(); messageRequests.push(body);
      if (mode === 'error') return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: { code: 'MODEL_NOT_CONFIGURED', message: '请先配置主模型 API。' } }) });
      const runId = `r${++runCounter}`; const messageId = `a${runCounter}`;
      conversation.messages.push({ id: `u${runCounter}`, role: 'user', ...body, createdAt: new Date().toISOString() });
      conversation.activeRunId = runId;
      return respond({ runId, messageId });
    }
    if (/\/runs\/[^/]+\/cancel$/.test(uri)) { cancelled++; releaseCancelled?.(); return respond({ status: 'cancelling' }); }
    if (/\/runs\/[^/]+\/events$/.test(uri)) {
      const runId = uri.split('/')[3]; const conversation = conversations.find(item => item.activeRunId === runId); const messageId = `a${runId.slice(1)}`;
      if (mode === 'cancel') await new Promise(resolve => { releaseCancelled = resolve; });
      const isCancelled = mode === 'cancel';
      const content = isCancelled ? '已停止。' : '已读取表格中的两年收入。\n\n| 年度 | 收入 |\n| --- | ---: |\n| 2023 | 100 |\n| 2024 | 110 |\n\n同比增长 **10%**。';
      const message = { id: messageId, role: 'assistant', content, status: isCancelled ? 'cancelled' : 'completed', sources: [{ sourceId: 'd1:p1', documentId: 'd1', page: 1, name: '财务样表.csv', quote: '2023,100; 2024,110' }], artifacts: [], createdAt: new Date().toISOString() };
      conversation.messages.push(message); delete conversation.activeRunId;
      const events = [['status', { stage: 'thinking' }], ['tool', { name: 'finance.query', status: 'completed', summary: '读取两行测试数据' }], ['delta', { text: content }], ['message', { message }], ['done', { status: isCancelled ? 'cancelled' : 'completed' }]];
      return route.fulfill({ contentType: 'text/event-stream', body: events.map(([event, value], index) => `id: ${index + 1}\nevent: ${event}\ndata: ${JSON.stringify(value)}\n\n`).join('') });
    }
    if (/\/conversations\/[^/]+$/.test(uri)) return respond(conversations.find(item => item.id === uri.split('/')[3]));
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { code: 'TEST_UNKNOWN_ROUTE', message: `Unhandled fixture route: ${uri}` } }) });
  });
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    await page.getByText('服务已连接', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'API 配置', exact: true }).count(), 1);
    assert.equal(await page.locator('.api-entry').count(), 1);
    assert.equal(await page.getByLabel('发送消息', { exact: true }).isDisabled(), true);
    await page.screenshot({ path: path.join(output, 'desktop-chat.png') }); checked('对话首页、两个 API 入口、空消息禁发');

    await page.getByRole('button', { name: 'API 配置', exact: true }).click();
    await page.getByLabel('API 地址 Base URL').fill('http://remote.example/v1');
    await page.getByLabel('模型名称 服务商提供的 Model ID').fill('contract-model');
    await page.getByRole('button', { name: '保存设置', exact: true }).click();
    await page.getByText(/远程服务需要 HTTPS/).waitFor();
    await page.getByLabel('API 地址 Base URL').fill('https://api.example.com/v1');
    await page.locator('#llm-key').fill('not-a-real-secret-contract-test');
    assert.equal(await page.locator('#llm-key').getAttribute('type'), 'password');
    await page.getByText('高级设置 · 上下文与价格', { exact: true }).click();
    await page.locator('#llm-input-price').fill('1.25'); await page.locator('#llm-output-price').fill('5');
    await page.getByRole('button', { name: '保存并测试连接' }).click();
    await page.getByText('连接成功（客户端契约测试服务）').waitFor();
    assert.equal(await page.locator('#llm-key').inputValue(), '');
    assert.equal(settingsRequests[0].llm.apiKey, 'not-a-real-secret-contract-test');
    const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } })); assert.equal(storage.includes('not-a-real-secret'), false);
    await page.screenshot({ path: path.join(output, 'desktop-api.png') }); checked('API URL 校验、真实测试接口契约、密钥清空且不写浏览器存储');

    await page.getByRole('button', { name: '文档与 OCR', exact: true }).click(); await page.locator('#ocr-mode').selectOption('api');
    await page.locator('#ocr-baseUrl').fill('https://ocr.example.com/recognize'); assert.equal(await page.locator('#ocr-model').count(), 0);
    await page.getByRole('button', { name: '运行限制', exact: true }).click();
    await page.locator('#runtime-budget').fill('5'); await page.getByRole('button', { name: '保存设置', exact: true }).click(); await page.getByText(/启用人民币预算前/).waitFor();
    await page.locator('#runtime-exchange').fill('7'); await page.getByRole('button', { name: '保存设置', exact: true }).click(); await page.getByText(/设置已保存/).waitFor();
    await page.getByLabel('关闭设置').click(); checked('OCR 配置、预算价格和折算率校验');

    await page.getByLabel('添加附件', { exact: true }).click(); await page.getByRole('button', { name: /从电脑添加文件/ }).click();
    await page.locator('input[type=file]').setInputFiles({ name: '财务样表.csv', mimeType: 'text/csv', buffer: Buffer.from('year,revenue\n2023,100\n2024,110') });
    await page.locator('.attachments .file-chip').waitFor(); await page.locator('.attachments').getByText(/已入库/).waitFor(); checked('附件上传接口、解析状态刷新、对话附件显示');
    await page.getByLabel('发送给金融 Agent 的消息').fill('比较两年的收入并计算同比。');
    await page.getByLabel('发送给金融 Agent 的消息').press('Enter');
    await page.getByText('同比增长', { exact: false }).waitFor(); await page.locator('.message.assistant table').waitFor();
    assert.deepEqual(messageRequests[0].documentIds, ['d1']);
    await page.getByLabel('发送消息', { exact: true }).waitFor(); checked('Enter 发送、SSE delta/message/done、最终消息与 Markdown 表格');

    await page.locator('.source-pill').click(); await page.locator('.page-text').getByText(/契约测试原文/).waitFor();
    assert.equal(await page.locator('.page-text img').count(), 0); await page.screenshot({ path: path.join(output, 'desktop-evidence.png') });
    await page.getByLabel('关闭附件流向').click(); checked('原文引用抽屉、页文本读取、HTML 字符串安全显示');

    const downloadPromise = page.waitForEvent('download'); await page.getByLabel('导出当前对话').click(); const download = await downloadPromise; assert.match(download.suggestedFilename(), /\.md$/); checked('当前对话导出 Markdown');
    await page.getByRole('button', { name: /^新对话/ }).click(); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    await page.locator('.chat-item').first().click(); await page.locator('.message.assistant table').waitFor(); checked('新对话、历史记录恢复、消息持久化接口');

    mode = 'error'; await page.getByLabel('发送给金融 Agent 的消息').fill('错误重试测试'); await page.getByLabel('发送消息', { exact: true }).click();
    await page.getByText('请先配置主模型 API。', { exact: true }).waitFor(); assert.equal(await page.getByLabel('发送给金融 Agent 的消息').inputValue(), '错误重试测试'); checked('后端失败明确显示且保留未发送草稿');
    mode = 'cancel'; await page.getByLabel('关闭错误提示').click(); await page.getByLabel('发送消息', { exact: true }).click();
    await page.getByLabel('停止生成').waitFor(); await page.getByLabel('停止生成').click();
    await page.getByText('已停止。', { exact: true }).waitFor(); assert.equal(cancelled, 1); checked('停止按钮请求后端取消并保留停止状态'); mode = 'normal';

    await page.getByRole('button', { name: '数据集与测试', exact: true }).click(); await page.getByRole('button', { name: '查看历史测试记录', exact: true }).click(); await page.getByRole('tab', { name: /组件结果/ }).click(); await page.locator('.component-result h3').getByText('客户端展示契约记录', { exact: true }).waitFor();
    await page.locator('.component-result h3').getByText('真实模型运行', { exact: true }).waitFor(); await page.locator('.component-result').filter({ hasText: '真实模型运行' }).getByText('未执行', { exact: true }).waitFor(); assert.ok(benchmarkTab); checked('验收中心读取真实接口契约，未运行不伪装通过');

    await page.getByLabel('新建项目').click(); await page.getByLabel('项目名称', { exact: true }).fill('项目 <img src=x>'); await page.getByRole('button', { name: '创建项目', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.project-group.selected')?.getAttribute('data-project-id') === 'p2'); assert.equal(await page.locator('.sidebar img').count(), 0); checked('项目创建、选择和名称转义');
    await page.getByRole('button', { name: /^新对话/ }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel('展开侧边栏').click(); await page.getByRole('button', { name: /^新对话/ }).click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    await page.screenshot({ path: path.join(output, 'mobile-chat.png') });
    await page.getByRole('button', { name: 'API 配置', exact: true }).click(); await page.screenshot({ path: path.join(output, 'mobile-api.png') });
    assert.equal(await page.evaluate(() => document.querySelector('dialog').scrollWidth > document.querySelector('dialog').clientWidth), false);
    await page.keyboard.press('Escape'); checked('390px 移动布局、侧栏、设置弹窗、Escape 关闭、无横向溢出');
    assert.deepEqual(pageErrors, []); checked('全流程没有浏览器运行时异常');
    fs.writeFileSync(path.join(output, 'browser-contract-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Frontend browser tests with API fixtures. NOT backend integration, parser, model, or benchmark accuracy evidence.', passed: checks.length, checks, pageErrors }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); fs.writeFileSync(path.join(output, 'browser-contract-failure.json'), JSON.stringify({ error: String(error.stack || error), checks }, null, 2)); process.exitCode = 1; });

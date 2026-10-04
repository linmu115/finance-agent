const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Browser contracts with controlled API fixtures; these are not model accuracy results. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:5174';
const output = path.resolve('web/test-results');
const checks = [];
const checked = name => { checks.push({ name, passed: true }); console.log('PASS', name); };
const projects = [{ id: 'empty', name: '空项目', documentCount: 0 }, { id: 'research', name: '消费行业财报研究', documentCount: 2 }];
const conversations = []; const releases = new Map(); const streamRequests = []; const cancelled = []; const messageRequests = [];
let runNumber = 0; let validationPolls = 0; let uploaded = false;
const docs = [{ id: 'doc1', document_id: 'doc1', name: '甲公司 2024 年报.pdf', original_name: '甲公司 2024 年报.pdf', status: 'ready', state: 'ready', pageCount: 140, fact_count: 6 }, { id: 'doc2', document_id: 'doc2', name: '乙公司 2024 年报.pdf', original_name: '乙公司 2024 年报.pdf', status: 'ready', state: 'ready', pageCount: 140, fact_count: 4 }];
const fact = (id, company, year, value, other = {}) => ({ fact_id: id, document_id: company === '甲公司' ? 'doc1' : 'doc2', metric: 'revenue', label: '营业收入', statement: 'income', company, year, period: String(year), scope: 'consolidated_CAS', currency: 'CNY', value: String(value), raw_value: String(value / 10000), raw_unit: '万元', normalized_unit: 'CNY', version: 'original', dimensions: {}, source_ref: { document_id: company === '甲公司' ? 'doc1' : 'doc2', page: 80, table_id: 'table1', row: 2, column: 1 }, ...other });
const facts = [fact('a1', '甲公司', 2023, 80000000), fact('a2', '甲公司', 2024, 120000000), fact('b1', '乙公司', 2023, 60000000), fact('b2', '乙公司', 2024, 90000000), fact('a3', '甲公司', 2023, 12000000, { metric: 'net_profit', label: '净利润' }), fact('a4', '甲公司', 2024, 24000000, { metric: 'net_profit', label: '净利润' }), fact('b3', '乙公司', 2024, 60000, { currency: 'USD', normalized_unit: 'USD', version: 'foreign' })];
const catalog = { database_path: 'D:\\codex\\金融\\data\\finance.sqlite', documents_path: 'D:\\codex\\金融\\data\\documents\\research', index_path: 'D:\\codex\\金融\\data\\indexes\\research', counts: { documents: 2, pages: 280, tables: 30, facts: facts.length }, companies: ['甲公司', '乙公司'], periods: ['2023', '2024'], scopes: ['consolidated_CAS'], currencies: ['CNY', 'USD'], metrics: [{ metric: 'revenue', label: '营业收入', statement: 'income' }, { metric: 'net_profit', label: '净利润', statement: 'income' }] };
const settings = { llm: { provider: 'openai-compatible', baseUrl: 'https://api.deepseek.com', model: 'deepseek-flash', hasKey: true }, embedding: { enabled: false, baseUrl: '', model: '', hasKey: false }, ocr: { mode: 'local', baseUrl: '', model: '' }, runtime: { maxToolCalls: 24, timeoutSeconds: 120 } };
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage(); const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const req = route.request(); const url = new URL(req.url()); const uri = url.pathname;
    const json = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (uri === '/api/projects') return json({ projects });
    if (uri === '/api/settings') return json(settings);
    if (uri === '/api/health') return json({ ok: true });
    if (/\/projects\/[^/]+\/conversations$/.test(uri)) {
      const projectId = uri.split('/')[3];
      if (req.method() === 'POST') { const chat = { id: `c${conversations.length + 1}`, projectId, title: req.postDataJSON().title, messages: [] }; conversations.push(chat); return json(chat); }
      return json({ conversations: conversations.filter(chat => chat.projectId === projectId) });
    }
    if (/\/conversations\/[^/]+\/messages$/.test(uri)) {
      const chat = conversations.find(item => item.id === uri.split('/')[3]); const body = req.postDataJSON(); messageRequests.push(body);
      chat.messages.push({ id: `u${++runNumber}`, role: 'user', ...body }); chat.activeRunId = `r${runNumber}`;
      return json({ runId: chat.activeRunId, messageId: `a${runNumber}` });
    }
    if (/\/conversations\/[^/]+$/.test(uri)) return json(conversations.find(item => item.id === uri.split('/')[3]));
    if (/\/runs\/[^/]+\/events$/.test(uri)) {
      const id = uri.split('/')[3]; streamRequests.push(id);
      const chat = conversations.find(item => item.activeRunId === id);
      await new Promise(resolve => releases.set(id, resolve));
      const stopped = cancelled.includes(id); const message = { id: `a${id.slice(1)}`, role: 'assistant', content: stopped ? `${chat.title}已停止` : `${chat.title}完成，数据已入库`, status: stopped ? 'cancelled' : 'completed' };
      chat.messages.push(message); delete chat.activeRunId;
      const events = [['status', { stage: 'normalizing' }], ['tool', { name: 'process_documents', status: 'completed', toolCallId: `tool-${id}`, summary: '字段清洗并入库完成' }], ['delta', { text: message.content }], ['message', { message }], ['done', {}]];
      try { return await route.fulfill({ contentType: 'text/event-stream', body: events.map(([event, data], at) => `id: ${at + 1}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('') }); } catch { return; }
    }
    if (/\/runs\/[^/]+\/cancel$/.test(uri)) { const id = uri.split('/')[3]; cancelled.push(id); releases.get(id)?.(); return json({ ok: true }); }
    if (/\/uploads$/.test(uri)) { uploaded = true; return json({ documents: [{ id: 'registered', name: '测试财报.pdf', status: 'registered' }] }); }
    if (/\/projects\/[^/]+\/documents$/.test(uri)) return json({ documents: uri.includes('/empty/') ? [] : [...docs, ...(uploaded ? [{ id: 'registered', name: '测试财报.pdf', status: 'registered' }] : [])] });
    if (/\/dashboard$/.test(uri)) return json({ documents: docs, facts, catalog, total: facts.length, truncated: false });
    if (/\/financial-data$/.test(uri)) {
      const filter = JSON.parse(url.searchParams.get('filters') || '{}'); let items = facts.filter(item => Object.entries(filter).every(([key, value]) => key === 'metrics' ? value.includes(item.metric) : key === 'dimensions' ? Object.entries(value).every(([k, v]) => item.dimensions[k] === v) : item[key] === value));
      if (url.searchParams.get('format') === 'csv') return route.fulfill({ contentType: 'text/csv', headers: { 'content-disposition': 'attachment; filename="finance.csv"' }, body: 'company,metric,period,value\n' + items.map(item => `${item.company},${item.metric},${item.period},${item.value}`).join('\n') });
      return json({ items, total: items.length, limit: 5000, offset: 0 });
    }
    if (/\/documents\/[^/]+\/tables$/.test(uri)) return json({ items: [] });
    if (/\/documents\/[^/]+\/pages\/\d+$/.test(uri)) return json({ text: '甲公司原始财报第 80 页：营业收入 12,000 万元。' });
    if (/\/documents\/[^/]+$/.test(uri)) return json(docs.find(doc => uri.includes(doc.id)) || docs[0]);
    if (uri === '/api/benchmark/catalog') return json({ datasets: [{ id: 'native', title: '无需 OCR 的财报 PDF', description: '4 份真实年报，共 925 页，保留原始文字层。', url: '/api/benchmark/download/native-pdf' }, { id: 'v02', title: '财报问答 benchmark v0.2', description: '186 道题目、标准答案、原始报告与评分说明。', url: '/api/benchmark/download/benchmark-v02' }], reports: [], validation: { runUrl: '/api/benchmark/run', description: '通过实际 Pi 会话处理测试附件并验证入库与查询。' } });
    if (uri === '/api/benchmark/run') { assert.equal(req.postDataJSON().mode, 'quick'); return json({ id: 'validation1', state: 'running', message: '正在执行两个会话', reportUrl: '/api/benchmark/report/validation1' }); }
    if (uri === '/api/benchmark/run/validation1') return json({ id: 'validation1', state: ++validationPolls > 1 ? 'completed' : 'running', message: validationPolls > 1 ? '2 项通过，0 项失败' : '正在验证入库结果', report: validationPolls > 1 ? { passed: 2, failed: 0, fixture: true } : undefined });
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { message: `Unhandled fixture ${uri}` } }) });
  });
  try {
    await page.goto(base); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    assert.equal(await selectedProject(page), 'research'); checked('首次进入优先选择已有财报的项目');
    await page.locator('input[type=file]').setInputFiles({ name: '测试财报.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 fixture') });
    await page.locator('.attachments').getByText('已附加 · 发送后处理').waitFor(); assert.equal(messageRequests.length, 0); checked('添加附件仅登记，发送前不启动模型处理');
    await page.getByLabel('发送给金融 Agent 的消息').fill('处理第一批财报'); await page.getByLabel('发送消息', { exact: true }).click();
    await page.getByLabel('停止生成').waitFor();
    await page.getByRole('button', { name: /^新对话/ }).click(); await page.getByLabel('发送给金融 Agent 的消息').fill('处理第二批财报');
    assert.equal(await page.getByLabel('发送消息', { exact: true }).isEnabled(), true); await page.getByLabel('发送消息', { exact: true }).click(); await page.getByLabel('停止生成').waitFor();
    await page.waitForFunction(() => document.querySelectorAll('.chat-item .progress-dot').length === 2);
    assert.deepEqual(streamRequests.sort(), ['r1', 'r2']); assert.deepEqual(messageRequests[0].documentIds, ['registered']); checked('两段会话并行运行，附件属于发起会话');
    await page.getByLabel('停止生成').click(); await page.getByText('处理第二批财报已停止', { exact: true }).waitFor(); assert.deepEqual(cancelled, ['r2']);
    await page.locator('.chat-item').filter({ hasText: '处理第一批财报' }).click(); await page.getByLabel('停止生成').waitFor();
    assert.equal(streamRequests.filter(id => id === 'r1').length, 1); checked('停止只影响当前会话，切回后台会话复用仍在运行的流');
    const projectToggle = page.locator('[data-project-id="research"] .project-toggle');
    await projectToggle.click(); assert.equal(await projectToggle.getAttribute('aria-expanded'), 'false');
    assert.equal(await page.locator('[data-project-id="research"] .chat-item').count(), 0);
    await page.getByLabel('停止生成').waitFor(); assert.deepEqual(cancelled, ['r2']);
    await projectToggle.click(); await page.locator('[data-project-id="research"] .chat-item').filter({ hasText: '处理第一批财报' }).waitFor();
    checked('项目下的会话展开和收起不影响当前任务');
    await chooseProject(page, 'empty'); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor();
    assert.equal(await page.locator('.project-group.selected .project-toggle').isEnabled(), true);
    await page.locator('[data-project-id="research"] .chat-item').filter({ hasText: '处理第一批财报' }).click();
    assert.equal(await selectedProject(page), 'research');
    releases.get('r1')(); await page.getByText('处理第一批财报完成，数据已入库', { exact: true }).waitFor(); checked('跨项目切换不停止其他项目运行，结果回到所属会话');
    const restored = { id: 'restored', projectId: 'research', title: '刷新前的后台会话', activeRunId: 'r3', messages: [{ id: 'u3', role: 'user', content: '刷新前的后台会话' }] }; conversations.push(restored);
    await page.reload(); await page.getByRole('heading', { name: '今天想研究什么？' }).waitFor(); assert.equal(await selectedProject(page), 'research'); checked('项目选择在刷新后恢复');
    await page.locator('.chat-item').filter({ hasText: restored.title }).click(); await page.getByLabel('停止生成').waitFor(); assert.ok(streamRequests.includes('r3'));
    releases.get('r3')(); await page.getByText('刷新前的后台会话完成，数据已入库', { exact: true }).waitFor(); checked('刷新后根据持久会话 activeRunId 恢复运行与结果');
    await page.getByRole('button', { name: '财报看板', exact: true }).click(); await page.getByRole('heading', { name: '财报看板', exact: true }).waitFor();
    await page.getByText(/当前指标包含不同币种或计量单位/).waitFor(); checked('混币种数据不会被放进同一数值轴');
    await page.getByLabel('币种', { exact: true }).selectOption('CNY'); await page.locator('.financial-chart-wrap svg').waitFor();
    assert.equal(await page.locator('.financial-chart-wrap rect[role=button]').count(), 4);
    await page.getByLabel('公司', { exact: true }).selectOption('甲公司'); await page.waitForFunction(() => document.querySelectorAll('.financial-chart-wrap rect[role=button]').length === 2);
    await page.getByRole('button', { name: '折线', exact: true }).click(); assert.equal(await page.locator('.financial-chart-wrap circle').count(), 2);
    await page.getByLabel('横轴', { exact: true }).selectOption('company'); await page.getByRole('button', { name: '柱状', exact: true }).click();
    await page.getByLabel('横轴', { exact: true }).selectOption('period'); checked('公司与币种筛选，期间/公司横轴，柱状/折线实时更新');
    await page.getByRole('button', { name: '+ 添加指标' }).click(); await page.getByLabel('纵轴指标 2').selectOption('net_profit');
    assert.equal(await page.locator('.financial-chart-wrap rect[role=button]').count(), 4); checked('动态指标目录支持多指标同单位对比');
    const svgDownload = page.waitForEvent('download'); await page.getByRole('button', { name: 'SVG', exact: true }).click(); const svg = await svgDownload; const svgPath = path.join(output, 'workbench-chart.svg'); await svg.saveAs(svgPath); assert.match(fs.readFileSync(svgPath, 'utf8'), /xmlns="http:\/\/www.w3.org\/2000\/svg"/);
    const pngDownload = page.waitForEvent('download'); await page.getByRole('button', { name: 'PNG', exact: true }).click(); const png = await pngDownload; const pngPath = path.join(output, 'workbench-chart.png'); await png.saveAs(pngPath); assert.ok(fs.statSync(pngPath).size > 3000); checked('SVG 和 PNG 图表可实际下载');
    const csvDownload = page.waitForEvent('download'); await page.getByRole('link', { name: '导出当前筛选 CSV' }).click(); const csv = await csvDownload; const csvPath = path.join(output, 'workbench-data.csv'); await csv.saveAs(csvPath); const csvText = fs.readFileSync(csvPath, 'utf8'); assert.match(csvText, /120000000/); assert.ok(!csvText.includes('乙公司')); checked('CSV 导出携带当前公司、币种与指标条件');
    await page.locator('.financial-chart-wrap rect[role=button]').first().click(); await page.getByRole('button', { name: '查看原文', exact: true }).click(); await page.locator('.page-text').getByText(/原始财报第 80 页/).waitFor();
    await page.getByLabel('关闭附件流向').click(); checked('图表数据点能够追溯至财报原始页面');
    await page.getByText('资料与数据存在哪里', { exact: true }).click(); await page.getByText(catalog.database_path, { exact: true }).waitFor();
    await page.locator('.financial-dashboard').evaluate(element => element.scrollTop = 0); await page.screenshot({ path: path.join(output, 'workbench-dashboard-desktop.png') }); checked('看板显示真实数据库、文档和索引位置');
    await page.getByRole('button', { name: '数据集与测试', exact: true }).click(); await page.getByRole('heading', { name: '数据集与测试', exact: true }).waitFor();
    assert.equal(await page.getByRole('link', { name: '下载数据包' }).count(), 2);
    await page.getByText('开发回归与历史结果', {exact:true}).click();
    await page.getByRole('button', { name: '快速端到端测试' }).click(); await page.getByText('测试正在运行', { exact: true }).waitFor();
    await page.getByRole('button', { name: '财报看板', exact: true }).click(); await page.getByRole('button', { name: '数据集与测试', exact: true }).click();
    await page.getByText('测试运行完成', { exact: true }).waitFor(); await page.screenshot({ path: path.join(output, 'workbench-datasets-desktop.png') }); checked('测试包入口、实际运行按钮、离开后恢复测试进度');
    await page.getByRole('button', { name: 'API 配置', exact: true }).click(); await page.getByText(/DeepSeek 通过 Pi/).waitFor(); assert.equal(await page.getByRole('button', { name: 'Embedding API', exact: true }).count(), 0); await page.getByLabel('关闭设置').click(); checked('清洗和对话共用 API 配置，一期不提供 Embedding 调用入口');
    await page.getByRole('button', { name: '财报看板', exact: true }).click(); await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.financial-dashboard h1').waitFor(); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(output, 'workbench-dashboard-mobile.png') }); checked('390px 看板布局无页面横向溢出');
    assert.deepEqual(errors, []); checked('完整流程无浏览器异常');
    fs.writeFileSync(path.join(output, 'browser-workbench-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Frontend contract tests with controlled API fixtures, NOT live model/semantic validation.', passed: checks.length, checks, pageErrors: errors }, null, 2));
  } catch (error) { await page.screenshot({ path: path.join(output, 'workbench-failure.png') }); throw error; }
  finally { releases.forEach(release => release()); await browser.close(); }
})().catch(error => { console.error(error); fs.writeFileSync(path.join(output, 'browser-workbench-failure.json'), JSON.stringify({ error: String(error.stack || error), checks }, null, 2)); process.exitCode = 1; });

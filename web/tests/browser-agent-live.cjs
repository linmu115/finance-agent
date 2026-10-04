const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Real browser -> Pi Agent -> configured official DeepSeek -> financial MCP service.
 * Uses synthetic developer fixtures and never reads benchmark gold answers.
 * Run only after the caller confirms the primary service is ready for evaluation.
 */
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const { chromium } = playwright;
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:3001';
const output = path.resolve('web/test-results'); fs.mkdirSync(output, { recursive: true });
const checks = []; const errors = []; const runEvidence = [];
const checked = (name, evidence) => { checks.push({ name, status: 'passed', evidence }); console.log('PASS', name); };
const failed = (name, error) => { checks.push({ name, status: 'failed', reason: String(error.message || error) }); console.error('FAIL', name, String(error.message || error)); };

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  let projectId; let conversationId; let firstRun; let modelMetadata;
  async function serverRun(id) { return page.evaluate(async id => (await (await fetch(`/api/runs/${id}`)).json()), id); }
  async function waitTerminal(id) {
    const deadline = Date.now() + 600000;
    let lastReport = 0;
    while (Date.now() < deadline) {
      const run = await serverRun(id);
      if (['completed', 'failed', 'cancelled'].includes(run.status)) return run;
      if (Date.now() - lastReport > 20000) { console.log('RUN', id, run.status, run.stage); lastReport = Date.now(); }
      await page.waitForTimeout(750);
    }
    throw new Error('Observation deadline reached after 10 minutes; run may still be live. Inspect this run ID before retrying.');
  }
  try {
    const healthResponse = await page.request.get(`${base}/api/health`);
    const health = await healthResponse.json(); assert.equal(health.modelConfigured, true, 'A real model must already be configured');
    const settingsResponse = await page.request.get(`${base}/api/settings`);
    const configured = await settingsResponse.json();
    assert.equal(new URL(configured.llm.baseUrl).hostname, 'api.deepseek.com', 'This acceptance run only uses the official DeepSeek endpoint');
    modelMetadata = { model: configured.llm.model, baseUrl: configured.llm.baseUrl };
    await page.goto(base); await page.getByText('服务已连接', { exact: true }).waitFor();
    await page.getByLabel('新建项目').click(); const name = `Agent 浏览器验收 ${new Date().toISOString()}`;
    await page.getByLabel('项目名称', { exact: true }).fill(name); await page.getByRole('button', { name: '创建项目', exact: true }).click();
    await page.waitForFunction(n => document.querySelector('.project-group.selected .project-toggle > span')?.textContent === n, name);
    projectId = await selectedProject(page);
    const uploadResponse = page.waitForResponse(response => response.url().endsWith(`/api/projects/${projectId}/uploads`) && response.request().method() === 'POST');
    await page.locator('input[type=file]').setInputFiles(path.resolve('web/test-fixtures/finance.xlsx'));
    const upload = await (await uploadResponse).json();
    await page.locator('.attachments .file-chip').waitFor();
    checked('真实 Excel 上传成为对话附件', { projectId, uploadedDocumentId: upload.documents[0].id, initialParseStatus: upload.documents[0].status });
    await page.evaluate(() => {
      window.__agentUiTrace = { messageLengths: [], stages: [], tools: [], mutations: 0 };
      new MutationObserver(() => {
        const trace = window.__agentUiTrace; trace.mutations++;
        const length = [...document.querySelectorAll('.message.assistant .markdown')].reduce((sum, item) => sum + item.textContent.length, 0);
        if (trace.messageLengths.at(-1) !== length) trace.messageLengths.push(length);
        const stage = document.querySelector('.run-progress .progress-line')?.textContent;
        if (stage && trace.stages.at(-1) !== stage) trace.stages.push(stage);
        for (const item of document.querySelectorAll('.run-progress .trace li b')) if (!trace.tools.includes(item.textContent)) trace.tools.push(item.textContent);
      }).observe(document.getElementById('root'), { childList: true, subtree: true, characterData: true });
    });
    const firstResponse = page.waitForResponse(response => /\/api\/conversations\/[^/]+\/messages$/.test(new URL(response.url()).pathname) && response.request().method() === 'POST');
    const sseRequest = page.waitForRequest(request => /\/api\/runs\/[^/]+\/events$/.test(new URL(request.url()).pathname));
    await page.getByLabel('发送给金融 Agent 的消息').fill('读取我上传的 Excel。查找2024年度和2023年度的营业收入，必须调用读取工具和计算工具，用(本年/上年-1)*100计算2024年同比增长率。请给出数值、公式和原文来源引用；不要猜测。');
    await page.getByLabel('发送给金融 Agent 的消息').press('Enter');
    const firstHttp = await firstResponse; const firstBody = await firstHttp.json();
    assert.equal(firstHttp.status(), 202, JSON.stringify(firstBody)); firstRun = firstBody.runId;
    conversationId = new URL(firstHttp.url()).pathname.split('/')[3]; console.log('FIRST_RUN', firstRun, 'CONVERSATION', conversationId);
    await sseRequest;
    const terminal = await waitTerminal(firstRun); runEvidence.push(terminal);
    await page.waitForTimeout(600);
    const trace = await page.evaluate(() => window.__agentUiTrace);
    try { assert.ok(trace.stages.length > 0); checked('SSE 连接与真实运行阶段展示', { stages: trace.stages, runId: firstRun }); } catch (error) { failed('SSE 连接与真实运行阶段展示', error); }
    try { assert.ok(trace.tools.length > 0); checked('真实工具执行状态展示', { tools: trace.tools }); } catch (error) { failed('真实工具执行状态展示', error); }
    const conversation = await page.evaluate(async id => (await (await fetch(`/api/conversations/${id}`)).json()), conversationId);
    const assistant = conversation.messages.filter(message => message.role === 'assistant').at(-1);
    if (assistant) await page.waitForFunction(({ id, status }) => {
      const item = document.querySelector(`[data-message-id="${id}"]`);
      return item && item.getAttribute('data-status') === (status || 'saved');
    }, { id: assistant.id, status: assistant.status }, { timeout: 30000 });
    try {
      assert.equal(terminal.status, 'completed', terminal.error || 'Agent did not complete');
      assert.match(assistant?.content || '', /10(?:\.0+)?\s*[%％]/);
      assert.ok((assistant.sources || []).length > 0, 'No source references were persisted');
      checked('真实 Agent 完成同比计算并持久化来源', { runId: firstRun, result: assistant.content, sources: assistant.sources });
    } catch (error) { failed('真实 Agent 完成同比计算并持久化来源', error); }
    try { assert.ok(trace.messageLengths.filter(length => length > 0).length > 1); checked('回答呈现多个真实增量片段', { observedLengths: trace.messageLengths }); } catch (error) { failed('回答呈现多个真实增量片段', error); }
    if (assistant?.sources?.length) {
      await page.locator('.source-pill').first().click(); await page.locator('.page-text').getByText(/营业收入/).waitFor();
      checked('最终回答的原文来源抽屉', { originalDocument: 'finance.xlsx' });
      await page.screenshot({ path: path.join(output, 'agent-live-evidence.png') });
      await page.getByLabel('关闭附件流向').click();
    }
    await page.screenshot({ path: path.join(output, 'agent-live-answer.png') });
    const renderedAssistant = await page.locator('.message.assistant .markdown').last().innerText();
    await page.reload(); await page.getByText('服务已连接', { exact: true }).waitFor();
    await chooseProject(page, projectId);
    await page.locator('.chat-item').first().click();
    await page.locator('.message.assistant').waitFor();
    try { assert.equal(await page.locator('.message.assistant .markdown').last().innerText(), renderedAssistant); assert.ok((await page.locator('.message.assistant').last().innerText()).length > 0); checked('刷新页面后从真实持久化历史恢复对话', { conversationId }); } catch (error) { failed('刷新页面后从真实持久化历史恢复对话', error); }
    const cancelResponse = page.waitForResponse(response => /\/api\/conversations\/[^/]+\/messages$/.test(new URL(response.url()).pathname) && response.request().method() === 'POST');
    await page.getByLabel('发送给金融 Agent 的消息').fill('请重新逐步读取整个表格，分别计算营业收入和归母净利润同比，并整理详细核对步骤。');
    await page.getByLabel('发送消息', { exact: true }).click();
    const cancelBody = await (await cancelResponse).json();
    await page.getByLabel('停止生成').waitFor(); await page.waitForTimeout(1200); await page.getByLabel('停止生成').click();
    const cancelledRun = await waitTerminal(cancelBody.runId); runEvidence.push(cancelledRun);
    try { assert.equal(cancelledRun.status, 'cancelled'); checked('真实模型运行可由对话停止按钮取消', { runId: cancelBody.runId, status: cancelledRun.status }); } catch (error) { failed('真实模型运行可由对话停止按钮取消', error); }
    await page.waitForTimeout(500); await page.screenshot({ path: path.join(output, 'agent-live-cancelled.png') });
    assert.deepEqual(errors, []); checked('真实 Agent 全流程无浏览器异常', { errors });
  } catch (error) { failed('真实 Agent 浏览器流程', error); await page.screenshot({ path: path.join(output, 'agent-live-error.png') }).catch(() => {}); }
  finally {
    fs.writeFileSync(path.join(output, 'browser-agent-live-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Real browser + Node Pi harness + configured official DeepSeek + Python service. Synthetic developer fixture, NOT benchmark gold or accuracy dataset.', model: modelMetadata, projectId, conversationId, firstRun, passed: checks.filter(check => check.status === 'passed').length, failed: checks.filter(check => check.status === 'failed').length, checks, runEvidence, pageErrors: errors }, null, 2));
    await browser.close();
  }
  if (checks.some(check => check.status === 'failed')) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });

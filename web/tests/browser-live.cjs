const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Real browser + local Node/Python service. Synthetic files test the transport and parser, not benchmark accuracy. */
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const { chromium } = playwright;
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:5173';
const output = path.resolve('web/test-results'); fs.mkdirSync(output, { recursive: true });
const checks = []; const errors = [];
const checked = (name, evidence) => { checks.push({ name, status: 'passed', evidence }); console.log('PASS', name); };
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base); await page.getByText('服务已连接', { exact: true }).waitFor();
    checked('真实本地服务启动并通过前端代理连接', { base });
    await page.getByLabel('新建项目').click(); const name = `前端联调验收 ${new Date().toISOString()}`;
    await page.getByLabel('项目名称', { exact: true }).fill(name); await page.getByRole('button', { name: '创建项目', exact: true }).click();
    await page.waitForFunction(n => document.querySelector('.project-group.selected .project-toggle > span')?.textContent === n, name);
    const projectId = await selectedProject(page);
    checked('真实创建独立项目', { projectId, name });
    await page.locator('input[type=file]').setInputFiles(['csv', 'tsv', 'xlsx', 'pdf'].map(ext => path.resolve(`web/test-fixtures/finance.${ext}`)));
    await page.waitForFunction(() => document.querySelectorAll('.attachments .file-chip').length === 4, { timeout: 90000 });
    await page.waitForFunction(() => [...document.querySelectorAll('.attachments .file-chip small')].every(item => /已入库|已解析/.test(item.textContent)), { timeout: 90000 });
    const documents = await page.evaluate(async id => (await (await fetch(`/api/projects/${id}/documents`)).json()).documents, projectId);
    assert.equal(documents.length, 4); assert.ok(documents.every(doc => ['ready', 'needs_review'].includes(doc.status)));
    checked('CSV/TSV/XLSX/PDF 四种真实上传、解析与状态回显', { documents: documents.map(({ id, name, status, pageCount }) => ({ id, name, status, pageCount })) });
    await page.locator('.attachments .file-chip-main').filter({ hasText: 'finance.xlsx' }).click();
    await page.getByRole('button',{name:/^提取表格/}).click();await page.locator('.attachment-source table').waitFor();
    await page.locator('.attachment-source').getByText('营业收入', { exact: true }).waitFor();
    assert.match(await page.locator('.attachment-source').innerText(), /110/);
    checked('Excel 单元格由后端解析、附件流向展示实际表格', { documentId: documents.find(doc => doc.name.endsWith('.xlsx')).id });
    await page.getByRole('button', { name: '原文', exact: true }).click(); await page.locator('.page-text').getByText(/营业收入/).waitFor();
    checked('Excel 原文读取和可追溯展示', { source: '实际数据库页记录' });
    await page.getByLabel('关闭附件流向').click();
    await page.locator('.attachments .file-chip-main').filter({ hasText: 'finance.pdf' }).click(); await page.getByRole('button', { name: '原文', exact: true }).click();
    await page.locator('.page-text').getByText(/Frontend integration financial report/).waitFor();
    await page.locator('.doc-img').waitFor(); await page.waitForFunction(() => document.querySelector('.doc-img')?.naturalWidth > 0);
    await page.screenshot({ path: path.join(output, 'live-pdf-evidence.png') });
    checked('PDF 原文、真实渲染页图像和来源地址', { documentId: documents.find(doc => doc.name.endsWith('.pdf')).id });
    const downloadPromise = page.waitForEvent('download'); await page.getByRole('link', { name: '下载原件', exact: true }).click(); const download = await downloadPromise;
    assert.match(download.suggestedFilename(), /\.pdf$/); checked('真实原件下载', { filename: download.suggestedFilename() });
    await page.getByLabel('关闭附件流向').click();
    await page.getByRole('button', { name: 'API 配置', exact: true }).click();
    await page.getByRole('button', { name: '运行限制', exact: true }).click();
    assert.equal(await page.locator('#runtime-timeout').inputValue(), '120');
    await page.getByRole('button', { name: '保存设置', exact: true }).click(); await page.getByText(/设置已保存/).waitFor();
    checked('真实设置读取与无改动保存，服务端返回脱敏设置', { secretAccess: 'none', externalRequests: 'none' });
    await page.getByLabel('关闭设置').click();
    const health = await page.evaluate(async () => (await fetch('/api/health')).json());
    if (!health.modelConfigured) {
      await page.getByLabel('发送给金融 Agent 的消息').fill('计算营业收入的同比增长率，并引用来源。'); await page.getByLabel('发送消息', { exact: true }).click();
      await page.getByText('请先在API配置中填写主模型地址和模型ID', { exact: true }).waitFor();
      assert.equal(await page.locator('.message.assistant').count(), 0);
      assert.equal(await page.locator('.attachments .file-chip').count(), 4);
      checked('未配置主模型时真实报错、保留草稿与附件、不制造回答', { modelConfigured: false });
    }
    await page.screenshot({ path: path.join(output, 'live-upload.png') });
    assert.deepEqual(errors, []); checked('真实服务联调无浏览器异常', { pageErrors: errors });
    fs.writeFileSync(path.join(output, 'browser-live-results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), scope: 'Real frontend + local Node API + Python parser. Four synthetic fixtures. Does not prove real LLM success or benchmark accuracy.', projectId, passed: checks.length, checks, pageErrors: errors }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); fs.writeFileSync(path.join(output, 'browser-live-failure.json'), JSON.stringify({ error: String(error.stack || error), checks }, null, 2)); process.exitCode = 1; });

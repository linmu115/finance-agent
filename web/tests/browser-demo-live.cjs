const { selectedProject, chooseProject } = require('./project-navigation.cjs');
/* Read-only inspection of an EXISTING completed demo. Never starts an Agent.
 * Default: node web/tests/browser-demo-live.cjs
 * Legacy:  node web/tests/browser-demo-live.cjs --demo benchmark/results/demo.json --output-prefix demo-legacy-live
 * Missing/in-progress demo: writes status=not_run, exits 2 before browser/network.
 */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const argv = process.argv.slice(2);
function option(name, fallback) {
  const index = argv.indexOf(name);
  if (index < 0) return fallback;
  assert.ok(argv[index + 1] && !argv[index + 1].startsWith('--'), `Missing value: ${name}`);
  return argv[index + 1];
}
for (let i = 0; i < argv.length; i += 2) assert.ok(['--demo', '--output-prefix'].includes(argv[i]), `Unknown option: ${argv[i]}`);
const recordPath = path.resolve(root, option('--demo', 'benchmark/results/demo-latest.json'));
assert.ok(['demo.json', 'demo-latest.json'].some(name => recordPath === path.join(root, 'benchmark/results', name)), 'Only the two known demo records are accepted');
const prefix = option('--output-prefix', path.basename(recordPath) === 'demo-latest.json' ? 'demo-latest-live' : 'demo-legacy-live');
assert.match(prefix, /^demo-(?:latest|legacy)-live(?:-[a-z0-9-]+)?$/, 'Output prefix must identify latest or legacy evidence');
assert.ok(!(path.basename(recordPath) === 'demo.json' && prefix.startsWith('demo-latest-')), 'Legacy checks cannot be labeled as the latest demo');
const output = path.join(root, 'web/test-results');
fs.mkdirSync(output, { recursive: true });
const reportPath = path.join(output, `${prefix}-verification.json`);
const screenshotPath = path.join(output, `${prefix}-desktop.png`);
const answerScreenshotPath = path.join(output, `${prefix}-answer-desktop.png`);
const base = new URL(process.env.WEB_TEST_URL || 'http://127.0.0.1:3001');
assert.ok(base.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname), 'Only a local HTTP application is supported');
assert.equal(base.pathname, '/');
assert.ok(!base.username && !base.password && !base.search && !base.hash);
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const relative = file => path.relative(root, file).split(path.sep).join('/');
const report = {
  checkedAt: new Date().toISOString(), status: 'running',
  scope: 'Read-only production browser inspection of an existing completed demo. No new model call, no data mutation, no financial-answer scoring.',
  record: relative(recordPath), baseUrl: base.origin,
  checks: [], errors: [], blockedRequests: [],
  safety: { allowedMethods: ['GET', 'HEAD'], sameOriginOnly: true, serviceWorkers: 'blocked', modelRequests: 0, mutatingRequests: 0 },
  visualReview: { status: 'not_run', reason: 'Automated loading checks do not establish Chinese label readability, six-bar semantics, or financial correctness; inspect the screenshot separately.' },
};
function writeReport() {
  report.passed = report.checks.filter(check => check.status === 'passed').length;
  report.failed = report.checks.filter(check => check.status === 'failed').length;
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
}
function checked(name, evidence) { report.checks.push({ name, status: 'passed', evidence }); console.log('PASS', name); }
function pending(reason) {
  report.status = 'not_run'; report.reason = reason; writeReport();
  console.log(JSON.stringify({ status: 'not_run', message: '待运行：新版示例须由宿主另行生成并完成，本脚本不会创建项目或调用模型。', reason, report: relative(reportPath) }));
  process.exitCode = 2;
}
function sameOrigin(value) {
  const url = new URL(value, base);
  assert.equal(url.origin, base.origin, 'Evidence must use the same application origin');
  return url;
}
function list(value, key) { return Array.isArray(value) ? value : value[key]; }
function sourceDocument(source) { return source.documentId || source.document_id || source.sourceId?.split(':p')[0]; }
function pngs(message) { return (message.artifacts || []).filter(item => /\.png$/i.test(item.name || '') && item.url); }

(async () => {
  if (!fs.existsSync(recordPath)) return pending('demo_record_not_generated');
  const bytes = fs.readFileSync(recordPath); const record = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/, ''));
  report.recordSha256 = sha256(bytes);
  if (record.status !== 'completed') return pending(`demo_status_${record.status || 'unknown'}`);
  for (const key of ['projectId', 'conversationId', 'runId']) assert.match(record[key] || '', /^[A-Za-z0-9_-]+$/, `Missing/invalid ${key}`);
  Object.assign(report, { projectId: record.projectId, conversationId: record.conversationId, runId: record.runId });
  let playwright;
  try { playwright = require('playwright'); }
  catch { playwright = require('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
  const browser = await playwright.chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: 'block', acceptDownloads: true });
  const methods = {};
  await context.route('**/*', async route => {
    const request = route.request(); const url = new URL(request.url()); const method = request.method();
    methods[method] = (methods[method] || 0) + 1;
    const mutation = !['GET', 'HEAD'].includes(method);
    if (mutation) report.safety.mutatingRequests++;
    if (mutation || url.origin !== base.origin) {
      report.blockedRequests.push({ method, path: url.pathname, reason: mutation ? 'method_not_read_only' : 'different_origin' });
      return route.abort('blockedbyclient');
    }
    return route.continue();
  });
  if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => socket.close());
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
  async function json(endpoint) {
    const url = sameOrigin(endpoint);
    return page.evaluate(async target => {
      const response = await fetch(target, { method: 'GET' });
      if (!response.ok) throw new Error(`Read-only API returned HTTP ${response.status}`);
      return response.json();
    }, url.href);
  }
  async function imageReady(locator) {
    await locator.scrollIntoViewIfNeeded();
    await page.waitForFunction(element => element?.complete && element.naturalWidth > 0 && element.naturalHeight > 0, await locator.elementHandle());
    return locator.evaluate(image => ({ width: image.naturalWidth, height: image.naturalHeight, url: image.getAttribute('src') }));
  }
  try {
    await page.goto(base.origin); await page.getByText('服务已连接', { exact: true }).waitFor();
    const projects = list(await json('/api/projects'), 'projects');
    const project = projects.find(item => item.id === record.projectId);
    assert.ok(project, 'Recorded demo project does not exist on this server');
    const conversation = await json(`/api/conversations/${record.conversationId}`);
    assert.equal(conversation.projectId, record.projectId);
    assert.ok(!conversation.activeRunId, 'Read-only inspection requires a completed conversation without an active run');
    const saved = record.conversation?.messages?.filter(message => message.role === 'assistant' && pngs(message).length).at(-1);
    const assistant = saved ? conversation.messages.find(message => message.id === saved.id) : conversation.messages.filter(message => message.role === 'assistant' && pngs(message).length && (!message.runId || message.runId === record.runId)).at(-1);
    assert.ok(assistant, 'No completed assistant message with a PNG artifact exists');
    assert.ok(!assistant.status || ['completed', 'saved'].includes(assistant.status), 'Assistant message is not completed');
    if (saved) assert.equal(assistant.content, saved.content, 'Live history differs from the saved demo snapshot');
    report.assistantMessageId = assistant.id;
    const docs = list(await json(`/api/projects/${record.projectId}/documents`), 'documents');
    const expectedIds = record.documentIds || docs.map(doc => doc.id);
    for (const id of expectedIds) assert.ok(docs.some(doc => doc.id === id && ['ready', 'needs_review'].includes(doc.status)), 'Expected report is missing or not parsed');
    await chooseProject(page, record.projectId);
    const chats = list(await json(`/api/projects/${record.projectId}/conversations`), 'conversations');
    const index = chats.findIndex(chat => chat.id === record.conversationId); assert.ok(index >= 0);
    await page.waitForFunction(count => document.querySelectorAll('.chat-item').length === count, chats.length);
    const chatButton = page.locator('.chat-item').nth(index);
    assert.equal((await chatButton.innerText()).trim(), conversation.title || '新对话');
    const opened = page.waitForResponse(response => new URL(response.url()).pathname === `/api/conversations/${record.conversationId}`);
    await chatButton.click(); assert.equal((await (await opened).json()).id, record.conversationId);
    const message = page.locator(`[data-message-id="${assistant.id}"]`);
    await message.locator('.markdown').waitFor();
    assert.ok((await message.locator('.markdown').innerText()).length > 50, 'Business response is empty');
    checked('加载记录指定的真实项目、已完成历史对话与业务结果', { projectName: project.name, assistantMessageId: assistant.id, documents: expectedIds.length, pages: docs.filter(doc => expectedIds.includes(doc.id)).reduce((sum, doc) => sum + (doc.pageCount || 0), 0), snapshotContentMatches: Boolean(saved) });
    await message.locator('.markdown').evaluate(element => {
      const scroller = document.querySelector('.conversation-scroll');
      scroller.scrollTop += element.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 20;
    });
    await page.screenshot({ path: answerScreenshotPath });
    report.answerScreenshot = relative(answerScreenshotPath); report.answerScreenshotSha256 = sha256(fs.readFileSync(answerScreenshotPath));

    const images = [];
    for (const artifact of pngs(assistant)) {
      const url = sameOrigin(artifact.url);
      assert.ok(url.pathname.startsWith(`/api/projects/${record.projectId}/artifacts/`));
      const card = message.locator('.artifact-card').filter({ has: page.getByRole('img', { name: artifact.name, exact: true }) });
      assert.equal(await card.count(), 1);
      const rendered = await imageReady(card.locator('.artifact-image'));
      assert.equal(sameOrigin(rendered.url).pathname, url.pathname);
      const downloadLink = card.getByRole('link', { name: '下载', exact: true });
      assert.equal(sameOrigin(await downloadLink.getAttribute('href')).pathname, url.pathname);
      const downloadPromise = page.waitForEvent('download'); await downloadLink.click();
      const download = await downloadPromise; assert.equal(await download.failure(), null);
      const downloaded = fs.readFileSync(await download.path());
      assert.equal(downloaded.subarray(0, 8).toString('hex'), '89504e470d0a1a0a', 'Downloaded artifact is not a PNG');
      const hash = sha256(downloaded);
      const artifactDir = path.basename(recordPath) === 'demo-latest.json' ? 'demo-latest-artifacts' : 'demo-artifacts';
      assert.equal(path.basename(artifact.name), artifact.name, 'Artifact filename must not contain a path');
      const local = path.join(root, 'benchmark/results', artifactDir, artifact.name);
      let retainedCopy;
      if (fs.existsSync(local)) { assert.equal(hash, sha256(fs.readFileSync(local)), 'Downloaded image differs from the retained demo artifact'); retainedCopy = relative(local); }
      images.push({ name: artifact.name, ...rendered, sha256: hash, bytes: downloaded.length, suggestedFilename: download.suggestedFilename(), retainedCopy });
    }
    checked('PNG在既有回答中实际加载，下载按钮取得有效PNG', { images });

    const sources = assistant.sources || [];
    assert.equal(await message.locator('.source-pill').count(), sources.length);
    const selected = expectedIds.map(id => sources.findIndex(source => sourceDocument(source) === id && (source.page || source.pageNumber)));
    assert.ok(selected.every(index => index >= 0), 'Each uploaded demo document must have a clickable page citation');
    const sourceChecks = [];
    for (const index of selected) {
      const source = sources[index]; const documentId = sourceDocument(source); const physicalPage = source.page || source.pageNumber;
      const expected = await json(`/api/projects/${record.projectId}/documents/${documentId}/pages/${physicalPage}`);
      const expectedText = expected.text || expected.page?.text;
      assert.ok(expectedText?.length, 'Cited source page has no readable text');
      const button = message.locator('.source-pill').nth(index); const label = await button.innerText(); await button.click();
      await page.waitForFunction(text => document.querySelector('.page-text')?.textContent === text, expectedText);
      const drawer = page.getByRole('complementary', { name: '文件与证据' });
      const pageLabel = await drawer.locator('.page-controls').innerText(); assert.ok(pageLabel.includes(`第 ${physicalPage} 页`));
      const image = await imageReady(drawer.locator('.doc-img'));
      assert.equal(sameOrigin(image.url).pathname, sameOrigin(expected.imageUrl).pathname);
      const original = sameOrigin(await drawer.getByRole('link', { name: '打开原始文档', exact: true }).getAttribute('href'));
      assert.equal(original.pathname, `/api/projects/${record.projectId}/documents/${documentId}/file`);
      assert.equal(original.hash, `#page=${physicalPage}`);
      const originalStatus = await page.evaluate(async url => (await fetch(url, { method: 'HEAD' })).status, original.href);
      assert.equal(originalStatus, 200);
      sourceChecks.push({ documentId, label, physicalPage, textLength: expectedText.length, textMatchesActualPageResponse: true, image, originalStatus });
      await page.getByLabel('关闭附件流向').click();
      await drawer.waitFor({ state: 'hidden' });
    }
    checked('每份资料的引用能打开实际页文本、原页图像与原件入口', { sourceCount: sources.length, sources: sourceChecks });

    const chart = message.locator('.artifact-card').filter({ has: page.getByRole('img', { name: images[0].name, exact: true }) });
    await imageReady(chart.locator('.artifact-image'));
    await chart.locator('.artifact-image').evaluate(element => {
      const scroller = document.querySelector('.conversation-scroll');
      const chartBox = element.getBoundingClientRect(); const box = scroller.getBoundingClientRect();
      scroller.scrollTop += chartBox.top - box.top - Math.max(20, (scroller.clientHeight - chartBox.height) / 2);
    });
    await page.waitForFunction(element => {
      const bounds = element.getBoundingClientRect(); const viewport = document.querySelector('.conversation-scroll').getBoundingClientRect();
      return bounds.top >= viewport.top && bounds.bottom <= viewport.bottom;
    }, await chart.locator('.artifact-image').elementHandle());
    await page.screenshot({ path: screenshotPath });
    report.screenshot = relative(screenshotPath); report.screenshotSha256 = sha256(fs.readFileSync(screenshotPath));
    const before = await message.locator('.markdown').innerText();
    await page.reload(); await page.getByText('服务已连接', { exact: true }).waitFor();
    await chooseProject(page, record.projectId);
    await page.waitForFunction(count => document.querySelectorAll('.chat-item').length === count, chats.length);
    await page.locator('.chat-item').nth(index).click(); await message.locator('.markdown').waitFor();
    assert.equal(await message.locator('.markdown').innerText(), before);
    checked('刷新并重新选择项目后，同一持久化业务回复可恢复', { conversationId: record.conversationId });
    assert.deepEqual(report.blockedRequests, [], 'A forbidden request was attempted and blocked');
    assert.deepEqual(report.errors, []);
    report.safety.observedMethods = methods;
    checked('全程仅同源GET/HEAD，无变更、模型调用或浏览器错误', { observedMethods: methods, blockedRequests: report.blockedRequests.length });
    report.status = 'passed';
  } catch (error) {
    report.status = 'failed'; report.checks.push({ name: '既有示例只读浏览器检查', status: 'failed', reason: String(error.message || error) });
    console.error('FAIL', String(error.message || error)); process.exitCode = 1;
  } finally { report.safety.observedMethods = methods; writeReport(); await browser.close(); }
  console.log(JSON.stringify({ status: report.status, passed: report.passed, failed: report.failed, report: relative(reportPath), screenshot: report.screenshot }));
})().catch(error => {
  report.status = 'failed'; report.checks.push({ name: '检查前置条件', status: 'failed', reason: String(error.message || error) }); writeReport();
  console.error('FAIL', String(error.message || error)); process.exitCode = 1;
});

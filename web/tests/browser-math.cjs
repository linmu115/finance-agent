// Uses the built 3001 frontend with browser-only API fixtures; no project data is written.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve('web/test-results/math');
fs.mkdirSync(output, { recursive: true });
const content = String.raw`### 现金流估值

行内公式：\(r=\frac{P_1-P_0}{P_0}\)。金额 $10 和 $20 保持普通文本。

\[
EV=\sum_{t=1}^{n}\frac{FCF_t}{(1+WACC)^t}+\frac{FCF_n(1+g)}{(WACC-g)(1+WACC)^n}
\]

| 指标 | 计算口径 |
| --- | --- |
| 毛利率 | $$\frac{R-C}{R}$$ |

公式下方仍可划选引用。这是界面渲染样例，不是投资分析。
`;
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], fontFailures = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', r => { if (/KaTeX.*woff2/.test(r.url()) && r.status() !== 200) fontFailures.push(r.url()); });
    await page.route('**/api/**', route => {
      assert.equal(route.request().method(), 'GET');
      const url = new URL(route.request().url()).pathname;
      const chat = { id: 'math-chat', projectId: 'math-project', title: '公式渲染样例', messages: [{ id: 'math-answer', role: 'assistant', content, status: 'completed' }] };
      const data = url === '/api/projects' ? { projects: [{ id: 'math-project', name: '公式界面样例' }] }
        : url === '/api/settings' ? { llm: { model: '界面样例', hasKey: true } }
        : url === '/api/health' ? { ok: true, service: 'connected', modelConfigured: true }
        : url === '/api/approvals' ? { requests: [] }
        : url.endsWith('/documents') ? { documents: [] }
        : url.endsWith('/conversations') ? { conversations: [chat] }
        : url === '/api/conversations/math-chat' ? chat : {};
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto('http://127.0.0.1:3001/');
    await page.getByRole('button', { name: '公式渲染样例', exact: true }).click();
    await page.locator('.markdown .katex-display').waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('.markdown .katex').count(), 3);
    assert.equal(await page.locator('.katex-error').count(), 0);
    assert.match(await page.locator('.markdown').innerText(), /金额 \$10 和 \$20/);
    assert.equal(await page.locator('.markdown table').count(), 1);
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
    const sizes = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth,
      math: [...document.querySelectorAll('.katex-display')].map(e => ({ client: e.clientWidth, scroll: e.scrollWidth, overflow: getComputedStyle(e).overflowX })) }));
    assert.ok(sizes.page <= sizes.viewport + 1, JSON.stringify(sizes));
    assert.equal(sizes.math[0].overflow, 'auto');
    assert.deepEqual(errors, []); assert.deepEqual(fontFailures, []);
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({ passed: true, fixtureOnly: true, sizes, errors, fontFailures }, null, 2));
    console.log(JSON.stringify({ passed: true, output, sizes }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

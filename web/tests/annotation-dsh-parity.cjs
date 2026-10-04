/* Isolated browser/HTTP acceptance; no mutations to the user's conversations. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve('data/acceptance-annotation-dsh-20261004');
const base = 'http://127.0.0.1:5173';
(async () => {
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
 page.setDefaultTimeout(12000);
 const checks = [], errors = []; let sends = 0;
 page.on('pageerror', error => errors.push(error.message));
 page.on('request', req => { if (req.method() === 'POST' && /\/messages$/.test(req.url())) sends++; });
 const pass = name => { checks.push(name); console.log('PASS', name); };
 const editor = page.getByRole('dialog', { name: '引用详情', exact: true });
 const comment = page.getByRole('textbox', { name: '引用注释' });
 const input = page.getByRole('textbox', { name: '发送给金融 Agent 的消息' });
 const select = async (selector, quote, occurrence = 0) => {
  await page.locator(selector).first().scrollIntoViewIfNeeded();
  await page.locator(selector).first().evaluate((element, { quote, occurrence }) => {
   const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT), chars = []; let content = '';
   for (let n = walker.nextNode(); n; n = walker.nextNode()) for (let i = 0; i < n.length; i++) { content += n.data[i]; chars.push([n, i]); }
   let start = -1, cursor = 0;
   for (let i = 0; i <= occurrence; i++) { start = content.indexOf(quote, cursor); if (start < 0) throw new Error('Missing selection text'); cursor = start + quote.length; }
   const range = document.createRange(); range.setStart(...chars[start]); range.setEnd(chars[cursor - 1][0], chars[cursor - 1][1] + 1);
   const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
   element.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
  }, { quote, occurrence });
  await page.getByRole('menuitem', { name: '添加到当前会话' }).click(); await editor.waitFor();
 };
 const openList = async count => { await page.getByRole('button', { name: `${count} 条待发送引用`, exact: true }).hover(); await page.getByRole('dialog', { name: '待发送引用列表' }).waitFor(); };
 try {
  await page.goto(base); await page.getByRole('button', { name: '附件核验示例', exact: true }).click();
  await page.locator('[data-message-id="arun1"] .markdown').waitFor();
  await select('[data-message-id="arun1"] .markdown', '经营现金流', 1);
  assert.equal(await comment.evaluate(el => el === document.activeElement), true);
  let geometry = await editor.boundingBox(), composer = await page.locator('.composer').boundingBox();
  assert.equal(Math.round(geometry.x), Math.round(composer.x)); assert.ok(geometry.y + geometry.height < composer.y); assert.equal(geometry.width, 326);
  await comment.fill('验收编号：松石七二。');
  await comment.press('Shift+Enter'); await comment.type('第二行注释。');
  await comment.dispatchEvent('keydown', { key: 'Enter', isComposing: true }); assert.equal(await editor.isVisible(), true);
  await page.screenshot({ path: path.join(output, 'annotation-editor-desktop.png') });
  await comment.press('Enter'); await editor.waitFor({ state: 'hidden' });
  await input.dispatchEvent('keydown', { key: 'Enter', repeat: true }); assert.equal(sends, 0);
  assert.equal(await page.locator('.annotation-rail:not(.sent) .annotation-count').count(), 1);
  assert.equal(await page.locator('.annotation-chip').count(), 0);
  await page.getByRole('button', { name: '打开选段引用 1', exact: true }).waitFor();
  const highlight = await page.evaluate(() => [...CSS.highlights.get('finance-references')].map(r => ({ text: r.toString(), parent: r.startContainer.parentElement.textContent, before: (() => { const p=document.createRange(); p.selectNodeContents(document.querySelector('[data-message-id="arun1"] .markdown')); p.setEnd(r.startContainer,r.startOffset); return p.toString(); })() })));
  assert.equal(highlight.length, 1); assert.equal(highlight[0].text, '经营现金流'); assert.match(highlight[0].before, /第二处/);
  await page.getByRole('button', { name: '打开选段引用 1', exact: true }).click(); assert.match(await comment.inputValue(), /第二行注释/); await page.keyboard.press('Escape');
  pass('selection opens focused composer-anchored editor; Enter saves without sending, Shift+Enter inserts a line, IME/held Enter are guarded; exact second-occurrence highlight and source badge reopen the same editor');

  await select('[data-message-id="arun1"] .markdown', '经营现金流', 1); assert.match(await comment.inputValue(), /松石七二/); await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '1 条待发送引用', exact: true }).waitFor();
  await select('[data-message-id="arun1"] .markdown', '经营现金流', 0); await comment.fill('验收编号：云帆六八。'); await comment.press('Enter');
  await openList(2); assert.equal(await page.locator('.annotation-list-item').count(), 2);
  await page.screenshot({ path: path.join(output, 'annotation-hover-list.png') });
  await page.getByRole('button', { name: '编辑引用 1', exact: true }).click(); await page.getByRole('button', { name: '查看引用 2', exact: true }).click(); assert.equal(await comment.inputValue(), '验收编号：云帆六八。');
  await comment.fill('验收编号：云帆六八。已补充。'); await page.getByRole('button', { name: '查看引用 1', exact: true }).click(); assert.match(await comment.inputValue(), /松石七二/);
  await input.click(); await editor.waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '空白会话', exact: true }).click(); assert.equal(await page.locator('.annotation-rail:not(.sent) .annotation-count').count(), 0); assert.equal(await page.locator('.annotation-source-badge').count(), 0);
  await page.getByRole('button', { name: '附件核验示例', exact: true }).click(); await openList(2); await page.getByRole('button', { name: '编辑引用 2', exact: true }).click(); assert.match(await comment.inputValue(), /已补充/); await page.keyboard.press('Escape');
  await page.reload(); await page.getByRole('button', { name: '附件核验示例', exact: true }).click(); await openList(2); await page.getByRole('button', { name: '编辑引用 1', exact: true }).click(); assert.match(await comment.inputValue(), /第二行注释/); await page.keyboard.press('Escape');
  pass('compact hover list, individual edit/jump/delete controls, tabs, duplicate selection reuse, distinct repeated occurrences, outside close and per-chat/reload draft preservation');

  // Selection eligibility is tested on rendered isolated messages, not real user data.
  await page.evaluate(() => { const source=document.querySelector('[data-message-id="arun1"]'); source.dataset.status='running'; const range=document.createRange(); range.selectNodeContents(source.querySelector('.markdown')); const sel=getSelection(); sel.removeAllRanges(); sel.addRange(range); source.dispatchEvent(new PointerEvent('pointerup',{bubbles:true})); });
  assert.equal(await page.getByRole('menu', { name: '选文操作' }).count(), 0);
  await page.evaluate(() => { document.querySelector('[data-message-id="arun1"]').dataset.status='completed'; const range=document.createRange(); range.setStart(document.querySelector('.user-bubble').firstChild,0); range.setEndAfter(document.querySelector('.markdown')); getSelection().removeAllRanges();getSelection().addRange(range);document.querySelector('.markdown').dispatchEvent(new PointerEvent('pointerup',{bubbles:true})); });
  assert.equal(await page.getByRole('menu', { name: '选文操作' }).count(), 0); await page.evaluate(() => getSelection().removeAllRanges());
  pass('cross-message and streaming selections do not create references');

  const prompt = '这是引用传递测试。不要调用工具，不要分析财报。仅逐字输出两条引用各自的注释，包括换行和补充文字。';
  await input.fill(prompt); let payload;
  const reject = route => { payload=route.request().postDataJSON(); return route.fulfill({ status:503, contentType:'application/json', body:'{"error":{"message":"引用发送失败模拟"}}' }); };
  await page.route('**/api/conversations/chat1/messages',reject); await page.getByRole('button',{name:'发送消息',exact:true}).click(); await page.getByText('引用发送失败模拟',{exact:true}).waitFor();
  assert.deepEqual(payload.annotations.map(a=>a.occurrence),[1,0]); assert.equal(await input.inputValue(),prompt); await page.getByRole('button',{name:'2 条待发送引用',exact:true}).waitFor();
  await page.unroute('**/api/conversations/chat1/messages',reject);
  await page.getByRole('button',{name:'发送消息',exact:true}).click();
  await page.getByRole('button',{name:'打开 2 条已发送引用',exact:true}).waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.message.assistant')].some(el=>el.dataset.status==='completed'&&el.innerText.includes('松石七二')&&el.innerText.includes('云帆六八')),undefined,{timeout:90000});
  const chat=await(await fetch('http://127.0.0.1:3003/api/conversations/chat1')).json(); const saved=chat.messages.find(m=>m.annotations?.length===2);
  assert.deepEqual(saved.annotations.map(a=>a.occurrence),[1,0]); fs.writeFileSync(path.join(output,'annotation-live-evidence.json'),JSON.stringify({input:saved,answer:chat.messages.at(-1)},null,2));
  await page.getByRole('button',{name:'打开 2 条已发送引用',exact:true}).click(); assert.equal(await comment.count(),0); await page.getByRole('button',{name:'查看引用 2',exact:true}).click(); await editor.getByText('验收编号：云帆六八。已补充。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'重新添加到当前提问',exact:true}).click(); await comment.waitFor(); assert.equal(await comment.inputValue(),'验收编号：云帆六八。已补充。'); await comment.press('Enter');
  pass('failed send preserves drafts; real DeepSeek receives exact comments; occurrence metadata persists; sent count opens read-only history and supports reuse');

  const request={id:'fixture-approval',digest:'a'.repeat(64),conversationId:'chat1',operation:{operation:'sql',current_project:'合成验收',reason:'仅验证键盘事件互不干扰',scope:'夹具',sql:'UPDATE fixture SET value=1'}}; let approvals=[request],decisions=[];
  await page.route('**/api/approvals',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({requests:approvals})}));
  await page.route('**/api/approvals/*',route=>{decisions.push(route.request().postDataJSON());approvals=[];return route.fulfill({contentType:'application/json',body:'{"ok":true}'});});
  await page.getByRole('region',{name:'数据库操作授权'}).waitFor(); await openList(1); await page.getByRole('button',{name:'编辑引用 1',exact:true}).click(); await comment.press('Enter'); assert.equal(decisions.length,0); assert.equal(sends,2);
  await page.locator('.approval-card').focus();await page.keyboard.press('Escape');await page.getByRole('region',{name:'数据库操作授权'}).waitFor({state:'hidden'});assert.equal(decisions[0].allow,false);
  await openList(1); await page.getByRole('button',{name:'编辑引用 1',exact:true}).click();
  await page.setViewportSize({width:390,height:844}); geometry=await editor.boundingBox(); assert.ok(geometry.x>=8&&geometry.x+geometry.width<=382); assert.ok(geometry.y>=8&&geometry.y+geometry.height<=836);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390); await page.screenshot({path:path.join(output,'annotation-editor-mobile.png')});
  await page.getByRole('button',{name:'删除引用',exact:true}).click();await editor.waitFor({state:'hidden'});assert.equal(await page.locator('.annotation-rail:not(.sent) .annotation-count').count(),0);
  pass('annotation Enter does not authorize or send; compact mobile editor stays within viewport; removing last draft clears the dock');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify({checks,errors,sends,approvalFixture:true,decisions},null,2));
 } catch(error) { await page.screenshot({path:path.join(output,'failure.png')});fs.writeFileSync(path.join(output,'failure.txt'),String(error)+'\n'+await page.locator('body').innerText());throw error; }
 finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

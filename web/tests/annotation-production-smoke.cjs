// Read-only production smoke check. Drafts exist only in this isolated browser context.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 page.setDefaultTimeout(12000); let writes=0;const errors=[];
 page.on('request',r=>{if(r.method()!=='GET'&&r.method()!=='HEAD')writes++});page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:3001/');
  const project=page.locator('[data-project-id="b43ae45c-d96b-43b6-ab5b-04306c0eb142"] .project-toggle');await project.waitFor();if(await project.getAttribute('aria-expanded')!=='true')await project.click();
  await page.getByRole('button',{name:'处理这个财报并向我分析汇报',exact:true}).click();await page.locator('.message.assistant .markdown').last().waitFor();
  assert.equal(await page.getByRole('button',{name:'附件流向',exact:true}).count(),1);
  await page.getByRole('button',{name:'附件流向',exact:true}).click();await page.locator('.flow-select').first().waitFor();
  const flow=await page.locator('.flow-drawer').boundingBox(),chat=await page.locator('.chat-area').boundingBox();assert.equal(flow.y,0);assert.equal(flow.height,960);assert.ok(chat.x+chat.width<=flow.x+1);
  await page.locator('.flow-select').first().click();await page.getByRole('button',{name:'核对原始附件'}).click();await page.locator('.doc-img').waitFor();await page.waitForFunction(()=>document.querySelector('.doc-img')?.naturalWidth>0);await page.getByRole('button',{name:'关闭附件流向'}).click();
  console.log('PASS production flow entry/layout and original PDF');
  const para=page.locator('.message.assistant .markdown p').last();await para.scrollIntoViewIfNeeded();
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await para.evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);getSelection().removeAllRanges();getSelection().addRange(range);el.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));});
  const menu=page.getByRole('menuitem',{name:'添加到当前会话'});await menu.waitFor();
  const menuBox=await menu.boundingBox();assert.ok(menuBox.y>=0&&menuBox.y+menuBox.height<=960);
  await menu.click();const note=page.getByRole('textbox',{name:'引用注释'});await note.fill('只读 UI 验证，本段不发送。');await note.press('Enter');
  await page.getByRole('button',{name:'1 条待发送引用',exact:true}).hover();await page.getByRole('button',{name:'编辑引用 1',exact:true}).click();assert.equal(await note.inputValue(),'只读 UI 验证，本段不发送。');
  await page.screenshot({path:'data/acceptance-annotation-dsh-20261004/production-annotation.png'});await page.getByRole('button',{name:'删除引用',exact:true}).click();
  assert.equal(writes,0);assert.deepEqual(errors,[]);
  fs.writeFileSync('data/acceptance-annotation-dsh-20261004/production-checks.json',JSON.stringify({url:page.url(),flow,chat,menuBox,errors,writes,checks:['single attachment entry','full height right column','real original PDF visible','production annotation selection/editor/hover/edit/delete','no production writes']},null,2));
  console.log('PASS production quote interactions and menu viewport bounds; no production writes');
 }catch(error){await page.screenshot({path:'data/acceptance-annotation-dsh-20261004/production-failure.png'});throw error}
 finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

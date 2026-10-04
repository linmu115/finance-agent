// Isolated compiled-release UI verification; no credentials or model calls.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const base=process.env.RELEASE_URL;
 assert.match(base,/^http:\/\/127\.0\.0\.1:\d+$/);
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.setDefaultTimeout(15000);
 try {
  await page.goto(base);
  await page.getByRole('button',{name:'新建项目',exact:true}).waitFor();
  await page.locator(`[data-project-id="${process.env.RELEASE_PROJECT_ID}"]`).waitFor();
  assert.equal(await page.getByRole('button',{name:'附件流向',exact:true}).count(),1);
  await page.getByRole('button',{name:'附件流向',exact:true}).click();
  await page.locator('.flow-drawer').waitFor();
  const box=await page.locator('.flow-drawer').boundingBox();
  assert.equal(box.y,0);assert.equal(box.height,960);
  await page.getByRole('button',{name:'关闭附件流向'}).click();
  await page.getByRole('button',{name:'API 配置',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  assert.ok(await page.getByRole('dialog').getByText('主模型',{exact:false}).count());
  await page.screenshot({path:path.join(process.env.RELEASE_EVIDENCE,'fresh-release.png')});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(process.env.RELEASE_EVIDENCE,'browser-verification.json'),JSON.stringify({status:'passed',pageErrors:errors,attachmentPanel:box,checks:['compiled app renders','persisted project visible','single attachment flow entry','full height right panel','API configuration opens']},null,2));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

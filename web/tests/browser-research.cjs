/* Real, read-only UI verification of isolated research acceptance data. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chooseProject}=require('./project-navigation.cjs');
(async()=>{
 const root=path.resolve('data/retests/research-ingestion-20261005');
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'live-manifest.json'),'utf8'));
 const base=process.env.WEB_TEST_URL||'http://127.0.0.1:3003';
 const selected=manifest.runs[0];
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const checks=[];
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByText('服务已连接',{exact:true}).waitFor();
  if(width<700)await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  await chooseProject(page,manifest.project.id);
  const response=await page.request.get(base+`/api/projects/${manifest.project.id}/conversations`);
  const chats=(await response.json()).conversations,index=chats.findIndex(c=>c.id===selected.conversationId);assert.ok(index>=0);
  await page.locator(`#project-chats-${manifest.project.id} .chat-item`).nth(index).click();
  await page.getByRole('button',{name:'附件流向',exact:true}).click();
  const card=page.locator('.flow-select').filter({hasText:selected.filename}).filter({hasText:'研报记录'}).first();
  await card.click();
  const records=page.getByRole('region',{name:'研报提取记录'});await records.waitFor();
  assert.match(await records.innerText(),/国信证券/);assert.match(await records.innerText(),/2025-07-23/);
  assert.match(await page.locator('.flow-destinations').innerText(),/研报数据/);
  await page.screenshot({path:path.join(root,`research-flow-${width}.png`),fullPage:true});
  await records.getByRole('button',{name:'核对原文',exact:true}).first().click();
  await page.locator('.attachment-source').waitFor();
  assert.match(await page.locator('.attachment-source').innerText(),/原文|PDF|提取表格/);
  await page.getByRole('button',{name:'关闭附件流向',exact:true}).click();
  await page.getByRole('button',{name:'API 配置',exact:true}).click();
  await page.getByRole('button',{name:'语义检索',exact:true}).click();
  await page.getByLabel('启用语义检索',{exact:true}).waitFor();
  assert.match(await page.getByRole('dialog').innerText(),/全文检索与结构化查询|相同内容复用/);
  assert.deepEqual(errors,[]);
  checks.push({width,sourceNavigation:true,recordsAndAttribution:true,embeddingConfigurationVisible:true,errors});await page.close();
 }
 fs.writeFileSync(path.join(root,'browser-results.json'),JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

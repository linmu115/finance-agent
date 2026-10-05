const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const output=path.resolve('data/retests/script-cleaning-20261005');fs.mkdirSync(output,{recursive:true});
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const usage={calls:4,input:100000,output:7000,cacheRead:96000,cacheKnownInput:100000,uncachedInput:4000,reasoning:3500,costUsd:null,costCnyMin:.03392,costCnyMax:.06784,priceSource:'测试标价估算；非账单',phases:{cleaning:{calls:2,input:70000,output:5000,cacheRead:67000,reasoning:2500,costUsd:null,costCnyMin:.02434,costCnyMax:.04868},cleaning_review:{calls:2,input:30000,output:2000,cacheRead:29000,reasoning:1000,costUsd:null,costCnyMin:.00958,costCnyMax:.01916}}};
  const chat={id:'usage-chat',projectId:'usage-project',title:'用量验收',messages:[{id:'u1',role:'user',content:'将附件清洗入库并核对。'},{id:'a1',role:'assistant',content:'已完成清洗并核对主要报表。',status:'completed',usage},{id:'u2',role:'user',content:'继续处理'},{id:'a2',role:'assistant',content:'请求失败，已保存完成的批次。',status:'failed',usage:{...usage,unknownCalls:1,cacheUnknownCalls:1}}]};
  await page.route('**/api/**',async route=>{
   const uri=new URL(route.request().url()).pathname;const reply=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
   if(uri==='/api/projects')return reply({projects:[{id:chat.projectId,name:'财报用量测试'}]});
   if(uri.endsWith('/conversations'))return reply({conversations:[chat]});
   if(uri==='/api/conversations/'+chat.id)return reply(chat);
   if(uri.endsWith('/documents'))return reply({documents:[]});
   if(uri==='/api/settings')return reply({llm:{model:'fixture',hasKey:true},runtime:{},embedding:{},ocr:{},search:{}});
   return reply({ok:true,items:[],requests:[]});
  });
  await page.goto(process.env.WEB_TEST_URL||'http://127.0.0.1:3002');
  if(width<700)await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  await page.getByText('用量验收',{exact:true}).click();
  const footer=page.locator('[data-message-id="a1"] .usage-footer');await footer.waitFor();
  assert.match(await footer.innerText(),/96\.0%/);assert.match(await footer.innerText(),/107,000/);
  await footer.locator('summary').click();assert.match(await footer.innerText(),/脚本清洗/);assert.match(await footer.innerText(),/清洗核验/);assert.match(await footer.innerText(),/¥0\.034–0\.068/);
  const failed=page.locator('[data-message-id="a2"] .usage-footer');await failed.locator('summary').click();assert.match(await failed.innerText(),/1 次请求未返回完整用量/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),true,'usage footer causes page overflow');assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(output,`usage-${width}.png`),fullPage:true});await page.close();
 }
 console.log('PASS completed/failed task usage, weighted cache rate, phase detail, estimates, partial usage, desktop/mobile and no console errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

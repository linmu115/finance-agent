// UI-only download contract. All API requests are intercepted; no production document data is read.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true});
 const chat={id:'fixture-chat',projectId:'fixture-project',title:'报告包界面验收',messages:[{id:'answer',role:'assistant',content:'【事实/数据】每股价值 11.52 元。\n\n【推论】估值受增长假设影响。',status:'completed'}]};
 const errors=[];page.on('pageerror',e=>errors.push(e.message));let posts=0;
 await page.route('**/api/**',async route=>{
  const uri=new URL(route.request().url()).pathname;
  const send=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  if(uri==='/api/projects')return send({projects:[{id:chat.projectId,name:'报告包测试'}]});
  if(uri==='/api/settings')return send({llm:{model:'fixture',hasKey:false},embedding:{enabled:false},ocr:{mode:'local'},runtime:{}});
  if(uri==='/api/health')return send({ok:true});
  if(uri.endsWith('/documents'))return send({documents:[]});
  if(uri.endsWith('/conversations'))return send({conversations:[chat]});
  if(uri.endsWith('/report-package')){
   assert.equal(route.request().method(),'POST');posts++;
   return route.fulfill({contentType:'application/zip',body:await fs.readFile('data/evaluation/analyst-delivery-smoke-20261008/package-replay/report_package.zip')});
  }
  if(uri==='/api/conversations/'+chat.id)return send(chat);
  return send({});
 });
 try{
  await page.goto('http://127.0.0.1:3001');
  await page.getByText(chat.title,{exact:true}).click();
  const button=page.getByRole('button',{name:'财报分析报告',exact:true});await button.waitFor();
  const pending=page.waitForEvent('download');await button.click();const download=await pending;
  assert.equal(download.suggestedFilename(),'财报分析报告.zip');assert.equal(posts,1);
  const folder=path.resolve('docs/evidence/analyst-delivery-20261008');
  await download.saveAs(path.join(folder,'ui-report-package.zip'));
  await page.screenshot({path:path.join(folder,'report-button.png')});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(folder,'ui-validation.json'),JSON.stringify({scope:'UI fixture only; POST and downloadable ZIP; real model and export checked separately',posts,filename:download.suggestedFilename(),page_errors:errors},null,2));
  console.log('Report package button, POST, ZIP download and browser runtime: passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

/* Isolated UI fixtures: no request reaches the application API or a model. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:5175';
const out=path.resolve('web/test-results');
const checks=[],apiRequests=[],errors=[];
const passed=name=>{checks.push({name,passed:true});console.log('PASS',name);};
const report=(id,score,state='completed')=>({id,state,reportUrl:'/api/benchmark/run/'+id,message:'INTERNAL_LOG_SENTINEL {"raw":true,"run_id":"implementation-detail"}',report:{status:state==='failed'?'failed':'passed',checks:[{name:'附件上传登记',status:'passed'},{name:'独立标准值核对',status:score===37?'passed':'failed'}],normalization:{expected_facts:37,passed_facts:score,failed_facts:37-score,checks:[{id:'fact1',file:'original.pdf',status:score===37?'passed':'failed',expected:{metric:'assets',period:'2024-12-31'},errors:score===37?[]:['period']}]}}});
const reports={latest:report('latest',35,'failed'),older:report('older',37)};
const running={id:'fixture-running',state:'running',reportUrl:'/api/benchmark/run/fixture-running',message:'INTERNAL_LOG_SENTINEL RUNS {"implementation":"private"}',report:{runs:[{stage:'正在规范字段'},{stage:'正在建立资料索引'}]}};
const catalog={datasets:[{id:'v031',title:'财报清洗测试 v0.3.1',url:'/api/benchmark/download/normalization',description:'标准答案修订 2'}],reports:[{title:'历史问答数据说明',url:'/api/benchmark/report/v02'},{title:'最新完整测试 · 35/37',url:'/api/benchmark/run/latest'},{title:'上次完整测试 · 37/37',url:'/api/benchmark/run/older'}],validation:{runUrl:'/api/benchmark/run'}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 page.on('pageerror',error=>errors.push(error.message));
 let finish=false,polls=0,expectedMode='quick';
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),uri=url.pathname;
  if(!uri.startsWith('/api/')){
   if(url.origin!==new URL(base).origin)throw new Error('Unexpected external request: '+url.origin);
   return route.continue();
  }
  apiRequests.push({path:uri,method:request.method()});
  const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  if(uri==='/api/projects')return json({projects:[{id:'fixture',name:'界面隔离测试',documentCount:1}]});
  if(uri==='/api/settings')return json({llm:{baseUrl:'https://api.deepseek.com',model:'deepseek-flash',hasKey:true},embedding:{enabled:false},ocr:{mode:'local'},runtime:{}});
  if(uri==='/api/health')return json({ok:true});
  if(uri==='/api/projects/fixture/conversations')return json({conversations:[]});
  if(uri==='/api/projects/fixture/documents')return json({documents:[]});
  if(uri==='/api/benchmark/catalog')return json(catalog);
  if(uri==='/api/benchmark/run'&&request.method()==='POST'){assert.deepEqual(request.postDataJSON(),{mode:expectedMode});return json(running);}
  if(uri==='/api/benchmark/run/fixture-running'){polls++;return json(finish?report('fixture-running',37):running);}
  const id=uri.split('/').at(-1);if(uri.startsWith('/api/benchmark/run/')&&reports[id])return json(reports[id]);
  throw new Error('Unhandled API fixture; blocked instead of calling the app: '+uri);
 });
 try{
  await page.goto(base);await page.getByRole('heading',{name:'今天想研究什么？'}).waitFor();
  await page.getByRole('button',{name:'数据集与测试',exact:true}).click();
  await page.getByText('35 / 37',{exact:true}).waitFor();
  assert.equal(await page.locator('.validation-check').count(),2);
  assert.ok((await page.locator('.validation-check').allTextContents()).some(t=>t.includes('独立标准值核对')&&t.includes('未通过')));
  assert.ok(apiRequests.some(r=>r.path==='/api/benchmark/run/latest'));
  passed('首次打开数据集页面自动加载最新真实报告并显示逐项分数');
  const colors=await page.locator('.validation-progress.failed').evaluate(element=>({
   title:getComputedStyle(element.querySelector(':scope > b')).color,
   passed:getComputedStyle(element.querySelector('.validation-check b:not(.error-text)')).color,
   failed:getComputedStyle(element.querySelector('.validation-check b.error-text')).color,
  }));
  assert.notEqual(colors.passed,colors.failed,'a passed check must not inherit failure red from the report');
  const rgb=value=>value.match(/\d+/g).slice(0,3).map(Number);
  const [r,g,b]=rgb(colors.passed);assert.ok(Math.max(r,g,b)-Math.min(r,g,b)<5,'passed check should remain neutral');
  for(const value of [colors.title,colors.failed]){const [red,green,blue]=rgb(value);assert.ok(red>green+40&&red>blue+40,'failure title and failed checks should retain an error color');}
  passed('失败报告中通过项保持普通颜色，只有失败标题和失败项使用错误色');
  await page.screenshot({path:path.join(out,'dataset-latest-report.png'),fullPage:true});
  await page.locator('.validation-progress').screenshot({path:path.join(out,'dataset-latest-report-card.png')});
  const originalUrl=page.url();
  await page.getByRole('button',{name:'上次完整测试 · 37/37',exact:true}).click();
  await page.getByText('37 / 37',{exact:true}).waitFor();
  await page.getByText('查看 1 项字段比对',{exact:true}).click();
  await page.locator('.validation-fact-check').getByText('original.pdf · assets · 2024-12-31',{exact:true}).waitFor();
  assert.equal(page.url(),originalUrl);assert.equal(context.pages().length,1);
  assert.equal(apiRequests.filter(r=>r.method==='POST').length,0);
  passed('历史报告按钮在当前页面加载流程和字段结果，不打开新页或重新运行');
  await page.screenshot({path:path.join(out,'dataset-history-report.png'),fullPage:true});
  await page.locator('.validation-progress').screenshot({path:path.join(out,'dataset-history-report-card.png')});
  assert.equal(await page.evaluate(()=>localStorage.getItem('finance.validation')),'older');
  await page.getByRole('button',{name:'返回对话',exact:true}).click();
  await page.getByRole('heading',{name:'今天想研究什么？'}).waitFor();
  await page.getByRole('button',{name:'数据集与测试',exact:true}).click();
  await page.getByText('35 / 37',{exact:true}).waitFor();
  assert.ok(apiRequests.filter(r=>r.path==='/api/benchmark/run/latest').length>=2);
  assert.equal(apiRequests.filter(r=>r.method==='POST').length,0);
  passed('回访时即使 localStorage 保存旧报告，也默认显示服务端最新报告');
  await page.getByText('开发回归与历史结果',{exact:true}).click();
  await page.getByRole('button',{name:'快速端到端测试',exact:true}).click();
  await page.getByText('测试正在运行',{exact:true}).waitFor();
  const progress=page.locator('.validation-progress');
  await progress.getByText('会话 1：正在规范字段；会话 2：正在建立资料索引',{exact:true}).waitFor();
  const visible=await progress.innerText();assert.ok(!visible.includes('INTERNAL_LOG_SENTINEL'));assert.ok(!visible.includes('{'));assert.ok(!visible.includes('implementation'));
  assert.equal(await page.getByRole('button',{name:'快速端到端测试',exact:true}).isEnabled(),false);
  await page.screenshot({path:path.join(out,'dataset-natural-progress.png'),fullPage:true});
  finish=true;await page.getByText('测试运行完成',{exact:true}).waitFor();assert.ok(polls>0);
  passed('运行进度使用各会话自然语言阶段，原始 JSON 和内部日志不出现在产品界面');
  assert.equal(await page.getByRole('link',{name:'查看设计与评分方法'}).getAttribute('href'),'/api/benchmark/design');
  await page.getByRole('button',{name:'完整开发回归',exact:true}).waitFor();
  for(const mode of ['financial_v05','generic_v05','correction_v01']){expectedMode=mode;finish=false;await page.getByLabel('选择测试组').selectOption(mode);await page.getByRole('button',{name:'运行或查看首次结果',exact:true}).click();await page.getByText('测试正在运行',{exact:true}).waitFor();finish=true;await page.getByText('测试运行完成',{exact:true}).waitFor();}
  passed('金融整表、通用Pi对照及研报纠错各发送正确独立模式，旧回归独立保留');
  assert.deepEqual(errors,[]);assert.ok(apiRequests.every(r=>r.method==='GET'||r.path==='/api/benchmark/run'));
  passed('所有 API 均由浏览器 fixture 响应，无真实会话、模型调用或浏览器异常');
  fs.writeFileSync(path.join(out,'browser-dataset-reports-results.json'),JSON.stringify({checked_at:new Date().toISOString(),scope:'Controlled browser API fixtures only; no real model requests.',passed:checks.length,checks,computedColors:colors,apiRequests,pageErrors:errors},null,2));
 }catch(error){await page.screenshot({path:path.join(out,'dataset-reports-failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'browser-dataset-reports-failure.json'),JSON.stringify({error:String(error.stack||error),checks,apiRequests},null,2));throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

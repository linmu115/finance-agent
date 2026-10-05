// Exercise the single running service; no additional server or synthetic production records.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chooseProject}=require('./project-navigation.cjs');
(async()=>{
 const root=path.resolve('data/acceptance/asset-dashboard'),base='http://127.0.0.1:3001';
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true}),checks=[];
 const smoke=process.argv.includes('--smoke');
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByText('服务已连接',{exact:true}).waitFor();
  if(width<700)await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  await chooseProject(page,manifest.project.id);
  assert.equal(await page.locator('.sidebar').getByRole('button',{name:'财报看板',exact:true}).count(),0);
  assert.equal(await page.locator('.sidebar').getByRole('button',{name:'研究成果',exact:true}).count(),0);
  await page.getByRole('button',{name:'资产看板',exact:true}).click();
  await page.getByRole('heading',{name:'资产看板',exact:true}).waitFor();
  await page.locator('.asset-summary').waitFor();
  const catalog=await (await page.request.get(`${base}/api/projects/${manifest.project.id}/assets/catalog`)).json();
  assert.ok(catalog.summary.documents>=1);
  await page.screenshot({path:path.join(root,`assets-overview-${width}${smoke?'-smoke':''}.png`),fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'page must not overflow horizontally');
  const nav=page.getByRole('navigation',{name:'资产分类'});
  await nav.getByRole('button',{name:'机构预期',exact:true}).click();
  await page.getByRole('region',{name:'机构预测与公司指引'}).waitFor();
  if(!smoke){
   await page.locator('.asset-table-scroll tbody tr').first().waitFor();
   assert.ok(catalog.summary.forecasts>0);
   await page.getByLabel('报告发布日期截至',{exact:true}).fill('2025-07-15');
   await page.getByRole('heading',{name:'当前筛选下没有记录',exact:true}).waitFor();
   await page.getByLabel('报告发布日期截至',{exact:true}).fill('2025-07-16');
   const row=page.locator('.asset-table-scroll tbody tr').first();await row.waitFor();
   assert.match(await row.innerText(),/国信证券/);assert.match(await row.innerText(),/2025-07-16/);
   await row.getByRole('button',{name:'原文',exact:true}).click();await page.locator('.attachment-source').waitFor();
   await page.getByRole('button',{name:'关闭附件流向',exact:true}).click();
   await page.screenshot({path:path.join(root,`assets-forecasts-${width}.png`),fullPage:true});
   await row.getByRole('checkbox').check();await page.getByRole('button',{name:'就此分析（1）',exact:true}).click();
   const draft=await page.locator('textarea').inputValue();assert.match(draft,/record_id/);assert.match(draft,/2025-07-16/);assert.match(draft,/analyst_forecast|company_guidance/);
   // This is a private browser used for checks. Never submit the test draft.
   if(width<700)await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
   await page.getByRole('button',{name:'资产看板',exact:true}).click();await page.locator('.asset-summary').waitFor();
   const financialEntity=catalog.entities.find(e=>e.facts>0);assert.ok(financialEntity);
   await page.getByLabel('研究对象',{exact:true}).selectOption(financialEntity.key);
   await page.locator('.asset-object-bar>span').filter({hasText:financialEntity.name}).waitFor({state:'attached'});
   await nav.getByRole('button',{name:'财务与经营',exact:true}).click();
   await page.locator('.dashboard-data tbody tr').first().waitFor();
   const rows=await page.locator('.dashboard-data tbody tr td:first-child').allTextContents();
   assert.ok(rows.every(row=>financialEntity.companies.some(name=>row.includes(name))));
   await page.getByRole('button',{name:'利润表',exact:true}).click();
   await page.locator('.financial-chart-wrap svg').waitFor();
   const chartLabels=await page.locator('.financial-chart-wrap [role="button"]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-label')).join('\n'));
   assert.match(chartLabels,/181,011,000/);assert.match(chartLabels,/120,392,000/);
   await page.locator('.dashboard-chart').scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(root,`assets-financial-${width}.png`),fullPage:true});
   await page.getByLabel('研究对象',{exact:true}).selectOption('');
   await nav.getByRole('button',{name:'模型与成果',exact:true}).click();
   await page.getByRole('navigation',{name:'研究成果分类'}).waitFor();
   const artifacts=(await (await page.request.get(`${base}/api/projects/${manifest.project.id}/research/artifacts`)).json()).artifacts;
   assert.ok(artifacts.filter(a=>a.kind==='dcf').length>=2,'two saved DCF scenarios must exist');
   assert.ok(artifacts.some(a=>a.kind==='financial_quality'),'saved financial quality model must exist');
   const dcf=artifacts.find(a=>a.kind==='dcf');
   await page.getByRole('complementary',{name:'研究成果列表'}).getByRole('button').filter({hasText:dcf.title}).click();
   await page.getByRole('region',{name:'计算结果'}).waitFor();
   assert.equal(await page.getByLabel('模型名称',{exact:true}).inputValue(),dcf.title);
   const model=await (await page.request.get(`${base}/api/projects/${manifest.project.id}/research/artifacts/${dcf.id}`)).json();
   const perShare=page.locator('.rw-kpis>div').filter({has:page.getByText('每股价值',{exact:true})}).locator('strong');
   assert.equal(await perShare.getAttribute('title'),String(model.result.results.value_per_share));
   assert.ok(await page.getByRole('button',{name:'重算并保存新版本',exact:true}).isEnabled());
   const csvLink=page.getByRole('link',{name:'导出此版本输入 CSV',exact:true});
   assert.equal((await page.request.get(new URL(await csvLink.getAttribute('href'),base).href)).status(),200);
   await page.getByRole('region',{name:'计算结果'}).scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(root,`assets-models-${width}.png`),fullPage:true});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'populated models must not overflow page horizontally');
   await nav.getByRole('button',{name:'总览',exact:true}).click();
   await page.locator('.asset-result-card').filter({hasText:dcf.title}).click();
   await page.getByRole('region',{name:'计算结果'}).waitFor();
   assert.equal(await page.getByLabel('模型名称',{exact:true}).inputValue(),dcf.title,'overview must open the selected model');
  }
  for(const name of ['观点与证据','模型与成果','财务与经营']){await nav.getByRole('button',{name,exact:true}).click();}
  assert.deepEqual(errors,[]);checks.push({width,singleNavigation:true,projectId:manifest.project.id,summary:catalog.summary,errors,smoke});await page.close();
 }
 fs.writeFileSync(path.join(root,`browser-${smoke?'smoke':'final'}.json`),JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

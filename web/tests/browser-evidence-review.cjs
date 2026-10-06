// Real read-only data on 3001. The model panel uses a separately labelled,
// deterministic result fixture; no persisted artifact or conversation is changed.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chooseProject}=require('./project-navigation.cjs');
const base='http://127.0.0.1:3001',out=path.resolve('data/retests/iteration-20261005');
fs.mkdirSync(out,{recursive:true});
const project=process.env.FINANCE_TEST_PROJECT||JSON.parse(fs.readFileSync('data/acceptance/asset-dashboard/manifest.json','utf8')).project.id;
const python=process.env.FINANCE_PYTHON||path.resolve('.venv/Scripts/python.exe');
const fixture=JSON.parse(execFileSync(python,['-c',[
 'import json',
 'from service.research_models import evaluate_model',
 'from service.research_schema import get_model_example',
 'spec=get_model_example("dcf")',
 'spec["input_basis"]["terminal.ebit_margin"]={"basis":"disclosed","source_kind":"analyst_forecast","rationale":"Fixed browser fixture"}',
 'print(json.dumps({"dcfResult":evaluate_model("dcf",spec)}))',
].join('\n')],{encoding:'utf8',windowsHide:true}));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),checks=[];
 try{
  for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:1050}}),errors=[],writes=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    if(route.request().method()!=='GET'){writes.push(route.request().url());return route.abort();}
    await route.continue();
   });
   await page.goto(base);await page.getByText('服务已连接',{exact:true}).waitFor();
   if(width<700)await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
   await chooseProject(page,project);
   const openDashboard=async()=>{
    if(width<700&&!await page.locator('.app').evaluate(node=>node.classList.contains('mobile-sidebar')))await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
    await page.getByRole('button',{name:'资产看板',exact:true}).click();
    await page.locator('.asset-summary').waitFor();
   };
   await openDashboard();
   const catalog=await (await page.request.get(`${base}/api/projects/${project}/assets/catalog`)).json();
   const financial=catalog.documents.find(d=>d.kind==='financial_report');
   const research=catalog.documents.find(d=>d.kind==='broker_research');
   assert.equal(financial.review.extraction_issues,6);
   assert.equal(research.review.records_needing_review,99);
   const financialCard=page.locator('.asset-source-card').filter({has:page.getByRole('heading',{name:financial.title,exact:true})});
   const review=financialCard.locator('.evidence-review');
   assert.equal(await review.getAttribute('open'),null,'details collapsed by default');
   await review.locator('summary').click();await review.locator('article').first().waitFor();
   assert.equal(await review.locator('article').count(),6);
   await review.getByRole('button',{name:'核对原文',exact:true}).first().click();
   await page.locator('.attachment-source .page-text').waitFor();
   const original=(await (await page.request.get(`${base}/api/projects/${project}/documents/${financial.document_id}/normalization?review_only=true&limit=10`)).json()).items[0];
   assert.match(await page.locator('.attachment-source .page-controls').innerText(),new RegExp(`第 ${original.source.page} 页`));
   await page.getByRole('button',{name:'关闭附件流向',exact:true}).click();
   await review.scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(out,`evidence-financial-${width}.png`),fullPage:true});
   await review.getByRole('button',{name:'带入会话',exact:true}).first().click();
   const draft=await page.locator('textarea').inputValue();
   assert.ok(draft.includes(financial.document_id)&&draft.includes('局部核验'));
   assert.equal(writes.length,0,'draft is never sent');
   await openDashboard();
   const researchCard=page.locator('.asset-source-card').filter({has:page.getByRole('heading',{name:research.title,exact:true})});
   const researchReview=researchCard.locator('.evidence-review');
   await researchReview.locator('summary').click();await researchReview.locator('article').first().waitFor();
   assert.equal(await researchReview.locator('article').count(),10);
   const firstText=await researchReview.locator('article').first().innerText();
   await Promise.all([page.waitForResponse(response=>response.url().includes('/normalization?')&&response.url().includes('offset=10')),researchReview.getByRole('button',{name:'下一页',exact:true}).click()]);
   await researchReview.locator('article').first().waitFor();
   assert.notEqual(await researchReview.locator('article').first().innerText(),firstText);
   await Promise.all([page.waitForResponse(response=>response.url().includes('/normalization?')&&decodeURIComponent(response.url()).includes('query=期间')),researchReview.getByRole('textbox').fill('期间')]);
   await researchReview.locator('article').first().waitFor();
   assert.match(await researchReview.innerText(),/期间待确认/);
   await researchReview.scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(out,`evidence-research-${width}.png`),fullPage:true});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no page horizontal overflow');
   const nav=page.getByRole('navigation',{name:'资产分类'});
   await nav.getByRole('button',{name:'机构预期',exact:true}).click();
   await Promise.all([page.waitForResponse(response=>response.url().includes('/assets/records?')&&decodeURIComponent(response.url()).includes('"quality":"needs_review"')),page.getByLabel('研报核验状态',{exact:true}).selectOption('needs_review')]);
   await page.locator('.asset-table-scroll tbody tr').first().waitFor();
   assert.match(await page.getByRole('region',{name:'机构预测与公司指引'}).innerText(),/24 条/);
   await nav.getByRole('button',{name:'财务与经营',exact:true}).click();
   await Promise.all([page.waitForResponse(response=>response.url().includes('/financial-data?')&&decodeURIComponent(response.url()).includes('needs_review')),page.getByLabel('财报核验状态',{exact:true}).selectOption('review')]);
   await page.waitForFunction(()=>document.querySelector('.dashboard-data tbody tr')===null);
   // Existing saved models are historical, so preview new metadata only in
   // this private browser response. The real calculator produced the fixture.
   const artifacts=(await (await page.request.get(`${base}/api/projects/${project}/research/artifacts`)).json()).artifacts;
   const model=artifacts.find(a=>a.kind==='dcf');assert.ok(model);
   await page.route(`**/api/projects/${project}/research/artifacts/${model.id}`,async route=>{
    const response=await route.fetch(),body=await response.json();
    body.result.checks=fixture.dcfResult.checks;body.result.input_usage=fixture.dcfResult.input_usage;
    await route.fulfill({response,json:body});
   });
   await nav.getByRole('button',{name:'模型与成果',exact:true}).click();
   await page.getByRole('complementary',{name:'研究成果列表'}).getByRole('button').filter({hasText:model.title}).click();
   const modelReview=page.getByLabel('模型核验依据',{exact:true});await modelReview.waitFor();
   assert.equal(await modelReview.getAttribute('open'),null);
   await modelReview.locator('summary').click();
   assert.match(await modelReview.innerText(),/机构预测/);
   assert.match(await modelReview.innerText(),/长期估值假设/);
   await modelReview.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,`model-review-fixture-${width}.png`),fullPage:true});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
   checks.push({width,project,liveEvidence:true,originalPage:true,draftOnly:true,reviewPagination:true,qualityFilters:true,modelPanel:'deterministic_fixture_readonly',errors,writes});
   await page.close();
  }
  fs.writeFileSync(path.join(out,'browser-evidence-review.json'),JSON.stringify(checks,null,2));
  console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

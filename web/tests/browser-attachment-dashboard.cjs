// Browser fixtures use the built 3001 page; no real project deletion or model calls.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const output=path.resolve('web/test-results/attachment-dashboard');fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let removed=false,deletions=0;
  const docs=[{id:'financial',name:'示例公司 2025 中期财报.pdf',status:'ready',pageCount:55,factCount:732,researchRecordCount:0,createdAt:'2026-10-06',profile:{kind:'financial_report'}},{id:'research',name:'研究机构 公司首次覆盖研报.pdf',status:'needs_review',pageCount:47,factCount:0,researchRecordCount:2285,createdAt:'2026-10-06',profile:{kind:'broker_research',publisher:'示例机构',published_at:'2024-11-08'}}];
  await page.route('**/api/**',route=>{
   const req=route.request(),url=new URL(req.url()).pathname;
   if(req.method()==='DELETE'){assert.equal(url,'/api/projects/p/documents/financial');assert.deepEqual(req.postDataJSON(),{confirm_document_id:'financial'});deletions++;removed=true;return route.fulfill({contentType:'application/json',body:'{"removed":{"facts":732}}'});}
   assert.equal(req.method(),'GET');
   const data=url==='/api/projects'?{projects:[{id:'p',name:'附件看板界面样例'}]}:url==='/api/settings'?{llm:{model:'界面样例'}}:url==='/api/health'?{ok:true,service:'connected'}:url==='/api/approvals'?{requests:[]}:url.endsWith('/documents')?{documents:removed?docs.slice(1):docs}:url.endsWith('/conversations')?{conversations:[]}:{};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('http://127.0.0.1:3001/');
  await page.getByRole('button',{name:'附件看板',exact:true}).click();
  await page.getByRole('article',{name:docs[0].name}).waitFor();
  assert.equal(await page.getByRole('button',{name:'数据集与测试'}).count(),0);
  await page.getByRole('article',{name:docs[0].name}).getByRole('button',{name:'删除',exact:true}).click();
  assert.equal(deletions,0);
  await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
  await page.getByRole('button',{name:'取消',exact:true}).click();assert.equal(deletions,0);
  await page.getByRole('article',{name:docs[0].name}).getByRole('button',{name:'删除',exact:true}).click();
  await page.getByRole('button',{name:'确认删除',exact:true}).click();
  await page.getByRole('status').filter({hasText:'已删除'}).waitFor();assert.equal(deletions,1);
  assert.equal(await page.getByRole('article').count(),1);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({status:'passed',real_data_mutations:0,api_fixtures:true,viewports:[1440,390],confirmation:true,deletions,errors},null,2));
  console.log('Attachment dashboard: desktop/mobile, confirmation, cancel, deletion and retained sibling passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

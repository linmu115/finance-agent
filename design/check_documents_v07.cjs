const {chromium}=require('playwright');
const {pathToFileURL}=require('node:url');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');

(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const checks=[],errors=[],network=[];
 const directory=path.join(__dirname,'preview');fs.mkdirSync(directory,{recursive:true});
 const historical={
  'architecture-v0.3-20261003.html':'b88bd6d9f7ba1a493e59bccd05b85fbc59b94cc3a40069cb892065ec09fe33e9',
  'roadmap-20261003-before-v07.html':'d35b7be4a2503a53fea561fb38de87ced6af60bac7a15e236f8547b77fd3a535'
 };
 try{
  const context=await browser.newContext();
  await context.route(/^https?:/,route=>{network.push(route.request().url());return route.abort();});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  for(const file of ['architecture.html','roadmap.html']){
   await page.goto(pathToFileURL(path.join(__dirname,file)).href);
   const text=await page.locator('body').innerText();
   assert.match(text,/v07/);assert.match(text,/实际公司/);assert.match(text,/正式整表/);assert.match(text,/未完成|待验/);
   if(file==='architecture.html'){
    assert.equal(await page.locator('.tools-grid .node').count(),6);
    assert.match(await page.locator('.tools-grid').innerText(),/联网取证/);
    assert.match(await page.locator('#research-flow').innerText(),/证据 → 模型 → 备忘录/);
    assert.match(text,/API 配置/);assert.match(text,/来源|原文/);assert.match(text,/stale/);
    assert.ok(!text.includes('上述 15 个业务工具'));
   }else{
    for(const content of ['业绩归因与盈利质量','研报纠错与反向核验','可调整的估值模型','投资观点与反证条件','同行比较、事件更新和产业链传导','扩容时按瓶颈升级'])assert.ok(text.includes(content));
    assert.equal(await page.locator('.progress').count(),5);
   }
   const links=await page.locator('a[href]').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href')));
   for(const href of links.filter(href=>!/^https?:|^#/.test(href))){
    const target=path.resolve(__dirname,decodeURIComponent(href.split('#')[0]));assert.ok(fs.existsSync(target),file+' broken local link '+href);
   }
   checks.push({file,check:'content_and_local_links',links:links.length,status:'passed'});
   for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
    await page.setViewportSize(viewport);await page.evaluate(()=>scrollTo(0,0));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,file+' overflow '+viewport.width);
    const nodes=await page.locator('.node').evaluateAll(nodes=>nodes.map(node=>({left:node.getBoundingClientRect().left,right:node.getBoundingClientRect().right})));
    assert.ok(nodes.every(node=>node.left>=0&&node.right<=viewport.width),file+' diagram bounds '+viewport.width);
    if(viewport.width!==768)await page.screenshot({path:path.join(directory,file.replace('.html','')+'-v07-'+(viewport.width===390?'mobile':'desktop')+'.png')});
    checks.push({file,check:'layout',viewport,status:'passed'});
   }
   if(file==='architecture.html'){
    await page.locator('#research-flow').screenshot({path:path.join(directory,'architecture-v07-research-mobile.png')});
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#runtime').screenshot({path:path.join(directory,'architecture-v07-runtime-desktop.png')});
   }
  }
  for(const [file,expected] of Object.entries(historical))assert.equal(createHash('sha256').update(fs.readFileSync(path.join(__dirname,file))).digest('hex'),expected);
  assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
  const result={status:'passed',at:new Date().toISOString(),scope:'static architecture and roadmap documents only',checks,historical_sha256:historical,external_requests:network,model_calls:0,server_lifecycle_changes:0,page_errors:errors};
  fs.writeFileSync(path.join(directory,'documents-v07-verification.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({status:result.status,checks:checks.length,historical_files:2,external_requests:network.length}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

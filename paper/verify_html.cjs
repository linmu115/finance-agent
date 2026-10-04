const {chromium}=require('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1400,height:1100},deviceScaleFactor:1});
 await page.goto(pathToFileURL(path.join(__dirname,'financial_analysis_paper_v0.1.html')).href);
 await page.screenshot({path:path.join(__dirname,'render/html-desktop.png')});
 const report=await page.evaluate(()=>({title:document.title,horizontalOverflow:document.documentElement.scrollWidth>innerWidth,tables:document.querySelectorAll('table').length,images:[...document.images].map(i=>({complete:i.complete,naturalWidth:i.naturalWidth})),hasDeepSeek:document.body.innerText.includes('deepseek-flash'),bodyLength:document.body.innerText.length}));
 fs.writeFileSync(path.join(__dirname,'render/html-qa.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
 await browser.close();
 if(report.horizontalOverflow||report.images.some(i=>!i.complete||i.naturalWidth===0))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});

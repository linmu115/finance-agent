// Exercise the isolated candidate build. Every response is intercepted; no production API or asset is read.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1200,height:900}});
 const chat={id:'fixture-chat',projectId:'fixture-project',title:'题给事实来源验收',messages:[
  {id:'question-1',role:'user',content:'2024 年收入 1120 百万元。'},
  {id:'answer',role:'assistant',content:'【事实/用户提供】2024 年收入 1120 百万元（user:question-1）。',status:'completed',sources:[{kind:'user_provided',sourceId:'user:question-1',messageId:'question-1',documentId:'',title:'用户提供',quote:'2024 年收入 1120 百万元。'}]}
 ]};
 const errors=[];page.on('pageerror',e=>errors.push(e.message));const requests=[];
 await page.route('**/*',async route=>{
  const uri=new URL(route.request().url()).pathname;requests.push(uri);
  const send=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  if(uri==='/api/projects')return send({projects:[{id:chat.projectId,name:'来源测试'}]});
  if(uri==='/api/settings')return send({llm:{model:'fixture',hasKey:false},embedding:{enabled:false},ocr:{mode:'local'},runtime:{}});
  if(uri==='/api/health')return send({ok:true});
  if(uri.endsWith('/documents'))return send({documents:[]});
  if(uri.endsWith('/conversations'))return send({conversations:[chat]});
  if(uri==='/api/conversations/'+chat.id)return send(chat);
  if(uri.startsWith('/api/'))return send({});
  if(uri==='/'||uri.startsWith('/assets/'))return route.fulfill({path:path.join('tmp/period-basis-merge-web',uri==='/'?'index.html':uri.slice(1))});
  return route.abort();
 });
 try{
  await page.goto('http://127.0.0.1:3001');
  await page.getByText(chat.title,{exact:true}).click();
  await page.getByRole('button',{name:'1. 用户提供',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'用户提供的来源'});await dialog.waitFor();
  assert.ok((await dialog.textContent()).includes('2024 年收入 1120 百万元。'));
  assert.ok(!requests.some(r=>r.includes('/sources/')||r.includes('/pages/')));
  assert.deepEqual(errors,[]);
  const folder='docs/evidence/period-basis-merge-20261008';
  await page.screenshot({path:path.join(folder,'user-source.png')});
  await fs.writeFile(path.join(folder,'ui-validation.json'),JSON.stringify({scope:'isolated build, intercepted UI fixture only',user_source_quote_visible:true,production_requests:0,page_errors:errors},null,2));
  console.log('User source label, source quote modal and browser runtime: passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

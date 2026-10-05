// Browser assertions use controlled API fixtures; native Pi behavior is covered
// separately by tests/pi-native-integration.test.ts.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],requests=[],uploads=[],documents=[];page.on('pageerror',e=>errors.push(e.message));
 let settings={llm:{provider:'openai-compatible',baseUrl:'https://example.com/v1',model:'legacy',contextWindow:128000,maxTokens:32768,hasKey:true},embedding:{enabled:false,baseUrl:'',model:''},ocr:{mode:'local',baseUrl:'',model:''},search:{provider:'tavily',baseUrl:'https://api.tavily.com',maxResults:6},runtime:{timeoutSeconds:120,contextCompaction:{enabled:true,mode:'auto',targetTokens:96000,keepRecentTokens:24000}}};
 const chat={id:'native-chat',projectId:'native-project',title:'Native UI fixture',messages:[]};let release;const finished=new Promise(r=>release=r);
 await page.route('**/api/**',async route=>{
  const req=route.request(),uri=new URL(req.url()).pathname,method=req.method();const respond=v=>route.fulfill({contentType:'application/json',body:JSON.stringify(v)});
  if(uri==='/api/health')return respond({ok:true});
  if(uri==='/api/projects')return respond({projects:[{id:'native-project',name:'原生会话验收'}]});
  if(uri==='/api/models')return respond({path:'fixture/.pi/agent/models.json',models:[{provider:'catalog-fixture',id:'model-a',name:'Catalog Model A',reasoning:true,contextWindow:1000000,maxTokens:64000,configured:true}]});
  if(uri==='/api/settings'){if(method==='PUT')settings=req.postDataJSON();return respond(settings);}
  if(uri.endsWith('/conversations'))return respond(method==='POST'?chat:{conversations:chat.messages.length?[chat]:[]});
  if(uri.endsWith('/uploads')){
   const count=(req.postData()||'').match(/name="files"/g)?.length||0;uploads.push(count);
   const batch=Array.from({length:count},()=>{const d={id:'doc-'+documents.length,name:'file-'+documents.length+'.csv',status:'registered'};documents.push(d);return d;});return respond({documents:batch});
  }
  if(uri.endsWith('/documents'))return respond({documents});
  if(uri.endsWith('/messages')){
   const body=req.postDataJSON();requests.push(body);const i=requests.length;chat.messages.push({id:'u'+i,role:'user',content:body.content,attachments:body.documentIds,status:i>1?'queued':undefined});chat.activeRunId='native-run';
   return respond({runId:'native-run',messageId:'a1',userMessageId:'u'+i,inputStatus:i>1?'queued':undefined});
  }
  if(uri.endsWith('/events')){
   await finished;const events=[];
   for(let i=1;i<=requests.length;i++){
    const answer={id:'a'+i,role:'assistant',content:'reply-'+i,status:'completed'};chat.messages.push(answer);
    if(i>1)events.push(['answer_start',{message:{...answer,content:'',status:'running'}}]);
    events.push(['delta',{messageId:answer.id,text:answer.content}],['message',{message:answer}]);
   }
   delete chat.activeRunId;events.push(['done',{status:'completed'}]);return route.fulfill({contentType:'text/event-stream',body:events.map(([event,data],i)=>`id: ${i+1}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('')});
  }
  if(uri==='/api/conversations/native-chat')return respond(chat);
  return respond({items:[],requests:[]});
 });
 try{
  await page.goto(process.env.WEB_TEST_URL||'http://127.0.0.1:5174');const input=page.getByLabel('发送给金融 Agent 的消息');await input.fill('initial task');await input.press('Enter');await page.getByLabel('停止生成',{exact:true}).waitFor();
  await input.fill('steer while running');assert.equal(await page.getByLabel('发送补充',{exact:true}).isEnabled(),true);await input.press('Enter');await page.getByText('steer while running',{exact:true}).waitFor();
  const files=Array.from({length:9},(_,i)=>({name:`file-${i}.csv`,mimeType:'text/csv',buffer:Buffer.from('year,value\n2024,1')}));await page.locator('input[type=file]').setInputFiles(files);await page.waitForFunction(()=>document.querySelectorAll('.attachments .file-chip').length===9);
  await input.fill('follow up after completion');await input.press('Alt+Enter');await page.getByText('follow up after completion',{exact:true}).waitFor();
  await page.locator('[data-message-id="u3"]').waitFor();assert.equal(requests.length,3);assert.deepEqual(requests.map(r=>r.mode),['steer','steer','followUp']);assert.equal(requests[2].documentIds.length,9);assert.deepEqual(uploads,[8,1]);assert.equal(await page.getByText('已保存，等待接入当前任务',{exact:true}).count(),2);
  release();await page.getByText('reply-3',{exact:true}).waitFor();await page.waitForFunction(()=>!document.querySelector('[aria-label="停止生成"]'));
  for(let i=1;i<=3;i++)assert.equal(await page.locator(`[data-message-id="a${i}"]`).count(),1);
  await page.getByRole('button',{name:'API 配置',exact:true}).click();await page.locator('#llm-provider').selectOption('catalog-fixture');assert.equal(await page.locator('#llm-catalog-model').inputValue(),'model-a');assert.equal(await page.locator('#llm-baseUrl').count(),0);
  await page.getByText('高级设置 · 上下文与价格',{exact:true}).click();assert.equal(await page.locator('#llm-context').inputValue(),'1000000');assert.equal(await page.locator('#llm-context').isDisabled(),true);
  await page.getByRole('button',{name:'保存设置',exact:true}).click();await page.getByText(/设置已保存/).waitFor();assert.equal(settings.llm.provider,'catalog-fixture');assert.equal(settings.llm.apiKey,'');
  await page.getByRole('button',{name:'运行限制',exact:true}).click();await page.getByText('长会话 · 上下文压缩',{exact:true}).click();assert.equal(await page.locator('#context-summary').count(),0);assert.equal(await page.locator('#runtime-maxTools').count(),0);
  assert.deepEqual(errors,[]);const output=path.resolve('data/retests/pi-native-20261004');fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'native-settings.png')});
  await page.getByLabel('关闭设置').click();await page.screenshot({path:path.join(output,'native-conversation.png')});
  console.log('PASS native message controls, 9-file upload in 2 requests, distinct assistant responses, global model selection, no summary override, no browser exceptions');
 }finally{release();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

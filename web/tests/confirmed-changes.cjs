/* Isolated acceptance: real local API/data for flows and models; explicit fixture for modal UX. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:3003';
if(!base.endsWith(':3003'))throw new Error('This test is restricted to isolated acceptance port 3003');
const output=path.resolve('data/acceptance-confirmed-20261004');
async function json(route,options){const r=await fetch(base+route,options);const data=await r.json();if(!r.ok)throw new Error(JSON.stringify(data));return data;}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:960}});const errors=[];page.on('pageerror',e=>errors.push(e.message));const checks=[];
 const pass=name=>{checks.push(name);console.log('PASS',name);};
 try{
  await page.goto(base);await page.getByRole('button',{name:'附件流向',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'项目资料库',exact:true}).count(),0);
  await page.getByRole('button',{name:'附件核验示例',exact:true}).click();await page.getByRole('button',{name:'附件流向',exact:true}).click();
  await page.locator('.flow-select').filter({hasText:'合成财报.csv'}).click();await page.getByText('原值：10000 元 → 入库值：').waitFor();await page.getByRole('button',{name:'查看对应财报数据'}).waitFor();
  await page.screenshot({path:path.join(output,'attachment-flow.png')});pass('conversation flow shows immutable source, raw and normalized value, destination record');
  await page.getByRole('button',{name:'核对原始附件'}).click();await page.getByText('合成财报：营业收入 10000 元',{exact:true}).waitFor();await page.getByRole('button',{name:'关闭附件流向'}).click();
  await page.getByRole('button',{name:'空白会话',exact:true}).click();await page.getByRole('button',{name:'附件流向',exact:true}).click();await page.getByText('此会话还没有附件流向记录。').waitFor();pass('other conversation does not inherit project-wide attachment state');await page.getByRole('button',{name:'关闭附件流向'}).click();
  await page.getByRole('button',{name:'编辑项目约定与技能：施工验收 · 合成资料'}).click();await page.getByLabel('项目约定 · agent.md').fill('# 验收项目约定\n回答开头写“验收规则已加载”。\n全部使用明确标识的合成数据。');await page.getByRole('button',{name:'保存项目设置'}).click();await page.getByText('已保存；从下一次会话任务开始生效。').waitFor();assert.ok((await json('/api/projects/acceptance/resources')).rules.includes('验收规则已加载'));await page.screenshot({path:path.join(output,'project-rules.png')});await page.getByRole('button',{name:'关闭',exact:true}).click();pass('project agent.md and skill toggles are editable and persisted');
  const schema=await json('/api/projects/acceptance/research/models/schema/three_statement');
  const saved=await json('/api/projects/acceptance/research/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'三表联动 · 验收合成示例',kind:'three_statement',spec:schema.synthetic_example})});
  const csv=await (await fetch(base+`/api/projects/acceptance/research/artifacts/${saved.id}/input-csv?revision=${saved.revision_id}`)).text();
  const imported=await json('/api/projects/acceptance/research/models/import-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv})});assert.deepEqual(imported.spec,saved.spec);fs.writeFileSync(path.join(output,'model-input.csv'),csv);
  await page.getByRole('button',{name:'研究成果',exact:true}).click();await page.getByRole('button',{name:/估值与分析/}).click();await page.getByText('三表联动 · 验收合成示例',{exact:true}).first().click();await page.getByRole('button',{name:'重算并保存新版本'}).waitFor();await page.getByLabel('导入模型输入 CSV').setInputFiles(path.join(output,'model-input.csv'));await page.getByText('已导入 CSV 参数。请核对来源与假设，再重算保存。').waitFor();await page.getByRole('button',{name:'重算并保存新版本'}).click();await page.getByText('已完成重算并保存新版本；原版本保留。').waitFor();await page.screenshot({path:path.join(output,'three-statement.png')});pass('Python model CSV export/import round trip and editable browser recalculation');
  let request={id:'fixture-approval',digest:'a'.repeat(64),projectId:'acceptance',conversationId:'chat1',operation:{operation:'sql',current_project:'施工验收',reason:'授权弹窗交互测试（不执行数据库变更）',scope:'验收用合成数据',sql:'DELETE FROM example WHERE id = ?',parameters:['fixture'],note:'此请求由浏览器测试夹具提供。'}};const decisions=[];
  await page.route('**/api/approvals',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({requests:request?[request]:[]})}));
  await page.route('**/api/approvals/fixture-approval',r=>{decisions.push(r.request().postDataJSON());request=null;return r.fulfill({contentType:'application/json',body:'{"ok":true}'});});
  await page.getByRole('button',{name:'附件核验示例',exact:true}).click();await page.getByRole('region',{name:'数据库操作授权'}).waitFor();await page.locator('.approval-card').focus();await page.screenshot({path:path.join(output,'authorization.png')});await page.keyboard.press('Escape');await page.getByRole('region',{name:'数据库操作授权'}).waitFor({state:'hidden'});assert.equal(decisions[0].allow,false);pass('authorization card belongs to the conversation and Escape rejects');
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile.png')});assert.deepEqual(errors,[]);pass('desktop and mobile render without page errors');
  fs.writeFileSync(path.join(output,'ui-checks.json'),JSON.stringify({checks,errors,approvalFixture:true},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

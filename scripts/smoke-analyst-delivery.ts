// One authorized real conversation. Isolated data, same configured model, no extra HTTP service.
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
const output=path.resolve('data/evaluation/analyst-delivery-smoke-20261008');
await fs.mkdir(output); // Existing evidence means no second paid run.
process.env.FINANCE_DATA_DIR=path.join(output,'app-data');await fs.mkdir(process.env.FINANCE_DATA_DIR);
await fs.copyFile('data/active/settings.json',path.join(process.env.FINANCE_DATA_DIR,'settings.json'));
const {loadSettings,getSettings}=await import('../server/config.js');await loadSettings();
const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
const {exportReportPackage}=await import('../server/report-package.js');
const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
const prompt='请依据以下匿名制造企业的已核对输入，写一份简洁的财报分析：2023/2024 年收入分别为 1000/1120 百万元，归母净利润 80/84 百万元，经营现金流 95/70 百万元。比较收入、利润和现金表现，区分数据支持的结论与业务原因推论；未知原因不要编造。另按给定情景估值：估值日 2024-12-31，2025—2029 年 FCFF 为 75、81、87、93、99 百万元，WACC 9%，永续增长 2%，净债务 120 百万元，股份 100 百万股，年末折现。请保存数值底稿并给出关键数据、估值及适用条件，便于用会话的“财报分析报告”按钮导出。本题输入仅用于交付冒烟，不是真实公司披露。';
let summary:any={attempts:1,commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),model:getSettings().llm.model,prompt,started_at:new Date().toISOString(),status:'starting'};
await fs.writeFile(path.join(output,'result.json'),JSON.stringify(summary,null,2));
try{
 await service.call('create_project',{project_id:'analyst-smoke',name:'分析师交付冒烟'});
 const chat:any={id:randomUUID(),projectId:'analyst-smoke',title:'匿名制造企业财报分析',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
 await service.putState(chat.projectId,'conversations',chat.id,chat);manager.indexConversation(chat.id,chat.projectId);
 const started=await manager.start(chat,prompt,[]);summary={...summary,conversation_id:chat.id,run_id:started.id,status:'running'};
 await fs.writeFile(path.join(output,'result.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify({run_id:started.id,model:summary.model}));
 while(manager.activeFor(chat.id))await delay(1000);
 const run=await manager.getRun(started.id),conversation=await manager.getConversation(chat.id);
 await fs.writeFile(path.join(output,'conversation.json'),JSON.stringify(conversation,null,2));
 summary={...summary,status:run.status,usage:run.usage,error:run.error,finished_at:new Date().toISOString()};
 if(run.status==='completed'){
  const result=await exportReportPackage(service,conversation),folder=path.join(process.env.FINANCE_DATA_DIR!,path.dirname(result.relative_path));
  await fs.cp(folder,path.join(output,'package'),{recursive:true});summary.package=result;
 }
 await fs.writeFile(path.join(output,'result.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
 if(run.status!=='completed')process.exitCode=1;
}catch(error){summary={...summary,error:String(error),status:'failed'};await fs.writeFile(path.join(output,'result.json'),JSON.stringify(summary,null,2));throw error;}
finally{await manager.shutdown();await service.close();}

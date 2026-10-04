/** Bounded real-provider development check on two forks of one real conversation.
 * No gold/holdout inputs. Credentials stay in the ignored local DATA directory.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

const root = path.resolve(import.meta.dirname, '..');
const outputDir = path.join(root, 'benchmark/results/restore-v08-20261004');
const output = path.join(outputDir, 'compaction-live.json');
const privateData = path.join(root, 'data/compaction-acceptance-20261004');
const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
const prior = JSON.parse(await fs.readFile(path.join(outputDir, 'network-workflow.json'), 'utf8'));
if (prior.status !== 'passed') throw Error('Requires the completed live network workflow');
const originalSession = path.join(root, 'data/workspaces', prior.project_id, prior.conversation_id, 'sessions/session.jsonl');
const originalBytes = await fs.readFile(originalSession, 'utf8');
const tasks = [
  '复核上一轮得到的两个财务指标。先用 read_research_source 回读对应的已归档新闻原文，再给出公司、报告期间、营业总收入和归母净利润及单位，附实际来源ID。只回读已保存原文，不联网、不下载PDF、不清洗，不把检索摘要当原文。回答简洁。',
  '继续核对上轮的两个数值，并补充该新闻直接披露的同比增幅。再次回读已归档原文。指出这份新闻能否据此确定 EBIT 或利息收入与支出的大小关系，缺乏证据就明确说明。保持上一轮的单位与期间；不联网、不下载PDF、不清洗。回答简洁。',
];
const limits = {max_model_calls:8,max_input_tokens:180000,max_output_tokens:32000,max_total_tokens:212000,max_wall_seconds:360};
const protocol = {
  id:'v08-real-history-compaction-20261004', created_at:new Date().toISOString(),
  kind:'development_compaction_fork_comparison', original_run:prior.search_run_id,
  original_session_sha256:hash(originalBytes), tasks, per_arm_budget:limits,
  order:['disabled','enabled'], model:'deepseek-flash', context_window:1048576, max_output_tokens:8192,
  policy:{targetTokens:16000,keepRecentTokens:4000,summaryMaxTokens:2048},
  boundary:'Two local forks of the same genuine provider/tool history; lower trigger is an engineering smoke test, not the production 96k threshold or a held-out-company accuracy benchmark. Sequential order/cache warmth is not controlled. No monetary savings claim without verified pricing. Failed arms remain in this report; no automatic rerun.',
  acceptance:['source reread in each turn','correct period, numbers and units','no new search/download/processing','enabled checkpoint exists and exact source pointers survive','history prefix unchanged','all summary usage counted in budget','follow-up continues after RunManager restart'],
};
await fs.writeFile(path.join(outputDir,'compaction-protocol.json'),JSON.stringify(protocol,null,2),{flag:'wx'});
const report:any={protocol,status:'running',started_at:new Date().toISOString(),arms:[]};
await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
const save = () => fs.writeFile(output,JSON.stringify(report,null,2));
await fs.mkdir(privateData,{recursive:false});
await fs.copyFile(path.join(root,'data/settings.json'),path.join(privateData,'settings.json'));
await fs.cp(path.join(root,'data/research',prior.project_id),path.join(privateData,'research',prior.project_id),{recursive:true,errorOnExist:true});
process.env.FINANCE_DATA_DIR=privateData;
const {loadSettings,saveSettings,getSettings,redactError}=await import('../server/config.js');
const {FinanceService}=await import('../server/mcp.js');
const {RunManager}=await import('../server/runs.js');
await loadSettings();
if (getSettings().llm.model!==protocol.model || new URL(getSettings().llm.baseUrl).hostname!=='api.deepseek.com') throw Error('Configured provider differs from frozen protocol');
await saveSettings({llm:{maxTokens:8192},search:{apiKey:''}});
const service=new FinanceService();
let manager:InstanceType<typeof RunManager> | undefined;
try {
  await service.connect();
  await service.call('create_project',{project_id:prior.project_id,name:'真实会话压缩对照 · 独立数据'});
  for (const enabled of [false,true]) {
    await saveSettings({runtime:{contextCompaction:{enabled,...protocol.policy}}});
    manager=new RunManager(service);
    const id=randomUUID(),stamp=new Date().toISOString();
    const chat:any={id,projectId:prior.project_id,title:enabled?'压缩开启':'压缩关闭',messages:[],createdAt:stamp,updatedAt:stamp};
    await service.putState(chat.projectId,'conversations',id,chat); manager.indexConversation(id,chat.projectId);
    const folder=path.join(privateData,'workspaces',chat.projectId,id,'sessions');await fs.mkdir(folder,{recursive:true});
    const lines=originalBytes.trimEnd().split('\n');
    const header=JSON.parse(lines[0]);header.id=randomUUID();header.cwd=path.dirname(folder);
    lines[0]=JSON.stringify(header);
    const before=lines.join('\n')+'\n',sessionFile=path.join(folder,'session.jsonl');
    await fs.writeFile(sessionFile,before,{flag:'wx'});
    const arm:any={enabled,conversation_id:id,history_sha256:hash(before),runs:[],checks:[],usage:{input:0,cacheRead:0,cacheWrite:0,output:0,summaryInput:0,summaryOutput:0,calls:0},status:'running'};
    report.arms.push(arm);await save();
    const evaluation={profile:'financial' as const,budget_group_id:'compact-'+id,budget:limits};
    for (const [index,task] of tasks.entries()) {
      if(index>0){await manager.shutdown();manager=new RunManager(service);await manager.recover(chat.projectId);}
      const started=await manager.start(await manager.getConversation(id),task,[],undefined,evaluation);
      let current=await manager.getRun(started.id),lastLog=0;
      while(!['completed','failed','cancelled'].includes(current.status)||manager.activeFor(id)) {
        if(Date.now()-lastLog>15000){console.log(enabled?'compression:on':'compression:off',current.status,current.stage,JSON.stringify(current.usage));lastLog=Date.now();}
        await delay(500);current=await manager.getRun(started.id);
      }
      const events=(await fs.readFile(path.join(privateData,'audit',started.id+'.jsonl'),'utf8')).trim().split('\n').map(line=>JSON.parse(line));
      const usage=events.filter(e=>e.type==='model_usage');
      const tools=events.filter(e=>e.type==='tool_result').map(e=>e.data.name);
      const answer=(await manager.getConversation(id)).messages.filter(m=>m.role==='assistant'&&m.runId===started.id).map(m=>m.content).join('\n');
      arm.runs.push({id:started.id,status:current.status,error:current.error,usage:current.usage,evaluation:current.evaluation,tools,answer,model_usage:usage.map(e=>e.data)});
      for(const event of usage){const u=event.data.usage||{};arm.usage.calls++;for(const key of ['input','cacheRead','cacheWrite','output'])arm.usage[key]+=u[key]||0;if(event.data.phase==='compaction'){arm.usage.summaryInput+=(u.input||0)+(u.cacheRead||0)+(u.cacheWrite||0);arm.usage.summaryOutput+=u.output||0;}}
      arm.checks.push({name:`turn_${index+1}_completed`,passed:current.status==='completed'});
      arm.checks.push({name:`turn_${index+1}_reread_original`,passed:tools.includes('read_research_source')});
      arm.checks.push({name:`turn_${index+1}_no_new_sources`,passed:!tools.some(n=>['search_web','fetch_research_source','process_documents','prepare_document_sources'].includes(n))});
      arm.checks.push({name:`turn_${index+1}_numbers_period_unit`,passed:/181\.81/.test(answer)&&/12\.30?\b/.test(answer)&&/2025/.test(answer)&&/半年|上半年|H1|1.?6月/.test(answer)&&/亿元/.test(answer)});
      await save();if(current.status!=='completed')break;
    }
    const after=await fs.readFile(sessionFile,'utf8'),checkpoints=after.trim().split('\n').map(line=>JSON.parse(line)).filter(e=>e.type==='compaction');
    arm.checkpoints=checkpoints.map(e=>({id:e.id,summary:e.summary,details:e.details,tokensBefore:e.tokensBefore}));
    arm.checks.push({name:'history_prefix_unchanged',passed:after.startsWith(before)});
    arm.checks.push({name:'checkpoint_matches_policy',passed:enabled?checkpoints.length>0:checkpoints.length===0});
    if(enabled)arm.checks.push({name:'exact_saved_source_pointer_retained',passed:checkpoints.some(e=>(e.details?.recoveryReferences?.sources||[]).includes('web_f34cddc6-52c8-41ea-a7e1-f290981805af'))});
    arm.checks.push({name:'audit_budget_calls_match',passed:arm.runs.at(-1)?.evaluation?.usage.model_calls===arm.usage.calls});
    arm.status=arm.checks.every(c=>c.passed)?'passed':'failed';
    await manager.shutdown();manager=undefined;await save();
  }
  report.original_history_unchanged=hash(await fs.readFile(originalSession))===protocol.original_session_sha256;
  report.status=report.original_history_unchanged&&report.arms.every(a=>a.status==='passed')?'passed':'failed';
} catch(error) {report.status='failed';report.error=redactError(error);}
finally {await manager?.shutdown();await service.close();report.finished_at=new Date().toISOString();await save();console.log('REPORT',output,report.status);if(report.status!=='passed')process.exitCode=1;}

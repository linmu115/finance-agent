// Replay the retained real answer through current display code. Zero model calls.
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve('data/evaluation/analyst-delivery-smoke-20261008');process.env.FINANCE_DATA_DIR=path.join(root,'app-data');
const {annotateAnswer,valuationSections}=await import('../server/answer-semantics.js');
const {exportReportPackage,reportSnapshot}=await import('../server/report-package.js');
const {FinanceService}=await import('../server/mcp.js');
const service=new FinanceService();await service.connect();
try{
 const chat=JSON.parse(await fs.readFile(path.join(root,'conversation.json'),'utf8')),snapshot=await reportSnapshot(chat),message=chat.messages.at(-1);
 const events=(await fs.readFile(path.join(root,'app-data/audit',message.runId+'.jsonl'),'utf8')).trim().split('\n').map(l=>JSON.parse(l));
 const template=events.findLast(e=>e.type==='answer_bound').data.template;
 message.content=(await service.call('render_answer',{project_id:chat.projectId,body:annotateAnswer(template,message.sources),tables:snapshot.turns.at(-1).tables})).data.body;
 if(valuationSections(message.content).length)throw Error('Missing valuation sections after replay');
 const result=await exportReportPackage(service,chat);
 await fs.cp(path.join(root,'app-data',path.dirname(result.relative_path)),path.join(root,'package-replay'),{recursive:true});
 await fs.writeFile(path.join(root,'answer-replay.md'),message.content);
 console.log(JSON.stringify({model_calls:0,package:result,alias_downgrades:(message.content.match(/【推论·缺少绑定或来源】/g)||[]).length}));
}finally{await service.close();}

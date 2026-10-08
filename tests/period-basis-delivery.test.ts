import test from 'node:test';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {registerNumericTables} from '../server/numeric-tables.js';
import {modelContext} from '../server/model-context.js';

test('analyst workpapers bind exact cells and export their chapters with provenance',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-period-basis-'));
 process.env.FINANCE_DATA_DIR=dir;
 const python=path.resolve('.venv/Scripts/python.exe');
 // Frozen N2 fixture only. Its database and deliveries live in a TemporaryDirectory.
 const {stdout}=await promisify(execFile)(python,['-c',`
import json
from unittest.mock import patch
from service.tests.test_workpaper_variance import VarianceContractTests
from service.financial_workpapers import financial_workpaper
f=VarianceContractTests();f.setUp()
try:
    results=[]
    for kind, module in [('period_analysis','workpaper_periods'),('basis_changes','workpaper_basis'),('anomaly_signals','financial_workpapers'),('variance_attribution','financial_workpapers')]:
        with patch('service.'+module+'.load_facts',return_value=f.facts):
            results.append(financial_workpaper(f.s,'p',kind,document_id=f.doc))
    with patch('service.financial_workpapers.load_facts',return_value=f.facts):
        statement=financial_workpaper(f.s,'p','statement_analysis',document_id=f.doc)
    print(json.dumps({'results':results,'statement':statement},ensure_ascii=False))
finally:f.doCleanups()
`],{maxBuffer:8*1024*1024,encoding:'utf8'});
 const {results,statement}=JSON.parse(stdout);
 const {FinanceService}=await import('../server/mcp.js');
 const {exportReportPackage,reportSnapshot}=await import('../server/report-package.js');
 const service=new FinanceService();await service.connect();
 try{
  await service.call('create_project',{project_id:'test',name:'Isolated period and basis delivery'});
  // K1 and variance in one answer must retain both distinct bridges.
  const combined:any={};registerNumericTables(combined,statement);
  registerNumericTables(combined,results.find((r:any)=>r.kind==='variance_attribution'));
  assert.deepEqual(combined.bridge,statement.numeric_tables.bridge);
  assert.ok(combined.profit_bridge);
  const both=(await service.call('render_answer',{project_id:'test',body:'{{table:bridge}}\n\n{{table:profit_bridge}}',tables:combined})).data.body;
  assert.ok(both.includes('期初至期末现金'));assert.ok(both.includes('归母净利润变化'));
  const chat:any={id:'test-chat',projectId:'test',title:'期间与口径底稿合并回放',messages:[]};
  await mkdir(path.join(dir,'audit'));
  for(const result of results){
   const tables:any={};registerNumericTables(tables,result);
   assert.deepEqual(tables,result.report.tables);
   assert.equal(modelContext('financial_workpaper',{status:'ok',data:result}).data.numeric_tables,undefined);
   for(const [name,t] of Object.entries(tables) as [string,any][])
    assert.equal(t.report_section,['missing','unrecognized'].includes(name)?'limitations':({period_analysis:'basis_changes',basis_changes:'basis_changes',anomaly_signals:'anomaly_signals',variance_attribution:'variance_attribution'} as any)[result.kind]);
   const [table,column]=({period_analysis:['quarters','amount'],basis_changes:['repeated_nonrecurring','occurrences'],anomaly_signals:['signals','value'],variance_attribution:['profit_bridge','contribution']} as any)[result.kind];
   const row=tables[table].row_keys[0];
   const body=`数值 {{${table}.${row}.${column}}}。\n\n{{table:${table}}}`;
   const rendered=(await service.call('render_answer',{project_id:'test',body,tables})).data.body;
   assert.ok(!rendered.includes('{{'));assert.ok(rendered.includes('|'));
   chat.messages.push({id:result.kind,runId:result.kind,role:'assistant',status:'completed',createdAt:'2026-10-08',content:rendered,sources:[],artifacts:[]});
   await writeFile(path.join(dir,'audit',result.kind+'.jsonl'),JSON.stringify({type:'tool_result',data:{name:'financial_workpaper',messageId:result.kind,result:{status:'ok',data:result}}})+'\n');
  }
  const snapshot=await reportSnapshot(chat);
  for(let i=0;i<results.length;i++)assert.deepEqual(snapshot.turns[i].tables,results[i].numeric_tables);
  const exported=await exportReportPackage(service,chat),folder=path.join(dir,path.dirname(exported.relative_path));
  const md=await readFile(path.join(folder,'report.md'),'utf8'),chapter=md.split(/## 特殊损益与口径\r?\n/)[1].split(/\r?\n## /)[0];
  for(const title of ['单季数据','累计数据','期间变化','口径识别结论','多期非经常项目'])assert.ok(chapter.includes(title),title);
  // This frozen fixture has unit-only page text, hence no policy-marker rows to render.
  assert.equal(results[1].numeric_tables.markers.rows.length,0);
  assert.ok(!chapter.includes('口径变化原文'));
  const variance=md.split(/## 业绩变化归因\r?\n/)[1].split(/\r?\n## /)[0],signals=md.split(/## 异常信号\r?\n/)[1].split(/\r?\n## /)[0];
  for(const title of ['利润桥','变化贡献','驱动因素原文'])assert.ok(variance.includes(title),title);
  assert.ok(!variance.includes('现金桥'));assert.ok(signals.includes('异常信号'));assert.ok(signals.includes('存货计提率'));
  assert.ok(signals.includes('未经行业校准'));assert.ok(variance.includes('未解释差额'));
  assert.deepEqual(JSON.parse(await readFile(path.join(folder,'snapshot.json'),'utf8')),snapshot);
  const check=await promisify(execFile)(python,['-c',`
import sys,json,fitz
from pathlib import Path
from openpyxl import load_workbook
p=Path(sys.argv[1]);b=load_workbook(p/'workpapers.xlsx');s=b['特殊损益与口径']
titles=[r[0].value for r in s]
assert any('单季数据' in str(v) for v in titles)
assert any('多期非经常项目' in str(v) for v in titles)
assert any(c.comment and 'source_ref' in c.comment.text for row in s for c in row)
assert any('利润桥' in str(r[0].value) for r in b['利润桥'])
assert any('存货计提率' in str(r[0].value) for r in b['信号'])
assert any(c.comment and 'source' in c.comment.text for row in b['贡献'] for c in row)
with fitz.open(p/'report.pdf') as pdf: assert len(pdf)>0
print(json.dumps({'source_comments':True,'chapter_workbook':True}))
`,folder]);
  assert.equal(JSON.parse(check.stdout).source_comments,true);
 }finally{await service.close();}
});

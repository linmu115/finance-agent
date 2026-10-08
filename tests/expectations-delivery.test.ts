import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {registerNumericTables} from '../server/numeric-tables.js';
import {modelContext} from '../server/model-context.js';

test('real K4 replay registers A1 and exports exact gaps, limitations and source comments',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-expectations-'));
 process.env.FINANCE_DATA_DIR=dir;
 const fixture=JSON.parse(await readFile('docs/evidence/n2-expectations/numeric-tables.json','utf8'));
 const data={kind:'expectations',numeric_tables:fixture,observations:fixture.observations.rows};
 const tables:any={};registerNumericTables(tables,data);
 assert.deepEqual(tables,fixture);
 assert.equal(modelContext('financial_workpaper',{status:'ok',data}).data.numeric_tables,undefined);
 const {FinanceService}=await import('../server/mcp.js');
 const {exportReportPackage,reportSnapshot}=await import('../server/report-package.js');
 const {GENERIC_TOOL_ALLOWLIST,PREPARED_TOOL_ALLOWLIST}=await import('../server/runs.js');
 assert.equal(GENERIC_TOOL_ALLOWLIST.has('financial_workpaper'),false);
 assert.equal(PREPARED_TOOL_ALLOWLIST.has('financial_workpaper'),false);
 const svc=new FinanceService();await svc.connect();
 try{
  await svc.call('create_project',{project_id:'k4-test',name:'Offline K4 delivery'});
  const row='b6d0952772964d22b374e2dcd582475e';
  const rendered=(await svc.call('render_answer',{project_id:'k4-test',tables,
   body:`EPS 数值参照差额 {{reference_gaps_CNY_per_share.${row}.difference}}。\n\n{{table:reference_gaps_CNY_per_share}}`})).data.body;
  assert.ok(!rendered.includes('{{'));assert.match(rendered,/-0.56/);assert.match(rendered,/仅数值参照/);
  const chat:any={id:'offline-k4',projectId:'k4-test',title:'伊利 2024 预期差（真实数据离线验收）',messages:[{id:'answer',runId:'k4',role:'assistant',status:'completed',createdAt:'2026-10-08',content:rendered,sources:[],artifacts:[]}]};
  await mkdir(path.join(dir,'audit'));
  await writeFile(path.join(dir,'audit/k4.jsonl'),JSON.stringify({type:'tool_result',data:{name:'financial_workpaper',messageId:'answer',result:{status:'ok',data}}})+'\n');
  assert.deepEqual((await reportSnapshot(chat)).turns[0].tables,fixture);
  const exported=await exportReportPackage(svc,chat),folder=path.join(dir,path.dirname(exported.relative_path));
  const md=await readFile(path.join(folder,'report.md'),'utf8');
  assert.ok(md.includes('实际与最近预测的数值参照'));assert.ok(md.includes('净利润归母身份未定'));assert.ok(md.includes('晚于预测截止日'));
  assert.ok(md.includes('-0.56'));assert.ok(md.includes('机构会计/合并范围未明确'));
  const python=process.env.FINANCE_PYTHON||path.resolve('.venv/Scripts/python.exe');
  const check=await promisify(execFile)(python,['-c',`
import sys,json,fitz
from pathlib import Path
from decimal import Decimal
from openpyxl import load_workbook
p=Path(sys.argv[1]);book=load_workbook(p/'workpapers.xlsx');snapshot=json.loads((p/'snapshot.json').read_text('utf8'))
tables=snapshot['turns'][0]['tables'];checked=0
for name,t in tables.items():
 if not name.startswith('reference_gaps'):continue
 fields=list(t['columns'])
 for expected in t['rows']:
  matches=[row for row in book['指标'] if row[0].value==expected['key'] and len(row)>fields.index('status') and row[fields.index('status')].value==expected['status']]
  assert len(matches)==1,(name,expected['key'])
  for key in ('forecast','actual','difference','difference_rate'):
   c=matches[0][fields.index(key)];assert Decimal(str(c.value))==Decimal(expected[key]);assert 'source_ref' in c.comment.text;checked+=1
with fitz.open(p/'report.pdf') as pdf:
 text=''.join(page.get_text() for page in pdf);assert '-0.56' in text;assert len(pdf)>0
 print(json.dumps({'checked_numeric_cells':checked,'pdf_pages':len(pdf),'folder':str(p)},ensure_ascii=False))
`,folder],{encoding:'utf8'});
  const info=JSON.parse(check.stdout);assert.equal(info.checked_numeric_cells,24);
  // Kept in the temp directory for actual visual acceptance, no HTTP server.
  console.log('K4 delivery evidence '+JSON.stringify(info));
 }finally{await svc.close();}
});

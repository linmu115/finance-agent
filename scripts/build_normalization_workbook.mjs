// Uses only the bundled artifact runtime; fixture semantics are intentionally fixed.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const root=path.resolve(import.meta.dirname,'..');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const working=path.join(root,'tmp/normalization-artifacts');
await fs.mkdir(working,{recursive:true});
try { await fs.symlink(runtime,path.join(working,'node_modules'),'junction'); } catch(e) { if(e.code!=='EEXIST') throw e; }
const require=createRequire(path.join(working,'builder.mjs'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const book=Workbook.create(), sheet=book.worksheets.add('合并利润表');
sheet.showGridLines=false;
sheet.getRange('A1:D7').values=[
 ['云岚设备股份有限公司2025年年度报告',null,null,null],
 ['合并利润表（中国企业会计准则）',null,null,null],
 ['单位：人民币万元；2024年度比较数据重述',null,null,null],
 ['项目','2025年度','2024年度',null],
 [null,'本年','调整前','调整后'],
 ['营业收入',5147.5,4562.5,4625],
 ['营销推广及销售渠道维护费用（销售费用）',417.5,362.5,368.75],
];
sheet.mergeCells('A1:D1');sheet.mergeCells('A2:D2');sheet.mergeCells('A3:D3');
sheet.mergeCells('A4:A5');sheet.mergeCells('C4:D4');
sheet.getRange('A1:D7').format.font={name:'Microsoft YaHei',size:11};
sheet.getRange('A1:D7').format.rowHeight=28;
sheet.getRange('A1:D1').format.font={name:'Microsoft YaHei',size:15,bold:true};
sheet.getRange('A1:D3').format.rowHeight=32;
sheet.getRange('A1:A7').format.columnWidth=52;
sheet.getRange('B1:D7').format.columnWidth=18;
sheet.getRange('A4:D5').format.fill='#ECEEF1';
sheet.getRange('A4:D5').format.font={name:'Microsoft YaHei',size:11,bold:true};
sheet.getRange('A4:D5').format.horizontalAlignment='center';
sheet.getRange('B6:D7').setNumberFormat('#,##0.00');
book.recalculate();
const inspect=await book.inspect({kind:'table',range:'合并利润表!A1:D7',include:'values,formulas',tableMaxRows:7,tableMaxCols:4});
await fs.writeFile(path.join(working,'workbook-inspection.txt'),inspect.ndjson);
const preview=await book.render({sheetName:'合并利润表',range:'A1:D7',scale:1.5,format:'png'});
await fs.writeFile(path.join(working,'merged-headers.png'),new Uint8Array(await preview.arrayBuffer()));
const out=path.join(root,'benchmark/versions/v0.3-normalization/inputs');await fs.mkdir(out,{recursive:true});
await (await SpreadsheetFile.exportXlsx(book)).save(path.join(out,'09_merged_headers.xlsx'));
try { await fs.rename(path.join(out,'09_merged_headers.xlsx.inspect.ndjson'),path.join(working,'export-inspection.ndjson')); } catch(e) { if(e.code!=='ENOENT') throw e; }
console.log('Created 09_merged_headers.xlsx and preview');

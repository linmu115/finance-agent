// Reproduce financial cell scores from a saved first-run report, no model/API.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {scoreFinancialTables} from './score_financial_tables_v05.mjs';
const argv=process.argv.slice(2),arg=(n,d)=>argv.includes(n)?argv[argv.indexOf(n)+1]:d;
if(argv.includes('--help'))console.log('node score_holdout_v05_artifact.mjs --suite DIR --report ORIGINAL_RUN.json --output NEW.json. Financial correctness only; no model or network.');
else{
 const suite=path.resolve(arg('--suite',path.join(import.meta.dirname,'../benchmark/versions/v0.5-holdout'))),reportFile=arg('--report'),output=arg('--output');
 if(!reportFile||!output)throw Error('--report and --output are required');
 const hash=s=>createHash('sha256').update(s).digest('hex'),goldBytes=await fs.readFile(path.join(suite,'gold.json')),manifest=JSON.parse(await fs.readFile(path.join(suite,'manifest.json'),'utf8'));
 if(hash(goldBytes)!==manifest.gold_sha256)throw Error('Frozen gold hash changed');
 const raw=await fs.readFile(path.resolve(reportFile),'utf8'),report=JSON.parse(raw);
 if(!Array.isArray(report.facts)||!Array.isArray(report.documents))throw Error('Report must preserve original facts and uploaded document mapping');
 const originalHash=report.suite_before?.['benchmark/versions/v0.5-holdout/gold.json'];if(originalHash&&originalHash!==hash(goldBytes))throw Error('This run used different gold');
 const score=scoreFinancialTables(JSON.parse(goldBytes),report.facts,report.documents);
 await fs.writeFile(path.resolve(output),JSON.stringify({...score,kind:'read_only_financial_correctness_score',original_report_sha256:hash(raw),gold_sha256:hash(goldBytes),model_calls:0,note:'Reproduces financial correctness only. Operational gates and actual Pi/cache provenance remain in the preserved original report.'},null,2),{flag:'wx'});
 console.log(JSON.stringify(score.score));
}

import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';

const root=path.resolve(import.meta.dirname,'..'),base='http://127.0.0.1:3001';
const source=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/pi-full-report-v03.json'),'utf8'));
const route=`/api/projects/${source.project_id}/financial-data`;
const checks=[],pages=[],ids=new Set();let expected;
const get=async url=>{const response=await fetch(base+url);if(!response.ok)throw Error(`HTTP ${response.status}: ${await response.text()}`);return response;};
for(let offset=0;;){
  const response=await get(`${route}?limit=10000&offset=${offset}`),text=await response.text(),page=JSON.parse(text);
  expected??=page.total;if(page.total!==expected)throw Error('Data changed during read-only pagination verification.');
  if(page.items.length>200||page.limit>200||page.offset!==offset)throw Error('Oversized request was not paginated correctly.');
  for(const fact of page.items){if(ids.has(fact.fact_id))throw Error('Repeated fact across pages.');ids.add(fact.fact_id);}
  pages.push({offset,count:page.items.length,bytes:Buffer.byteLength(text)});offset+=page.items.length;
  if(offset>=page.total)break;if(!page.items.length)throw Error('Pagination stopped before all facts.');
}
checks.push({name:'large requested limit returns complete bounded pages',passed:ids.size===expected});
const csv=Buffer.from(await(await get(route+'?format=csv')).arrayBuffer());
const csvPath=path.join(root,'data/runtime/pagination-verification.csv');await fs.writeFile(csvPath,csv);
const health=await(await get('/api/health')).json();checks.push({name:'MCP remains connected after full pagination and CSV export',passed:health.ok&&health.service==='connected'});
const report={project_id:source.project_id,at:new Date().toISOString(),expected_facts:expected,loaded_facts:ids.size,pages,checks,csv_path:csvPath,csv_bytes:csv.length,csv_sha256:createHash('sha256').update(csv).digest('hex')};
await fs.writeFile(path.join(root,'benchmark/results/large-response-pagination-v03.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({facts:ids.size,pages:pages.length,csv_bytes:csv.length,checks}));

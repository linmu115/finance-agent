/** Host maintenance: replay saved semantic mappings, with the application stopped. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {FinanceService} from '../server/mcp.ts';
const root=path.resolve(import.meta.dirname,'..');
try{const response=await fetch('http://127.0.0.1:3001/api/health',{signal:AbortSignal.timeout(1500)});if(response.ok)throw new Error('APPLICATION_STILL_RUNNING');}
catch(error){if(error.message==='APPLICATION_STILL_RUNNING')throw new Error('Stop the application before running host maintenance.');}
const report=JSON.parse(await fs.readFile(path.join(root,'benchmark/results/pi-full-report-v03.json'),'utf8'));
const service=new FinanceService();
try{
 await service.connect();
 const result=await service.call('rematerialize_documents',{project_id:report.project_id,document_ids:[report.document_id]});
 const evidence={project_id:report.project_id,document_id:report.document_id,...result.data};
 await fs.writeFile(path.join(root,'benchmark/results/full-report-rematerialization-live-v033.json'),JSON.stringify(evidence,null,2));
 console.log(JSON.stringify({model_requests:evidence.model_requests,batches_replayed:evidence.batches_replayed,facts_rebuilt:evidence.facts_rebuilt,catalog_review:evidence.catalog_review,audit_path:evidence.audit_path}));
}finally{await service.close();}

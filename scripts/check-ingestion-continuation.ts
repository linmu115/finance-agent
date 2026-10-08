import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {ingestionRemaining,madeIngestionProgress} from '../server/ingestion-continuation.js';

const path=process.argv[2];
const transition=JSON.parse(await readFile(path,'utf8'));
const before=ingestionRemaining(transition.before),after=ingestionRemaining(transition.after);
const continueRun=madeIngestionProgress(before.progress,after.progress);
assert.equal(continueRun,true);
assert.equal(after.work.length,1);
assert.equal(after.work[0].pending_tables.includes(116),false);
assert.equal(madeIngestionProgress(after.progress,ingestionRemaining(transition.after.reverse()).progress),false);
const result={continue:continueRun,processing_id:after.work[0].processing_id,
 before:Object.values(before.progress).map(d=>({tables:d.completed_tables.length,facts:d.fact_count})),
 after:Object.values(after.progress).map(d=>({tables:d.completed_tables.length,facts:d.fact_count})),
 remaining_tables:after.work[0].pending_tables.length,duplicate_work_items:after.work.length,
 unchanged_transition_progress:false,model_calls:0};
await writeFile(path.replace('commit-transition.json','continuation-verdict.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));

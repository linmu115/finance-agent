import test from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Independent ESM observation helper.
import {readPersistedRunAnswer} from '../scripts/validation_utils.mjs';

test('completed-run scoring waits for that run’s persisted reply without starting another model request',async()=>{
 let reads=0;
 const result=await readPersistedRunAnswer(async()=>({messages:[{role:'assistant',runId:'older',content:'unrelated nonempty answer'},{role:'assistant',runId:'target',content:++reads>=3?'correct batch marker':''}]}),'target',{timeoutMs:1000,pollMs:1});
 assert.equal(result.answer.content,'correct batch marker');assert.equal(result.attempts,3);
 const missing=await readPersistedRunAnswer(async()=>({messages:[{role:'assistant',runId:'older',content:'other run'}]}),'target',{timeoutMs:5,pollMs:1});
 assert.equal(missing.answer,undefined,'an older assistant answer must not satisfy the current turn');
});

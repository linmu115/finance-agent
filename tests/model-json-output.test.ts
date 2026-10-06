import test from 'node:test';
import assert from 'node:assert/strict';
import {jsonOutputPayload} from '../server/model-runtime.js';

test('JSON mode uses the wire contract of the configured API and preserves other options',()=>{
 const input={input:[{role:'user',content:'Return JSON.'}],text:{verbosity:'low'},store:false};
 const response=jsonOutputPayload(input,'openai-responses');
 assert.equal('response_format' in response,false);
 assert.deepEqual(response.text,{verbosity:'low',format:{type:'json_object'}});
 assert.equal(response.input,input.input);
 assert.deepEqual(input.text,{verbosity:'low'});
 const chat=jsonOutputPayload({messages:[]},'openai-completions');
 assert.deepEqual(chat.response_format,{type:'json_object'});
 assert.equal('text' in chat,false);
 assert.equal(jsonOutputPayload(input,'anthropic-messages'),input);
});

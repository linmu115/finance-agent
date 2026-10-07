// Frozen G1 replay; no LLM, no edits to the original conversation or artifacts.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {markdownArtifactUrl,latestNamedArtifacts} from '../web/src/artifact-links.js';
const root='data/evaluation/pi-cowork-postfix-20261007';
const chat=JSON.parse(await fs.readFile(root+'/G1-conversation.json','utf8'));
const answer=chat.messages.findLast((m:any)=>m.role==='assistant');
const audit=(await fs.readFile(root+'/G1-audit.jsonl','utf8')).split('\n').filter(Boolean).map(x=>JSON.parse(x));
const runs=audit.filter(e=>e.type==='tool_result'&&e.data.name==='get_analysis_status'&&e.data.result.data.artifacts?.some((a:any)=>a.name==='chart_1.png')).map(e=>e.data.result.data.run_id);
const history=answer.artifacts.filter((a:any)=>a.name==='chart_1.png');
assert.equal(history.length,2);assert.equal(runs.length,2);
const latest=latestNamedArtifacts(answer.artifacts);const image=latest.filter((a:any)=>a.name==='chart_1.png');
assert.equal(image.length,1);assert.ok(image[0].url.includes(runs.at(-1)));
const links=['chart_1.png','sandbox:/output/chart_1.png',`analysis/${runs[0]}/output/chart_1.png`,history[0].url].map(input=>({input,resolved:markdownArtifactUrl(input,answer.artifacts)}));
assert.ok(links.every(x=>x.resolved===image[0].url));
const downloads=[];
for(const artifact of history){
 const response=await fetch('http://127.0.0.1:3001'+artifact.url);const bytes=Buffer.from(await response.arrayBuffer());
 assert.equal(response.status,200);assert.equal(bytes.subarray(1,4).toString(),'PNG');
 downloads.push({url:artifact.url,status:response.status,bytes:bytes.length,content_type:response.headers.get('content-type')});
}
const evidence={method:'Frozen G1 tool-result publication order and frontend resolver, both immutable downloads fetched over 3001; no LLM and no held-out reads.',conversation_id:chat.id,run_order:runs,original_chart_count:history.length,visible_chart_count:image.length,latest_url:image[0].url,links,downloads,history_retained:true};
await fs.writeFile('docs/evidence/harness-v2-followup-20261007/a4-g1-replay.json',JSON.stringify(evidence,null,2));
console.log(JSON.stringify(evidence,null,2));

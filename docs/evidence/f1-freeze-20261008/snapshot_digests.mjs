import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const [input,output]=process.argv.slice(2);
const snapshot=JSON.parse(await fs.readFile(input,'utf8'));
const hash=x=>createHash('sha256').update(x,'utf8').digest('hex');
const normalize=s=>s.replace(/(<cwd>\n)[^\n]+(\n<\/cwd>)$/, '$1<WORKSPACE>$2');
const count=s=>({chars:[...s].length,rough_tokens:Math.ceil([...s].reduce((a,c)=>a+(c.codePointAt(0)<128?.25:1),0))});
const result={method:'Native Pi empty isolated project, no prompt or model request. Full context=system plus JSON.stringify(ordered full tools). Unicode code points; rough tokens=ceil(ASCII/4 + non-ASCII). UTF-8 SHA256; normalize only trailing cwd. Combined hash=JSON.stringify({system,tools}), key order retained. History, dynamic results, attachments and transport overhead excluded.',profiles:{}};
for(const [profile,p] of Object.entries(snapshot.profiles)){
 const system=normalize(p.system),tools=JSON.stringify(p.tools);
 const names=p.tools.map(t=>t.name);
 if(names.includes('advance_cleaning_round'))throw Error('host-only tool exposed');
 if(names.includes('financial_workpaper')!==(profile==='financial'))throw Error('wrong financial tool exposure');
 const shared=p.tools.find(t=>t.name==='run_analysis').description;
 for(const entry of ['{{表名.行键.列名}}','{{table:表名}}','source_run_id+params','edits','get_artifact'])if(!shared.includes(entry))throw Error('missing shared entry: '+entry);
 result.profiles[profile]={tool_count:names.length,tools:names,...count(p.system+tools),system_chars:[...p.system].length,
  system_raw_sha256:hash(p.system),instructions_sha256:hash(system),tools_sha256:hash(tools),
  context_raw_sha256:hash(JSON.stringify(p)),context_normalized_sha256:hash(JSON.stringify({system,tools:p.tools}))};
}
await fs.writeFile(output,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(Object.fromEntries(Object.entries(result.profiles).map(([k,v])=>[k,{tools:v.tool_count,chars:v.chars,rough_tokens:v.rough_tokens,context_normalized_sha256:v.context_normalized_sha256}]))));

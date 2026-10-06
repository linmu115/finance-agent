// Verify the actual replies through React Markdown, then download resolved files.
import {readFile,writeFile} from 'node:fs/promises';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {parseHTML} from 'linkedom';
import {markdownArtifactUrl} from '../web/src/artifact-links.ts';
const dir='data/evaluation/'+(process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261005-cpa');
const state=JSON.parse(await readFile(dir+'/experiment.json','utf8'));
const outputArg=process.argv.indexOf('--output');
const output=outputArg<0?'post-trial-link-check.json':process.argv[outputArg+1];
const results=[];
for(const run of state.runs){
  const chat=JSON.parse(await readFile(`${dir}/${run.label}-conversation.json`,'utf8'));
  const messages=chat.messages.filter(m=>m.role==='assistant'&&m.runId===run.runId);
  let mapped=0;
  const html=messages.map(m=>renderToStaticMarkup(createElement(ReactMarkdown,{remarkPlugins:[remarkGfm],urlTransform:url=>{
    const target=markdownArtifactUrl(url,m.artifacts);if(target!==url&&target.startsWith('/api/'))mapped++;return target;
  }},m.content))).join('\n');
  const {document}=parseHTML(html);
  const links=[...document.querySelectorAll('a')].map(a=>a.getAttribute('href'));
  const files=[];
  for(const url of [...new Set(links.filter(u=>u?.startsWith('/api/projects/')))]){
    const response=await fetch('http://127.0.0.1:3001'+url);await response.arrayBuffer();
    files.push({url,status:response.status,type:response.headers.get('content-type')});
  }
  results.push({label:run.label,mapped,unresolvedLocalLinks:links.filter(u=>!u||/^(?:analysis|sandbox:)/.test(u)),downloads:files});
}
await writeFile(dir+'/'+output,JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify({mapped:results.reduce((n,r)=>n+r.mapped,0),downloads:results.flatMap(r=>r.downloads).length,failed:results.flatMap(r=>r.downloads).filter(x=>x.status!==200||x.type?.includes('text/html')),unresolved:results.flatMap(r=>r.unresolvedLocalLinks)},null,2));

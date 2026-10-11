// Same Markdown renderer as the host; no HTTP server, model or database writes.
import {readFile,writeFile} from 'node:fs/promises';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
const [input,output]=process.argv.slice(2);
const md=await readFile(input,'utf8');
await writeFile(output,renderToStaticMarkup(createElement(Markdown,{remarkPlugins:[remarkGfm],skipHtml:true,
 components:{img:({src,alt})=>src?.startsWith('assets/')?createElement('img',{src,alt}):createElement('p',null,alt||'图表','（见原会话附件）')}},md)));

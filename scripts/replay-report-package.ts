import fs from 'node:fs/promises';
import path from 'node:path';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
process.env.FINANCE_DATA_DIR=path.resolve('tmp/analyst-package-replay');
const {FinanceService}=await import('../server/mcp.js');const service=new FinanceService();await service.connect();
try{
 await service.call('create_project',{project_id:'replay',name:'Offline report package replay'});
 const raw=JSON.parse(await fs.readFile('docs/evidence/n2-ashare-workpapers/carote-tables.json','utf8'));
 const snapshot={project_id:'replay',conversation_id:'offline',title:'卡罗特中报底稿回放',turns:[{id:'replay',created_at:'2026-10-08',body:'【观点】本报告回放已验收底稿，仅验证导出结构与数值保留。',sources:[],tables:raw.tables??raw}]};
 const prepared=(await service.call('prepare_report_package',{project_id:'replay',snapshot})).data;
 const html=renderToStaticMarkup(createElement(Markdown,{remarkPlugins:[remarkGfm],skipHtml:true},prepared.markdown));
 const result=(await service.call('finish_report_package',{project_id:'replay',package_id:prepared.package_id,html})).data;
 console.log(JSON.stringify(result));
}finally{await service.close();}

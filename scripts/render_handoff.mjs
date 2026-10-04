import fs from 'node:fs/promises';
import path from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const root=path.resolve(import.meta.dirname,'..');
const body=renderToStaticMarkup(React.createElement(Markdown,{remarkPlugins:[remarkGfm]},await fs.readFile(path.join(root,'HANDOFF.md'),'utf8')));
const style=`
:root{color-scheme:light;font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;color:#242424;background:#f5f5f5;font-size:16px;line-height:1.85}
*{box-sizing:border-box}body{margin:0}header{background:#fff;border-bottom:1px solid #e4e4e4;padding:18px max(24px,calc((100vw - 1050px)/2));display:flex;gap:18px;flex-wrap:wrap;align-items:center}
header strong{margin-right:auto}header a{font-size:14px;color:#444}main{max-width:1050px;margin:32px auto 80px;background:white;border:1px solid #e4e4e4;border-radius:16px;padding:46px 52px;overflow-wrap:anywhere}
h1{font-size:30px;line-height:1.4;letter-spacing:-.5px;margin:0 0 20px}h2{font-size:22px;border-top:1px solid #e6e6e6;padding-top:26px;margin-top:36px}h3{font-size:18px;margin-top:28px}p{margin:16px 0}a{color:#294f8a;text-underline-offset:3px}code{font:13px/1.6 Consolas,monospace;background:#f0f0f0;border-radius:4px;padding:2px 5px}pre{background:#f5f5f5;border:1px solid #e5e5e5;padding:18px;border-radius:10px;overflow:auto;line-height:1.6}pre code{background:none;padding:0;white-space:pre}
table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.75;margin:20px 0}th,td{text-align:left;vertical-align:top;border:1px solid #dedede;padding:11px 13px}th{background:#f4f4f4;font-weight:600}th:first-child,td:first-child{min-width:130px}li{margin:8px 0}strong{font-weight:650}
@media(max-width:700px){main{margin:12px;padding:24px 18px;border-radius:12px}header{padding:14px 24px}h1{font-size:25px}h2{font-size:20px}table{display:block;overflow-x:auto}td,th{min-width:170px}code{word-break:break-word}}
@media print{body{background:white}header{display:none}main{border:0;margin:0;padding:0;max-width:none}a{color:inherit}pre,table{break-inside:avoid}}
`;
await fs.writeFile(path.join(root,'HANDOFF.html'),`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>金融研究 Agent · 收尾交接</title><style>${style}</style></head><body><header><strong>金融研究工作台 · 交接</strong><a href="http://127.0.0.1:3001/">本机应用</a><a href="benchmark/design.html">Benchmark 设计</a><a href="HANDOFF.md">Markdown 原稿</a></header><main>${body}</main></body></html>`,'utf8');
console.log('HANDOFF.html generated from HANDOFF.md');

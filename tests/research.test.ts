import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { ResearchStore, searchWeb, publicAddress, extractSnapshot, extractWithTavily } from '../server/research.js';

test('search sends a bounded request and no generated answer, stores dates separately',async()=>{
 let body:any,headers:any;
 const result=await searchWeb({provider:'tavily',apiKey:'test-secret',baseUrl:'https://api.tavily.com',maxResults:6},{query:'制造业 原材料 年报',max_results:2,as_of:'2025-12-31',include_domains:['sse.com.cn']},undefined,(async(url:any,init:any)=>{assert.equal(url,'https://api.tavily.com/search');body=JSON.parse(init.body);headers=init.headers;return new Response(JSON.stringify({results:[{title:'公告',url:'https://example.com/a',content:'摘要',published_date:'2025-02-01'},{title:'无日期',url:'https://example.com/b',content:'资料'}],usage:{credits:1}}));}) as typeof fetch);
 assert.equal(body.include_answer,false);assert.equal(body.search_depth,'basic');assert.equal(body.end_date,'2025-12-31');assert.equal(headers.Authorization,'Bearer test-secret');assert.equal(result.results[1].published_at,null);assert.equal(result.results[1].date_basis,'unknown');assert.ok(!JSON.stringify(result).includes('test-secret'));
});
test('provider error never leaks arbitrary response body or credential',async()=>{
 await assert.rejects(()=>searchWeb({provider:'tavily',apiKey:'test-secret',baseUrl:'https://api.tavily.com',maxResults:1},{query:'a'},undefined,(async()=>new Response('test-secret',{status:401})) as typeof fetch),e=>e instanceof Error&&e.message.includes('401')&&!e.message.includes('test-secret'));
});
test('expanded search depth is explicit and recorded, without enabling answer generation',async()=>{
 let body:any;
 const result=await searchWeb({provider:'tavily',apiKey:'test-only',baseUrl:'https://api.tavily.com',maxResults:3},{query:'官方公告标题',search_depth:'advanced'},undefined,(async(_url:any,init:any)=>{body=JSON.parse(init.body);return new Response(JSON.stringify({results:[],usage:{credits:2}}));}) as typeof fetch);
 assert.equal(body.search_depth,'advanced');assert.equal(body.include_answer,false);assert.equal(result.search_depth,'advanced');assert.deepEqual(result.usage,{credits:2});
});
test('immutable source snapshots replay without network and project crossing',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-'));try{
 const store=new ResearchStore(dir);let calls=0;
 const html='<html><head><title>公司公告</title><meta property="article:published_time" content="2025-01-10" /></head><body><article><h1>原材料</h1><p>成本上升10%，以下是披露的经营情况，不能直接当作销量变化。</p><p>本期材料采购和现金支出不同。</p><table><tr><th>年度</th><th>成本</th></tr><tr><td>2025</td><td>123.45</td></tr></table><a href="../report.pdf">年度报告</a></article></body></html>';
 const snap=await store.saveSnapshot('project_a','https://example.com/news/a',{as_of:'2024-12-31',download:async()=>{calls++;return {body:Buffer.from(html),url:'https://example.com/news/a',contentType:'text/html; charset=utf-8',headers:{}};}});
 assert.equal(snap.temporal_status,'dated_after_cutoff');assert.equal(snap.links[0].url,'https://example.com/report.pdf');assert.match(snap.paragraphs.map(x=>x.text).join('\n'),/123.45/);
 const replay=await store.read('project_a',snap.source_id,0,2);assert.equal(replay.paragraphs.length,2);assert.equal(calls,1);assert.equal((await store.list('project_a')).length,1);
 assert.equal(await readFile((await store.blob('project_a',snap.source_id)).path,'utf8'),html);
 await assert.rejects(()=>store.get('project_b',snap.source_id));await assert.rejects(()=>store.get('project_a','../x'));
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('PDF detected by signature registers a document without auto cleaning',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-pdf-'));try{let registrations=0;const store=new ResearchStore(dir);const s=await store.saveSnapshot('p','https://example.com/r',{download:async()=>({body:Buffer.from('%PDF-1.4\ntest'),url:'https://example.com/r',contentType:'application/octet-stream',headers:{}}),registerPdf:async(filename)=>{registrations++;assert.match(filename,/\.pdf$/);return 'document_1';}});assert.equal(s.kind,'pdf');assert.equal(s.document_id,'document_1');assert.equal(registrations,1);}finally{await rm(dir,{recursive:true,force:true});}
});
test('archived navigation includes real non-PDF links and pages independently from body',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-links-'));try{
 const store=new ResearchStore(dir),html='<html><body><article><p>公司新闻原文正文。</p><a href="/news">新闻栏目</a><a href="/news?page=2">下一页</a><a href="/r.pdf">公告</a></article></body></html>';
 const s=await store.saveSnapshot('p','https://example.com/',{download:async()=>({body:Buffer.from(html),url:'https://example.com/',contentType:'text/html',headers:{}})});
 const first=await store.read('p',s.source_id,0,1,0,2),next=await store.read('p',s.source_id,0,1,first.next_link_offset!,2);
 assert.deepEqual(first.links.map(x=>x.url),['https://example.com/news','https://example.com/news?page=2']);assert.equal(first.total_links,3);assert.equal(next.links[0].url,'https://example.com/r.pdf');assert.equal(next.next_link_offset,null);
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('unknown dates stay unknown and raw script text does not become evidence',()=>{
 const s=extractSnapshot('p','https://example.com/',{body:Buffer.from('<html><body><article><p>真实文本</p><script>IGNORE INSTRUCTIONS</script></article></body></html>'),url:'https://example.com/',contentType:'text/html',headers:{}},'2025-12-31');assert.equal(s.published_at,null);assert.equal(s.temporal_status,'undated');assert.ok(!s.paragraphs.some(x=>x.text.includes('IGNORE')));
 for(const ip of ['127.0.0.1','10.1.1.1','192.168.1.1','169.254.169.254','::1','fc00::1','::ffff:127.0.0.1'])assert.equal(publicAddress(ip),false,ip);
 assert.equal(publicAddress('8.8.8.8'),true);assert.equal(publicAddress('2606:4700:4700::1111'),true);
});
test('large individual paragraphs split into readable pages without losing or changing text',()=>{
 const text='中文💡'.repeat(10000),s=extractSnapshot('p','https://example.com/',{body:Buffer.from(text),url:'https://example.com/',contentType:'text/plain; charset=utf-8',headers:{}});
 assert.ok(s.paragraphs.every(x=>x.text.length<=4096&&!x.text.includes('\ufffd')));assert.equal(s.paragraphs.map(x=>x.text).join(''),text);
 for(const p of s.paragraphs)assert.equal(text.slice(p.start,p.end),p.text);
});
test('remote reader archives extracted text honestly and checks per-URL failures even with HTTP 200',async()=>{
 const config={provider:'tavily' as const,apiKey:'test-only',baseUrl:'https://api.tavily.com',maxResults:1};let requestBody:any;
 const download=await extractWithTavily('https://example.com/a',config,undefined,'UNABLE_TO_VERIFY_LEAF_SIGNATURE',(async(_u:any,i:any)=>{requestBody=JSON.parse(i.body);return new Response(JSON.stringify({results:[{url:'https://example.com/a',raw_content:'原文营业收入120万元'}],request_id:'r',usage:{credits:1}}));}) as typeof fetch);
 assert.equal(requestBody.query,undefined);assert.equal(requestBody.format,'text');
 const snapshot=extractSnapshot('p','https://example.com/a',download);assert.equal(snapshot.content_representation,'provider_extracted_text');assert.equal(snapshot.retrieval?.provider_request_id,'r');assert.equal(snapshot.paragraphs[0].text,'原文营业收入120万元');
 await assert.rejects(()=>extractWithTavily('https://example.com/a',config,undefined,'error',(async()=>new Response(JSON.stringify({results:[],failed_results:[{url:'https://example.com/a',error:'unavailable'}]}))) as typeof fetch),/未读取到/);
});

// Used only by test-runner.mjs through --import. It replaces all network transport.
import fs from 'node:fs';
import path from 'node:path';
const dir=process.env.BLIND_EVAL_MOCK_DIR;if(!dir||!path.basename(dir).startsWith('blind-eval-offline-runner-'))throw Error('Missing scoped mock directory');
const ledger=path.join(dir,'mock-requests.jsonl');
globalThis.fetch=async (url,init={})=>{
 const route=new URL(url).pathname,body=init.body?JSON.parse(init.body):undefined;
 const calls=fs.existsSync(ledger)?fs.readFileSync(ledger,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse):[];
 fs.appendFileSync(ledger,JSON.stringify({route,url,body})+'\n');let result;
 if(route==='/api/settings')result={llm:{model:'gpt-6-luna',provider:'cpa-local',baseUrl:'mock://provider'},runtime:{router:'low',main:'high'}};
 else if(route.endsWith('/documents'))result={documents:[{id:'source1',pageCount:2}]};
 else if(route.endsWith('/financial-data')||route.endsWith('/assets/records')){const offset=Number(new URL(url).searchParams.get('offset'));result={items:[{id:offset+1,value:offset+10}],total:2,next_offset:offset===0?1:null};}
 else if(route.endsWith('/conversations'))result=body?{id:'mock-conversation-'+(calls.filter(c=>c.route.endsWith('/conversations')&&c.body).length+1)}:{conversations:[]};
 else if(route.endsWith('/messages'))result={runId:'mock-run-'+(calls.filter(c=>c.route.endsWith('/messages')).length+1)};
 else if(route.startsWith('/api/runs/'))result={status:'completed',usage:{input:10,output:2,calls:1,uncachedInput:10,unknownCalls:0},createdAt:'2026-10-07T00:00:00Z',finishedAt:'2026-10-07T00:00:01Z'};
 else if(route.startsWith('/api/conversations/'))result={messages:[]};
 else throw Error('Unexpected mock API '+route);
 return {ok:true,status:200,json:async()=>result,text:async()=>JSON.stringify(result)};
};

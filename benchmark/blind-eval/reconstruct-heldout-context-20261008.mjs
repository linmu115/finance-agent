// Offline only. Private intermediate; never distribute this file's raw output.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {buildSessionContext} from '../../node_modules/@earendil-works/pi-coding-agent/dist/core/session-manager.js';
import {getSystemMessageText} from '../../node_modules/@earendil-works/pi-ai/dist/utils/text.js';
import {convertResponsesTools} from '../../node_modules/@earendil-works/pi-ai/dist/api/openai-responses-shared.js';
const root=process.cwd(), base=path.join(root,'data/evaluation/blind-eval-F12-heldout-20261008');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8').replace(/^\uFEFF/,''));
const lines=f=>fs.readFileSync(f,'utf8').trim().split('\n').map(JSON.parse);
const study=read(path.join(base,'experiment.json'));
const routerSource=execFileSync('git',['show','3df658f:server/reasoning-routing.ts'],{encoding:'utf8'});
const router=routerSource.match(/export const ROUTER_PROMPT='([^']+)';/)[1];
const output=[];
for(const run of study.runs){
 const audit=lines(path.join(base,run.label+'-audit.jsonl'));
 const es=lines(path.join(root,'data/active/workspaces',run.projectId,run.conversationId,'sessions/session.jsonl'));
 const conversation=read(path.join(base,run.label+'-conversation.json'));
 const request=read(path.join(base,run.label+'-run.json')).request;
 const question=conversation.messages.find(m=>m.id===request.userMessageId).content;
 const chainRuns=study.runs.filter(x=>x.conversationId===run.conversationId);
 const toolArgs=new Map(chainRuns.flatMap(r=>lines(path.join(base,r.label+'-audit.jsonl')).filter(x=>x.type==='tool_request').map(x=>[x.data.toolCallId,x.data])));
 let ordinal=0;
 for(const row of audit.filter(x=>x.type==='model_request')){
  const q=row.data, usage=audit.find(x=>x.type==='model_usage'&&x.data.requestId===q.requestId)?.data;
  if(!usage)throw Error('Missing usage record');
  const blocks=[];let contextChars;
  const add=(category,key,text,extra={})=>blocks.push({category,key,text,...extra});
  if(q.phase==='router'){
   const context={systemPrompt:router,messages:[{role:'user',content:question,timestamp:Date.parse(row.at)}]};
   contextChars=JSON.stringify(context).length;
   add('system_prompt','router-system',router);add('current_user_message',run.label+'-router-query',question);
  }else{
   if(q.phase!=='main')throw Error('Unimplemented phase '+q.phase);
   const prefix=es.filter(e=>e.timestamp<=row.at);
   const messages=buildSessionContext(prefix).messages;
   contextChars=JSON.stringify({messages}).length;
   const lastUser=messages.findLastIndex(m=>m.role==='user');
   for(const [mi,m] of messages.entries()){
    const key='message-'+m.timestamp+'-'+mi;
    if(m.role==='system'){
     add('system_prompt',key+'-system',getSystemMessageText(m));
     for(const tool of convertResponsesTools(m.toolsAdded||[],{supportsStrictMode:false}))
      add('tool_schema',key+'-tool-'+tool.name,JSON.stringify(tool),{tool:tool.name});
    }else if(m.role==='toolResult'){
     const call=toolArgs.get(m.toolCallId);if(!call)throw Error('Missing tool request');
     const kind=call.name==='financial_workpaper'?call.args.kind:null;
     for(const [i,b] of m.content.entries()){
      if(b.type!=='text')throw Error('Non-text tool result requires separate accounting');
      add('tool_result',key+'-'+i,b.text,{tool:m.toolName,kind,callKey:m.toolCallId,isError:!!m.isError});
     }
    }else if(m.role==='assistant'){
     for(const [i,b] of m.content.entries()){
      if(b.type==='text')add('assistant_history_text',key+'-'+i,b.text);
      else if(b.type==='toolCall')add('assistant_history_tool_arguments',key+'-'+i,JSON.stringify({name:b.name,arguments:b.arguments}),{tool:b.name});
      else if(b.type==='thinking'){
       // Opaque encrypted content is replayed by the provider, but is not plaintext tokens.
       const item=b.thinkingSignature?JSON.parse(b.thinkingSignature):null;
       const summaries=(item?.summary||[]).map(x=>x.text||'').join('\n');
       if(summaries)add('assistant_history_reasoning_summary',key+'-'+i,summaries);
       if(item?.encrypted_content)add('opaque_reasoning_envelope',key+'-'+i,'',{opaqueCharacters:item.encrypted_content.length});
      }else throw Error('Unexpected assistant block '+b.type);
     }
    }else if(m.role==='user'){
     const text=typeof m.content==='string'?m.content:m.content.map(b=>{if(b.type!=='text')throw Error('Image input');return b.text}).join('\n');
     add(mi===lastUser?'current_user_message':'prior_user_history',key,text);
    }else throw Error('Unimplemented role '+m.role);
   }
  }
  if(contextChars!==q.contextCharacters)throw Error(`Context reconstruction mismatch ${run.label} ${ordinal}: ${contextChars} != ${q.contextCharacters}`);
  output.push({label:run.label,profile:run.profile,chain:run.conversationId,ordinal:++ordinal,phase:q.phase,
   requestId:q.requestId,contextCharacters:contextChars,usageKnown:usage.usageKnown,usage:usage.usage??null,blocks});
 }
}
fs.writeFileSync(path.join(base,'private-reconstructed-contexts.json'),JSON.stringify(output));
console.log(JSON.stringify({requests:output.length,exact_context_character_matches:output.length,raw_intermediate:'N1 private only'}));

import type {Message,Source} from './types.js';

const label = /(?:\*\*)?【(事实(?:[／/]数据)?|题给事实|用户提供|题给数据[／/]计算|数据支持的结论|数据|推论|观点)(?:[^】]*)】(?:\*\*)?/;
const factual=(value?:string)=>!!value&&!['推论','观点'].includes(value);
const valuation = /估值|目标价|合理(?:股价|价值)|投资建议|(?:建议|维持|给予).{0,8}(?:买入|卖出|增持|减持|持有)|\bDCF\b|target price|fair value|investment recommendation/i;
export function valuationSections(body:string){
 if(!valuation.test(body.replace(/```[\s\S]*?```/g,'')))return [];
 // A keyword in prose is not a section. Require a heading/label with substantive content.
 const sections=[...body.matchAll(/(?:^|\n)(?:#{1,6}\s+|\*\*)([^\n*]+)(?:\*\*)?([^]*?)(?=\n#{1,6}\s|\n\*\*[^\n*]+\*\*|$)/g)];
 return ['假设','风险','适用范围'].filter(name=>!sections.some(m=>m[1].includes(name)&&m[2].replace(/[\s:：\/、*]/g,'').length>0));
}
/** Only saved, delivered user messages from this conversation can be cited. */
export function citedUserSources(body:string,messages:Message[]):Source[]{
 const ids=new Set([...body.matchAll(/\buser:([\w-]+)/g)].map(m=>m[1]));
 return messages.filter(m=>m.role==='user'&&m.status!=='queued'&&ids.has(m.id)).map(m=>({
  kind:'user_provided',messageId:m.id,sourceId:'user:'+m.id,documentId:'',title:'用户提供',quote:m.content,
 }));
}
function sourced(text:string,sources:Source[]){
 return sources.find(s=>{
  if(s.kind==='user_provided')return [...text.matchAll(/\buser:([\w-]+)/g)].some(m=>m[1]===s.messageId);
  if(s.url&&text.includes(s.url))return true;
  if(s.sourceId&&text.includes(s.sourceId))return true;
  return !!s.documentId&&text.includes(s.documentId)&&(!s.page||new RegExp(`(?:第\\s*${s.page}\\s*页|[pP]\\.?\\s*${s.page}\\b|page[=: /]${s.page}\\b)`).test(text));
 });
}
/** Unsourced/unbound prose defaults to inference/analysis. Opinions are explicit;
 * a numeric premise never upgrades an explicit causal/valuation judgment to fact. */
export function annotateAnswer(body:string,sources:Source[]=[]){
 let fenced=false;
 const lines=body.split('\n');
 return lines.map((line,index)=>{
  if(/^\s*```/.test(line)){fenced=!fenced;return line;}
  if(fenced||!line.trim()||/^\s*(?:#{1,6}\s|!\[|\[\^\w+\]:)/.test(line))return line;
  if(/^\s*\|/.test(line)){
   if(index>0&&/^\s*\|/.test(lines[index-1]))return line;
   let end=index+1;while(end<lines.length&&/^\s*\|/.test(lines[end]))end++;
   const block=lines.slice(index,end).join('\n');
   return (/\{\{\s*(?!chart:)[^{}]+\}\}/.test(block)||sourced(block,sources)?'【事实/数据】':'【推论/分析】')+'\n\n'+line;
  }
  if(/^\s*(?:【事实(?:\/数据)?】\s*)?\{\{table:[^{}]+\}\}\s*$/.test(line))return '【事实/数据】\n\n'+line.replace(label,'').trim();
  const prefix=line.match(/^\s*(?:[-*+]\s+|\d+\.\s+|>\s*)?/)![0];
  let inherited:string|undefined;
  return prefix+line.slice(prefix.length).split(/(?<=[。！？])(?=[^”’」』]|$)/u).map(sentence=>{
   if(!sentence.trim())return sentence;
   const marked=sentence.match(label)?.[1];if(marked)inherited=marked;
   const bound=/\{\{\s*(?!chart:)[^{}]+\}\}/.test(sentence),ref=sourced(sentence,sources);
   const evidence=bound||!!ref,factLabel=!bound&&ref?.kind==='user_provided'?'【事实/用户提供】':'【事实/数据】';
   const text=sentence.replace(label,'');
   // Explicit inference/opinion can contain a bound premise without becoming a fact.
   if(marked==='推论'||marked==='观点')return sentence;
   if(inherited==='推论'||inherited==='观点')return '【'+inherited+'】'+sentence;
   if(evidence&&!inherited)return factLabel+sentence;
   if(factual(marked||inherited))return evidence?factLabel+text:'【推论·缺少绑定或来源】'+text;
   return '【推论/分析】'+sentence;
  }).join('');
 }).join('\n');
}
export function requireValuationSections(body:string){
 const missing=valuationSections(body);
 if(missing.length)throw Object.assign(new Error('估值或投资判断缺少有内容的小节：'+missing.join(' / ')+'。请保留已核对数值，补全后重新给出完整回答；资料不足要明确说明。'),{code:'answer_contract_error'});
}

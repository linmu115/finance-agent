import type {Message,Source} from './types.js';

const label = /(?:\*\*)?【(事实(?:[／/]数据)?|题给事实|用户提供|题给数据[／/]计算|数据支持的结论|数据|推论|观点)(?:[^】]*)】(?:\*\*)?/;
const factual=(value?:string)=>!!value&&!['推论','观点'].includes(value);
const sectionNames=['假设','风险','适用范围'];
/** Detect an asserted conclusion, not a mention of the topic or a quoted recommendation. */
export function hasValuationJudgment(body:string){
 const text=body.replace(/```[\s\S]*?```|`[^`\n]*`/g,'').replace(/^\s*>.*$/gm,'')
  .replace(/[“「][^”」]*[”」]|"[^"\n]*"/g,'').replace(/\*\*|__/g,'');
 return text.split(/[。！？；;\n]|(?:但是|但|然而|\bbut\b)/i).some(sentence=>{
  const clause=sentence.trim().replace(/估值(?:日|时点|方法|输入|参数|假设|模型|所需)|\bDCF\s*(?:模型|方法|输入|参数|所需)/gi,'');
  if(!clause||/^#{1,6}\s.*(?:假设|风险|适用范围)/.test(clause))return false;
  // Negation applies to a clause, never to the complete answer.
  if(/(?:不(?:做|提供|给出|构成|作|含|涉及|属于|应)|未(?:做|提供|给出|建立)|无法|不能|不足以|并非|没有).*(?:估值|目标价|建议|投资|DCF)|(?:估值|投资判断|投资建议)\s*[:：]\s*(?:无|不适用)|\b(?:no|not|without|cannot|can't)\b.*(?:valuation|target price|fair value|recommend)/i.test(clause))return false;
  if(/(?:估值|目标价|合理价值)\s*(?:不(?:是|为|等于)|并非|未提供|无法确定)/.test(clause))return false;
  if(/(?:研报|机构|券商|分析师|管理层|公司|报告|原文).{0,12}(?:给出|认为|建议|预计|预测|提出|披露|维持|称)|(?:引用|引述).*(?:估值|目标价)|\b(?:analyst|broker|management|report)\b.*\b(?:states?|says?|quotes?|recommends?|targets?)\b/i.test(clause)&&!/(?:我们|本次|本文).*(?:认为|判断|建议|测算)|\bwe\s+(?:estimate|recommend|value)/i.test(clause))return false;
  return /(?:估值|目标价|合理(?:股价|价值)|内在价值|\bDCF\b|target price|fair value).{0,32}(?:\d|\{\{|偏高|偏低|合理|低估|高估)|(?:建议|维持|给予).{0,8}(?:买入|卖出|增持|减持|持有)|(?:被低估|被高估)|\b(?:recommend|rating)\b.{0,24}\b(?:buy|sell|hold)\b/i.test(clause);
 });
}
export function valuationSections(body:string){
 if(!hasValuationJudgment(body))return [];
 const found=new Set<string>();let active:string[]=[],tableHeaders:string[][]=[];
 const meaningful=(s:string)=>!!s.replace(/[\s:：\/、*|#\-]/g,'')&&!/^(?:待补充|待填写|TODO|TBD|暂无|无)$/i.test(s.trim());
 const names=(s:string)=>sectionNames.filter(name=>s.includes(name));
 for(const raw of body.replace(/```[\s\S]*?```/g,'').split('\n')){
  const line=raw.trim().replace(/\*\*|__/g,'');if(!line)continue;
  if(line.startsWith('|')){
   const cells=line.replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
   if(cells.every(c=>/^[-:\s]+$/.test(c)))continue;
   const headers=cells.map(names);
   if(headers.filter(h=>h.length).length>1&&cells.every((c,i)=>headers[i].length||!meaningful(c))){tableHeaders=headers;continue;}
   if(tableHeaders.length){for(let i=0;i<cells.length;i++)if(meaningful(cells[i]))for(const name of tableHeaders[i]||[])found.add(name);continue;}
   if(headers[0]?.length&&cells.slice(1).some(meaningful))for(const name of headers[0])found.add(name);
   continue;
  }
  tableHeaders=[];
  // A merged heading may use several labelled clauses on the following line.
  for(const clause of active.length>1?line.split(/[；;。]/):[]){
   const inline=clause.trim().match(/^(假设|风险|适用范围)\s*[:：为是]?\s*(.+)$/);
   if(inline&&!/^[\/／、]/.test(inline[2])&&meaningful(inline[2]))found.add(inline[1]);
  }
  const heading=/^#{1,6}\s/.test(line);
  const labelLine=line.replace(/^#{1,6}\s+|^(?:[-*+]\s+|\d+[.)、]\s*)/,'');
  const labelMatch=labelLine.match(/^(假设|风险|适用范围)(?:\s*[\/／、和与]\s*(?:假设|风险|适用范围))*\s*[:：]?\s*/);
  if(labelMatch){
   active=names(labelMatch[0]);const content=labelLine.slice(labelMatch[0].length);
   if(meaningful(content))for(const name of active)found.add(name);
  }else if(heading){active=names(labelLine);}
  else if(meaningful(line)){for(const name of active)found.add(name);}
 }
 return sectionNames.filter(name=>!found.has(name));
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
  if(!s.documentId||!text.includes(s.documentId))return false;
  const page=s.page;if(!page)return true;
  // A source locator can name a page list/range, not just one page.
  const locators=[...text.matchAll(/(?:第|PDF\s*第?|\bpage[=: /]+|(?<![A-Za-z])[pP]\.?)\s*(\d+(?:\s*[-–—至,，、/及与]\s*\d+)*)\s*页?/gi)];
  return locators.some(m=>[...m[1].matchAll(/(\d+)(?:\s*[-–—至]\s*(\d+))?/g)].some(p=>page>=Number(p[1])&&page<=Number(p[2]??p[1])));
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
  // Keep closing quotes/emphasis with their sentence, so labels cannot split **…**.
  const sentences=line.slice(prefix.length).match(/[^]*?[。！？](?:[”’」』）)]|\*\*|__)*|[^]+$/gu)??[];
  let displayedLabel:string|undefined;
  const classified=sentences.map(sentence=>{
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
  });
  return prefix+classified.map(sentence=>{
   const marker=sentence.match(label)?.[0];
   if(!marker)return sentence;
   if(marker===displayedLabel)return sentence.replace(label,'');
   displayedLabel=marker;return sentence;
  }).join('');
 }).join('\n');
}
export function requireValuationSections(body:string){
 const missing=valuationSections(body);
 if(missing.length)throw Object.assign(new Error('估值或投资判断缺少有内容的小节：'+missing.join(' / ')+'。请保留已核对数值，补全后重新给出完整回答；资料不足要明确说明。'),{code:'answer_contract_error'});
}

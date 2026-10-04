import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
// @ts-expect-error independent host scorer
import {scoreReportCorrection} from '../scripts/score_report_correction_v01.mjs';

function sample(){
 const source='2022年营业收入12.35万元；2023年营业收入13.50万元。';
 const statements=[['error','2022年营业收入为12.53万元。'],['protected','2023年营业收入为13.50万元。'],['protected','我认为明年需求可能走弱。']];
 let original='📊 独立核对\n';const claims:any[]=[];
 for(let i=0;i<statements.length;i++){
  const [kind,text]=statements[i],start=original.length;original+=text+'\n';
  const claim:any={id:'C'+i,kind,text,start,end:start+text.length,evidence:i===2?[]:[{input_page:1,original_page:9,anchors_all:[i===0?'12.35':'13.50']}],claim_type:i===2?'inference':'fact'};
  if(kind==='error'){const at=start+text.indexOf('12.53');Object.assign(claim,{target:{start:at,end:at+5,original:'12.53'},accepted_replacements:['12.35'],category:'number'});}
  claims.push(claim);
 }
 const gold={original_text_sha256:createHash('sha256').update(original).digest('hex'),claims,thresholds:{correction_precision:.95,correction_recall:.9}};
 const evidence=[{kind:'document',id:'actual-id',locator:'page:1',quote:source}];
 const issue={id:'fix',...claims[0].target,replacement:'12.35',category:'number',reason:'小数位误写',evidence};
 const make=(issues:any[]= [issue])=>{
  let cursor=0,revised='';for(const i of [...issues].sort((a,b)=>a.start-b.start)){revised+=original.slice(cursor,i.start)+i.replacement;cursor=i.end;}revised+=original.slice(cursor);
  return {kind:'report_correction',content:{original_text:original,issues,revised_text:revised,verified_claims:[{id:'C1',text:claims[1].text,type:'fact',evidence}]}};
 };
 const score=(artifact:any)=>scoreReportCorrection(gold,original,artifact,{documentId:'actual-id',sourcePages:{1:source}});
 return {source,original,claims,gold,issue,make,score};
}

test('UTF-16 patches accept minimal edit and unchanged-context expanded span, exact financial correction',()=>{
 const s=sample();assert.equal(s.score(s.make()).status,'passed');
 const c=s.claims[0];assert.equal(s.score(s.make([{...s.issue,start:c.start,end:c.end,original:c.text,replacement:c.text.replace('12.53','12.35')}])).status,'passed');
 const wrongOffset={...s.issue,start:s.issue.start-1,end:s.issue.end-1};assert.equal(s.score(s.make([wrongOffset])).score.true_corrections,0);
 const wrongScale={...s.issue,start:c.start,end:c.end,original:c.text,replacement:'2022年营业收入为12.35元。'};
 assert.equal(s.score(s.make([wrongScale])).score.true_corrections,0);
});

test('host verifies exact original, saved patch output, real document/page/quote and corrected replacement',()=>{
 const s=sample();
 for(const evidence of [[],[{...s.issue.evidence[0],id:'forged-id'}],[{...s.issue.evidence[0],locator:'page:9'}],[{...s.issue.evidence[0],quote:'凭空捏造12.35'}]])assert.equal(s.score(s.make([{...s.issue,evidence}])).score.true_corrections,0);
 const merelyFlagged=s.score(s.make([{...s.issue,replacement:'有待确认'}]));assert.equal(merelyFlagged.score.detection_recall,1);assert.equal(merelyFlagged.score.correction_recall,0);
 const changed=s.make();changed.content.original_text+=' ';assert.equal(s.score(changed).status,'failed');
 const saved=s.make();saved.content.revised_text+='无授权修改';assert.equal(s.score(saved).status,'failed');
});

test('false positives, duplicates, deleting errors and rewriting opinions cannot pass',()=>{
 const s=sample(),protectedClaim=s.claims[1],opinion=s.claims[2];
 const falsePositive={...s.issue,id:'unnecessary',start:protectedClaim.start,end:protectedClaim.end,original:protectedClaim.text,replacement:protectedClaim.text.replace('13.50','14.00')};
 const over=s.score(s.make([s.issue,falsePositive]));assert.equal(over.score.correction_precision,.5);assert.equal(over.score.protected_claims_changed,1);assert.equal(over.status,'failed');
 const duplicate=s.score(s.make([s.issue,{...s.issue,id:'again'}]));assert.equal(duplicate.score.true_corrections,0);assert.equal(duplicate.score.submitted_issues,2);
 const c=s.claims[0];assert.equal(s.score(s.make([{...s.issue,start:c.start,end:c.end,original:c.text,replacement:''}])).score.true_corrections,0);
 const opinionIssue={...s.issue,id:'opinion',start:opinion.start,end:opinion.end,original:opinion.text,replacement:'明年需求一定走强。'};
 assert.equal(s.score(s.make([s.issue,opinionIssue])).score.opinions_changed,1);
});

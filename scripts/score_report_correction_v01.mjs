// Independent host-only scoring. Never invokes a model or production patcher.
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
export const SCORER_VERSION='report-correction-0.1.0';
const sha=s=>createHash('sha256').update(s,'utf8').digest('hex');
const compact=s=>String(s??'').replace(/\s/g,'');
export const normalizeCorrectionText=s=>compact(String(s??'').normalize('NFKC'))
 .replace(/(?<=\d),(?=\d)/g,'').replace(/[−－]/g,'-').replace(/[／÷]/g,'/').replace(/[＊*]/g,'×');
const overlap=(a,b)=>a.start<b.end&&b.start<a.end;
const same=(a,b)=>normalizeCorrectionText(a)===normalizeCorrectionText(b);

function evidenceCheck(claim,evidence,documentId,pages){
 const errors=[],byPage=new Map();
 for(const ref of evidence||[]){
  const match=/^page:(\d+)$/.exec(ref.locator||'');
  if(ref.kind!=='document'||ref.id!==documentId||!match){errors.push('wrong_document_or_page_reference');continue;}
  const page=Number(match[1]),source=pages[page]??pages[String(page)];
  if(typeof ref.quote!=='string'||!compact(ref.quote)||typeof source!=='string'||!compact(source).includes(compact(ref.quote))){errors.push('quote_not_in_frozen_original_page');continue;}
  byPage.set(page,(byPage.get(page)||'')+compact(ref.quote));
 }
 for(const ref of claim.evidence||[]){
  const cited=byPage.get(ref.input_page)||'';
  for(const anchor of ref.anchors_all)if(!cited.includes(compact(anchor)))errors.push('missing_source_anchor_page_'+ref.input_page);
 }
 return [...new Set(errors)];
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const argv=process.argv.slice(2),arg=(n,d)=>argv.includes(n)?argv[argv.indexOf(n)+1]:d;
 if(argv.includes('--help'))console.log('node score_report_correction_v01.mjs --suite DIR --artifact saved-report.json --document-id ACTUAL_ID --output NEW.json. Read-only scoring; no model or network.');
 else{
  const directory=path.resolve(arg('--suite',path.join(import.meta.dirname,'../benchmark/versions/v0.1-report-correction'))),artifactFile=arg('--artifact'),documentId=arg('--document-id'),output=arg('--output');
  if(!artifactFile||!documentId||!output)throw Error('--artifact, --document-id and --output are required');
  const manifest=JSON.parse(await fs.readFile(path.join(directory,'manifest.json'),'utf8'));
  for(const [file,expected] of Object.entries(manifest.files))if(createHash('sha256').update(await fs.readFile(path.join(directory,file))).digest('hex')!==expected)throw Error('Frozen fixture hash changed: '+file);
  const gold=JSON.parse(await fs.readFile(path.join(directory,'gold.json'),'utf8')),original=await fs.readFile(path.join(directory,'REPORT.txt'),'utf8'),mapping=JSON.parse(await fs.readFile(path.join(directory,'source-map.json'),'utf8')),sourcePages={};
  for(const p of mapping.page_mapping)sourcePages[p.input_page]=await fs.readFile(path.join(directory,'evidence/original-page-'+p.original_page+'.txt'),'utf8');
  const artifactText=await fs.readFile(path.resolve(artifactFile),'utf8'),report=scoreReportCorrection(gold,original,JSON.parse(artifactText),{documentId,sourcePages});
  await fs.writeFile(path.resolve(output),JSON.stringify({...report,kind:'read_only_artifact_score',artifact_sha256:sha(artifactText),scorer_sha256:sha(await fs.readFile(fileURLToPath(import.meta.url),'utf8')),gold_sha256:manifest.files['gold.json'],model_calls:0},null,2),{flag:'wx'});
  console.log(report.status,JSON.stringify(report.score));
 }
}

/** gold is parsed only host-side after terminal; pages are independent originals. */
export function scoreReportCorrection(gold,originalText,artifact,{documentId,sourcePages}={}){
 if(!documentId||!sourcePages)throw Error('Host must supply actual uploaded document ID and frozen original page text');
 if(sha(originalText)!==gold.original_text_sha256)throw Error('Frozen original text hash mismatch');
 const content=artifact?.content??artifact,issues=Array.isArray(content?.issues)?content.issues:[],errors=[];
 if(artifact?.kind&&artifact.kind!=='report_correction')errors.push('artifact_kind');
 if(content?.original_text!==originalText)errors.push('original_text_changed');
 const claims=gold.claims,expected=claims.filter(c=>c.kind==='error'),protectedClaims=claims.filter(c=>c.kind==='protected');
 const checked=issues.map((issue,index)=>{
  const e=[];
  if(!Number.isInteger(issue.start)||!Number.isInteger(issue.end)||issue.start<0||issue.end<=issue.start||issue.end>originalText.length||originalText.slice(issue.start,issue.end)!==issue.original)e.push('invalid_utf16_original_location');
  if(typeof issue.replacement!=='string'||!issue.replacement||issue.replacement===issue.original)e.push('empty_or_no_op_replacement');
  if(!issue.id||issues.filter(x=>x.id===issue.id).length!==1)e.push('duplicate_or_missing_issue_id');
  const claim=claims.find(c=>issue.start>=c.start&&issue.end<=c.end);
  if(!claim)e.push('outside_single_claim');
  else if(claim.kind!=='error')e.push('protected_claim_flagged');
  else if(!overlap(issue,claim.target))e.push('location_does_not_touch_error');
  return {index,id:issue.id,claim_id:claim?.id,start:issue.start,end:issue.end,errors:e};
 });
 for(const item of checked){
  const issue=issues[item.index],claim=expected.find(c=>c.id===item.claim_id);
  if(checked.some(other=>other.index!==item.index&&overlap(item,other)))item.errors.push('overlapping_corrections');
  if(claim&&checked.filter(x=>x.claim_id===claim.id).length!==1)item.errors.push('duplicate_corrections_for_one_error');
  if(claim&&!item.errors.includes('invalid_utf16_original_location')){
   const revised=claim.text.slice(0,issue.start-claim.start)+issue.replacement+claim.text.slice(issue.end-claim.start);
   const targetStart=claim.target.start-claim.start,targetEnd=claim.target.end-claim.start;
   const accepted=claim.accepted_replacements.map(r=>claim.text.slice(0,targetStart)+r+claim.text.slice(targetEnd));
   item.corrected_claim=revised;
   if(!accepted.some(a=>same(a,revised)))item.errors.push('replacement_not_correct_or_changed_other_content');
   item.errors.push(...evidenceCheck(claim,issue.evidence,documentId,sourcePages));
   // Category is diagnostic, not a language-dependent financial correctness gate.
   item.reported_category=issue.category;item.expected_category=claim.category;
  }
  item.status=item.errors.length?'failed':'passed';
 }
 const checks=expected.map(c=>{
  const found=checked.filter(i=>i.claim_id===c.id);
  return {id:c.id,category:c.category,status:found.length===1&&found[0].status==='passed'?'passed':'failed',
   expected:{original:c.target.original,accepted_replacements:c.accepted_replacements,evidence:c.evidence},
   submitted_issue_ids:found.map(i=>i.id),errors:found.length?found.flatMap(i=>i.errors):['not_detected'],
   original_location:{start:c.target.start,end:c.target.end}};
 });
 const protectedResults=protectedClaims.map(c=>{
  const touching=checked.filter(i=>overlap(i,c));
  return {id:c.id,type:c.claim_type,text:c.text,flagged:touching.length>0,changed:touching.some(i=>issues[i.index].replacement!==issues[i.index].original),issue_ids:touching.map(i=>i.id)};
 });
 const validLocations=checked.every(c=>!c.errors.includes('invalid_utf16_original_location')&&!c.errors.includes('overlapping_corrections'));
 let revisedText=null;
 if(validLocations){let cursor=0;revisedText='';for(const issue of [...issues].sort((a,b)=>a.start-b.start)){revisedText+=originalText.slice(cursor,issue.start)+issue.replacement;cursor=issue.end;}revisedText+=originalText.slice(cursor);}
 if(!validLocations)errors.push('cannot_apply_patches');
 if(content?.revised_text!==revisedText)errors.push('saved_revised_text_not_independent_patch_result');
 const verified=Array.isArray(content?.verified_claims)?content.verified_claims:[];
 const verifiedChecks=protectedClaims.filter(c=>c.claim_type!=='inference').map(c=>{
  const found=verified.filter(v=>v.id===c.id),v=found[0],errs=[];
  if(found.length!==1)errs.push('missing_or_duplicate_verified_claim');
  else {if(!same(v.text,c.text))errs.push('verified_claim_text_changed');if(v.type!==c.claim_type)errs.push('claim_type');errs.push(...evidenceCheck(c,v.evidence,documentId,sourcePages));}
  return {id:c.id,status:errs.length?'failed':'passed',errors:errs};
 });
 const falseVerified=verified.filter(v=>expected.some(c=>c.id===v.id&&same(v.text,c.text)));
 const corrected=checks.filter(c=>c.status==='passed').length;
 const detectedKeys=new Set(checked.filter(i=>expected.some(c=>c.id===i.claim_id)&&!i.errors.includes('invalid_utf16_original_location')&&!i.errors.includes('location_does_not_touch_error')).map(i=>i.claim_id));
 const score={true_corrections:corrected,submitted_issues:issues.length,expected_errors:expected.length,false_or_invalid_corrections:issues.length-corrected,missed_or_incorrect:expected.length-corrected,
  correction_precision:issues.length?corrected/issues.length:0,correction_recall:corrected/expected.length,
  detection_precision:issues.length?detectedKeys.size/issues.length:0,detection_recall:detectedKeys.size/expected.length,
  protected_claims_changed:protectedResults.filter(c=>c.changed&&c.type!=='inference').length,opinions_changed:protectedResults.filter(c=>c.changed&&c.type==='inference').length,
  correct_claims_verified:verifiedChecks.filter(c=>c.status==='passed').length,expected_correct_claims:verifiedChecks.length,errors_incorrectly_verified:falseVerified.map(v=>v.id)};
 const acceptance={thresholds:gold.thresholds,correction_gate:score.correction_precision>=gold.thresholds.correction_precision&&score.correction_recall>=gold.thresholds.correction_recall,
  protection_gate:score.protected_claims_changed===0&&score.opinions_changed===0,
  output_integrity_gate:errors.length===0&&falseVerified.length===0};
 return {version:SCORER_VERSION,status:Object.values(acceptance).slice(1).every(Boolean)?'passed':'failed',score,acceptance,errors,checks,issue_checks:checked,protected_claims:protectedResults,verified_claims:verifiedChecks,
  normalization:{expected_facts:expected.length,passed_facts:corrected,failed_facts:expected.length-corrected,checks:checks.map(c=>({...c,file:'REPORT.txt',expected:{metric:c.category,period:'2024',value:c.expected.accepted_replacements.join(' | ')}}))},
  original_sha256:sha(originalText),revised_sha256:revisedText===null?null:sha(revisedText)};
}

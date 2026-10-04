/** Read-only correction of an overly narrow source-index assertion; never reruns models. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { buildSessionContext } from '@earendil-works/pi-coding-agent';
const root=path.resolve(import.meta.dirname,'..');
const reportDir=path.join(root,'benchmark/results/restore-v08-20261004');
const raw=await fs.readFile(path.join(reportDir,'compaction-live.json'));
const original=JSON.parse(raw.toString());
const project=JSON.parse(await fs.readFile(path.join(reportDir,'network-workflow.json'),'utf8')).project_id;
const sourceId='web_f34cddc6-52c8-41ea-a7e1-f290981805af';
const checks=[];
for(const arm of original.arms){
 const session=path.join(root,'data/compaction-acceptance-20261004/workspaces',project,arm.conversation_id,'sessions/session.jsonl');
 const entries=(await fs.readFile(session,'utf8')).trim().split('\n').map(JSON.parse);
 const checkpoints=entries.filter(e=>e.type==='compaction');
 for(const checkpoint of checkpoints){
  const prefix=entries.slice(1,entries.indexOf(checkpoint)+1);
  const context=buildSessionContext(prefix);
  const retained=context.messages.filter(m=>m.role==='toolResult'&&JSON.stringify(m.content).includes(sourceId));
  checks.push({name:'saved_source_in_effective_context_at_checkpoint',conversation_id:arm.conversation_id,
   checkpoint_id:checkpoint.id,first_kept_entry_id:checkpoint.firstKeptEntryId,
   source_id:sourceId,retained_tool_names:retained.map(m=>m.toolName),
   passed:retained.length>0||(checkpoint.details?.recoveryReferences?.sources||[]).includes(sourceId)});
 }
 checks.push({name:'all_other_original_assertions_pass',enabled:arm.enabled,
  passed:arm.checks.filter(c=>c.name!=='exact_saved_source_pointer_retained').every(c=>c.passed)});
 const answer=arm.runs.at(-1)?.answer||'';
 checks.push({name:'final_answer_marks_missing_ebit_interest_evidence',enabled:arm.enabled,
  passed:/EBIT/.test(answer)&&/利息/.test(answer)&&/无法|不能|不足/.test(answer)&&/13\.21/.test(answer)&&/25\.05/.test(answer)});
}
const off=original.arms.find(a=>!a.enabled).usage,on=original.arms.find(a=>a.enabled).usage;
const totalInput=u=>u.input+u.cacheRead+u.cacheWrite;
const review={created_at:new Date().toISOString(),kind:'read_only_effective_context_review',
 original_status:original.status,original_report_sha256:createHash('sha256').update(raw).digest('hex'),
 correction:'The first assertion searched only the checkpoint recovery index. Pi kept the final source tool message as recent verbatim history, so the source need not occur in the compressed prefix index. Verify the reconstructed effective context at the checkpoint instead. The original failed report is unchanged.',
 checks,status:checks.every(c=>c.passed)?'passed':'failed',
 usage:{disabled:{...off,total_input:totalInput(off)},enabled:{...on,total_input:totalInput(on)},input_reduction_fraction:1-totalInput(on)/totalInput(off),cost_usd:null},
 limits:'One short real-history fork comparison with a lowered 16k trigger, sequential cache conditions and no pricing configured. It does not establish monetary savings, default-96k behavior, artifact revision recovery, document table recovery, held-out accuracy or the entire six-stage product acceptance.'};
await fs.writeFile(path.join(reportDir,'compaction-independent-review.json'),JSON.stringify(review,null,2),{flag:'wx'});
console.log(JSON.stringify(review,null,2));
if(review.status!=='passed')process.exitCode=1;

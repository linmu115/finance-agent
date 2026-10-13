"""Offline plan and current authorization update; never starts participant runs."""
import hashlib,json,statistics
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/evaluation/blind-eval-formal-plan-20261008'
OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def write(p,x):(ROOT/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
now=datetime.now(timezone.utc).isoformat()
draft='data/evaluation/blind-eval-analyst-alignment-20261008/new-task-drafts.json'
d=read(draft);before={t['id']:hashlib.sha256(t['prompt'].encode()).hexdigest() for t in d['tasks']}
d['status']='prompts_approved_20261008_references_pending_final_freeze'
for t in d['tasks']:t['status']='approved_prompt_pending_material_and_reference_freeze'
d['approval']={'at':now,'authority':'Claude latest instruction: X6/X7 approved; N3 owns Yili Q3 reprocessing and Haier CAS full ingestion.'}
write(draft,d)
mfile='data/evaluation/blind-eval-analyst-alignment-20261008/new-material-plan.json'
m=read(mfile);m['updated_at']=now
states={'yili_q3':('N3_ingested_period_reprocessing_pending',True),'haier_2024':('N3_queued_after_Yili_annual',False),'yili_2024':('N3_resuming_on_3001',True)}
for v in m['materials']:
 v['preparation_status'],v['model_ingestion_started']=states[v['id']]
 v['execution_owner']='N3';v['status_authority']='Claude latest instruction, API snapshot in blind-eval-formal-plan-20261008; historical matches retained with their original observation scope.'
m['proposed_projects']['haier_2024']='已批准：独立项目 海尔智家 2024，由N3创建/入库，ID待回报'
m['policy']='X6/X7题面与完整材料已获批准；N3执行伊利年报、三季报重处理及海尔CAS年报。N1只准备参考/方案，不替N3入库，不迁移旧库。'
write(mfile,m)
sfile='data/evaluation/blind-eval-preparation-20261007/approved-scope.json'
s=read(sfile)
s.setdefault('decision_history',[]).append({'previous_authority':s['authority'],'superseded_at':now})
s['at']=now;s['authority']='Claude authorizes Qingdao one resume on 58a903c/3001; X6/X7 approved; formal comparison remains plan only pending N4 final freeze and go-ahead.'
s['tasks'].update({'X6':'approved; annual+Q3; N3 reprocessing periods','X7':'approved; CAS annual; N3 independent 海尔智家 2024 project','X2':'optional formal task only if Midea ready and scope approved; no N1 ingestion authorization'})
s['ingestion_order']=['tsingtao_2024_resume_only']
s['excluded_ingestion']=['yili_2023','midea_2024']
s['n1_excluded_ingestion']=['yili_2024','yili_q3','haier_2024']
s['paused_ingestion']={}
s['ingestion_owners']={'tsingtao_2024':'N1 one resume, native continuation only','yili_2024':'N3 currently resuming','yili_q3':'N3 period reprocessing','haier_2024':'N3 after Yili annual'}
s['tsingtao_resume_ledger']='data/evaluation/blind-eval-tsingtao-resume-20261008/preparation.json'
write(sfile,s)
groups=[('development',['D1','D2','D3']),('yili',['X1','X3','X4','X5','X6']),('haier',['X7']),('heldout',['H1','H2'])]
task_ids=[t for _,ts in groups for t in ts];indices={t:i for i,t in enumerate(task_ids)}
parents={'D3':'D2','H2':'H1'};schedule=[]
for repeat in [1,2]:
 for cohort,tasks in (groups if repeat==1 else list(reversed(groups))):
  for task in tasks:
   order=['prepared','financial'] if indices[task]%2==0 else ['financial','prepared']
   if repeat==2:order.reverse()
   for profile in order:
    schedule.append({'sequence':len(schedule)+1,'cohort':cohort,'task_id':task,'repeat':repeat,'profile':profile,'conversation_key':f'{profile}-r{repeat}-{parents.get(task,task)}','parent_task':parents.get(task),'status':'proposal_not_submitted'})
assert len(schedule)==44
assert all({(r['repeat'],r['profile']) for r in schedule if r['task_id']==t}=={(i,p) for i in [1,2] for p in ['prepared','financial']} for t in task_ids)
for r in schedule:
 if r['parent_task']:assert any(x['task_id']==r['parent_task'] and x['profile']==r['profile'] and x['repeat']==r['repeat'] for x in schedule[:r['sequence']-1])
specs=[('ordinary',['D1','X1','X4'],[8,30],[100000,2000000],[4000,18000]),('valuation',['D2'],[12,40],[300000,2500000],[6000,30000]),('update',['D3','H2'],[6,18],[200000,1000000],[2000,12000]),('complex',['X3','X5','X6','X7','H1'],[15,45],[500000,3000000],[6000,30000])]
est=[];totals={k:[0,0] for k in ['requests','input','output']}
for kind,tasks,req,inp,out in specs:
 n=len(tasks)*4; row={'kind':kind,'tasks':tasks,'turns':n,'per_turn':dict(requests=req,input=inp,output=out)}
 row['subtotal']={k:[v*n for v in rg] for k,rg in row['per_turn'].items()}
 for k,rg in row['subtotal'].items():totals[k]=[a+b for a,b in zip(totals[k],rg)]
 est.append(row)
historical=[]
for p in sorted((ROOT/'data/evaluation/pi-cowork-acceptance-20261006').glob('*-run.json')):
 r=json.loads(p.read_text(encoding='utf-8'));u=r.get('usage') or {}
 historical.append({'label':p.stem[:-4],'status':r['status'],**{k:u.get(k) for k in ['calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls','costUsd']}})
complete=[r for r in historical if r['status']=='completed']
summary={k:{'min':min(r[k] for r in complete),'median':statistics.median(r[k] for r in complete),'max':max(r[k] for r in complete)} for k in ['calls','input','output','uncachedInput','reasoning']}
plan={'status':'proposal_only_not_frozen_not_authorized_to_execute','created_at':now,'participant_model':'cpa-local/gpt-6-luna','judge':{'model':'gpt-6-astra','reasoning_effort':'high','fresh_threads':8,'cohorts':['development','yili','haier','heldout'],'rounds':2,'provider_requests':None,'estimated_input_scenario':[800000,3200000],'estimated_output_scenario':[96000,320000],'basis':'planning envelope for 8 fresh sessions; historical judge token telemetry unavailable, recalculate from actual anonymous package before approval'},'task_ids':task_ids,'optional':['X2'],'repeats_per_arm':2,'participant_turns':44,'fresh_conversations':36,'with_X2':{'participant_turns':48,'fresh_conversations':40,'additional_requests':[60,180],'additional_input':[2000000,12000000],'additional_output':[24000,120000]},'schedule':schedule,'estimates':{'basis':'Historical 12 completed turns give scale only; wider planning ranges cover new annual, multi-source and report tasks. Not a cap, confidence interval or measured new-version cost. Excludes ingestion and judging.','by_kind':est,'totals':totals,'uncached_input':None,'cache_read':None,'cache_write':None,'reasoning':None,'unknown_usage':None,'provider_billed_cost':None},'historical_usage':historical,'historical_completed_summary':summary,'prompt_approval_verification':{'before':before,'after':{t['id']:hashlib.sha256(t['prompt'].encode()).hexdigest() for t in d['tasks']},'unchanged':True},'runtime_candidate':'58a903c; final version awaits N4 merge and explicit freeze/go-ahead','execution_implementation':'Current runner is one-project and task-ordered. Global schedule, complete freeze and cross-conversation artifact isolation must be made concrete after this plan is approved. No start/run/freeze issued.'}
write('data/evaluation/blind-eval-formal-plan-20261008/plan.json',plan)
write('data/evaluation/blind-eval-formal-plan-20261008/validation.json',{'at':now,'offline_only':True,'participant_requests_submitted':0,'turns':len(schedule),'conversations':len({r['conversation_key'] for r in schedule}),'paired_repeats_complete':True,'continuation_dependencies_valid':True,'X6_X7_prompts_unchanged':before=={t['id']:hashlib.sha256(t['prompt'].encode()).hexdigest() for t in d['tasks']}})
print(json.dumps({'turns':44,'conversations':36,'estimates':totals,'historical':summary},ensure_ascii=False))

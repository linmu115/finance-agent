"""Assemble approved prompts without rewriting their financial instructions."""
from blind import ROOT,read,dump
here=ROOT/'benchmark/blind-eval'
dev=read(here/'development-config.json')
ext=read(ROOT/'data/evaluation/blind-eval-preparation-20261007/task-drafts.json')['tasks']
new=read(ROOT/'data/evaluation/blind-eval-analyst-alignment-20261008/new-task-drafts.json')['tasks']
carote='03b52dde-19da-49c1-949a-ee6d93bf036b';yili='374beac2-a970-4972-b210-e91018bbd6e6'
tasks=[]
for t in dev['tasks']:
 t={**t,'id':'D'+t['id'],'projectId':carote,'phase':1}
 if t.get('continuationOf'):t['continuationOf']='D'+t['continuationOf']
 tasks.append(t)
for taskid in ['X1','X3','X4','X5','X6','X7','H1','H2']:
 t=next(t for t in ext+new if t['id']==taskid)
 tasks.append({**{k:t[k] for k in ['id','split','type','prompt','materials','continuationOf'] if k in t},'phase':1 if taskid in ['X4','X5','X6'] else 2,'projectId':'d324c744-4113-4213-aa22-af3bb91a3c84' if taskid=='X7' else '8513b99f-9168-4156-a92f-8df20d84d51b' if taskid.startswith('H') else yili})
config={'schema':'f1-approved-20261008','model':'gpt-6-luna','provider':'cpa-local','repeats':2,'tasks':tasks,'evaluationLimits':dev['evaluationLimits'],'phases':{
 '1':{'blocks':[['D1','D2','D3'],['X4','X5','X6']],'referenceFiles':['benchmark/blind-eval/reference-development.json','benchmark/blind-eval/reference-notes.md','benchmark/blind-eval/reference-phase1.json','benchmark/blind-eval/selectors-phase1.json','data/evaluation/blind-eval-f1-preparation-20261008/reference-freeze.json']},
 '2':{'blocks':[['X1','X3'],['X7'],['H1','H2']],'referenceFiles':['benchmark/blind-eval/reference-phase2.json','benchmark/blind-eval/selectors-phase2.json']}},
 'referenceFiles':['benchmark/blind-eval/rubric.md','benchmark/blind-eval/metrics.py','benchmark/blind-eval/blind.py','benchmark/blind-eval/replay.py','benchmark/blind-eval/make-judge-reference.py','benchmark/blind-eval/runner-f1.mjs','benchmark/blind-eval/study-f1.mjs','benchmark/blind-eval/snapshot-f1.py','benchmark/blind-eval/a5-adapter.py','benchmark/blind-eval/selectors-f1.py','benchmark/blind-eval/F1_EXECUTION.md','scripts/collect-pi-analysis.mjs','scripts/scan-delivery-consistency.py'],
 'preparationLedgers':['data/evaluation/blind-eval-ingestion-20261007/preparation.json','data/evaluation/blind-eval-tsingtao-resume-20261008/preparation.json'],
 'failurePolicy':'No automatic paid retry. Terminal failures retained, descendants without delivered parent blocked; independent chains proceed. Uncertain POST stops for read-only reconciliation. Input drift stops phase; all usage retained, unknown stays unknown.',
 'status':'approved_design_offline_verified_waiting_F1_and_explicit_paid_go_ahead','excluded':[{'id':'X2','status':'未执行','reason':'美的未入库；本轮不做'}]}
dump(here/'f1-config.json',config)
print('Wrote 11-task config; no runs or HTTP requests')

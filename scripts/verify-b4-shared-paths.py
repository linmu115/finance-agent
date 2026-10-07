"""Deterministic params/edits/read/binding exercise in both actual Docker profiles."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
folder=ROOT/'docs/evidence/a3-a5-b4-20261007'
service=FinanceService(ROOT/'data/evaluation/a3-a5-b4-20261007');project='b4-shared';service.create_project(project,'B4 shared deterministic paths')
code='''from decimal import Decimal
from analysis_report import save_table
AMOUNT=10
FACTOR=1
save_table('values',{'item':{},'value':{'unit':'元','currency':'CNY'}},[{'item':'total','value':str(Decimal(str(AMOUNT))*Decimal(str(FACTOR)))}])
'''
results=[]
def save():(folder/'b4-shared-paths.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
def run(profile,kind,**args):
    run_id=service.run_analysis(project,financial_tools=profile=='financial',**args)['data']['run_id']
    state=service.analysis_futures[run_id].result();item={'profile':profile,'kind':kind,'run_id':run_id,'state':state};results.append(item);save()
    assert state['status']=='succeeded',state
    return run_id,service.get_analysis_status(project,run_id)['data'],item
try:
    for profile in ('prepared','financial'):
        base,base_status,_=run(profile,'base',code=code)
        updated,status,item=run(profile,'params',source_run_id=base,params={'AMOUNT':{'*':'1.1'}},params_order=['AMOUNT'])
        context=status['scenario_context'];old=context['baseline']['tables']['values'];new=context['scenario']['tables']['values']
        template='基准 {{'+old+'.total.value}}；情景 {{'+new+'.total.value}}\n'+context['preferred_embedding']
        answer=service.render_answer(project,template,status['numeric_tables'])['data']['body']
        assert '基准 10.00 CNY 元；情景 11.00 CNY 元' in answer
        assert '差额（情景减基准）' in answer
        item.update(answer=answer,baseline_kept=True,comparison_embedded=True);save()
        repaired,status,item=run(profile,'edits',source_run_id=updated,edits=[{'before':'FACTOR=1','after':'FACTOR=2'}])
        answer=service.render_answer(project,'{{values.total.value}}\n{{table:values}}',status['numeric_tables'])['data']['body']
        assert '22.00 CNY 元' in answer and '| total | 22.00 |' in answer
        artifact=service.get_artifact(project,repaired,'values.csv',rows={'start':0,'end':1})['data']
        assert artifact['content'][0]['（CNY 元）']=='22.0',artifact
        item.update(answer=answer,artifact=artifact);save()
        print(profile,'params/edits/read/bind PASS',flush=True)
finally:service.analysis_pool.shutdown()

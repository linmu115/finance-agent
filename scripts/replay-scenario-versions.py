"""Deterministic Docker replay using the pre-held-out D2 snapshot only. No LLM."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.analysis_report import bind_text

def main():
    trial=ROOT/'data/evaluation/harness-v2-a2-20261007'
    assert (trial/'finance.sqlite').is_file(),'Requires the existing pre-held-out snapshot; never copy the active DB.'
    service=FinanceService(trial);project='03b52dde-19da-49c1-949a-ee6d93bf036b'
    source='18f59dcff3ce4da583c4344de2ecb8f8'
    evidence={'method':'Frozen D2 input snapshot, two successive params updates, Docker only, no LLM, no active/held-out reads.','cases':[]}
    target=ROOT/'docs/evidence/harness-v2-followup-20261007/scenario-replay.json'
    try:
        for params in ({'wacc0':{'+':.005},'fcf':{'*':.9}},{'wacc0':{'+':.001}}):
            result=service.run_analysis(project,source_run_id=source,params=params,financial_tools=False)['data']
            run=result['run_id'];state=service.analysis_futures[run].result();status=service.get_analysis_status(project,run)['data']
            item={'source_run_id':source,'run_id':run,'status':state['status'],'params':params,'state':state};evidence['cases'].append(item)
            target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
            assert state['status']=='succeeded',state
            context=status['scenario_context'];tables=status['numeric_tables'];name='forecast_and_dcf_inputs'
            baseline=tables[context['baseline']['tables'][name]];scenario=tables[context['scenario']['tables'][name]]
            old=next(r['value'] for r in baseline['rows'] if r['metric']=='Value/share')
            new=next(r['value'] for r in scenario['rows'] if r['metric']=='Value/share')
            rendered=bind_text(context['preferred_embedding'],tables)
            assert name not in tables
            assert all(not key.startswith(('基准_','情景_')) for key in context['scenario']['tables'])
            if len(evidence['cases'])==2:assert old==evidence['cases'][0]['scenario_price']
            item.update(baseline_price=old,scenario_price=new,comparison_rows=len(tables[context['preferred_table']]['rows']),embedded='差额（情景减基准）' in rendered,scenario_context=context)
            assert item['embedded']
            target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
            print(json.dumps({k:item[k] for k in ('run_id','status','baseline_price','scenario_price','comparison_rows','embedded')}),flush=True)
            source=run
    finally:service.analysis_pool.shutdown()

if __name__=='__main__':main()

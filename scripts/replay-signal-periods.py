"""Read-only acceptance of radar integration with N2's period algebra."""
import argparse
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('signals_replay',Path(__file__).with_name('replay-analyst-signals.py'))
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
from service.workpaper_analyst import AnalystData,locators


def main():
    p=argparse.ArgumentParser();p.add_argument('--old-copy',type=Path,required=True);p.add_argument('--current-copy',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();cases=[]
    for name,which,project,doc in shared.CASES:
        s=shared.legacy.FinanceService.__new__(shared.legacy.FinanceService)
        s.store=shared.legacy.ReadOnlyCopy(args.old_copy if which=='old' else args.current_copy)
        a=AnalystData(s,project,doc)
        values={metric:a.quarters(metric)[3] for metric in ('revenue','parent_profit','cfo')}
        checks=[]
        if a.ps[0].endswith('-FY'):
            for r in a.period_series()['reconciliations']:
                if r['period']!=a.ps[0][:4]+'-Q4':continue
                assert Decimal(r['residual']['value'])==0
                assert locators(r['derived']['quantity'])
                checks.append({'metric':r['metric'],'residual':r['residual']['value'],'disclosed':r['disclosed']['quantity']['value'],
                               'derived':r['derived']['quantity']['value'],'sources':locators(r['derived']['quantity'])})
            assert len(checks)==4
        else:assert all(q['value'] is None for q in values.values())
        cases.append({'company':name,'current_period':a.ps[0],'q4_values':values,'q4_reconciliations':checks})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'n2_dependency_commit':'d349e04','llm_calls':0,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps([{'company':x['company'],'q4_reconciliations':len(x['q4_reconciliations']),'q4_values':{k:v['value'] for k,v in x['q4_values'].items()}} for x in cases],ensure_ascii=False))


if __name__=='__main__':main()

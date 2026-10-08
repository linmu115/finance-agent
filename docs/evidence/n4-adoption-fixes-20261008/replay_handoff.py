"""Local deterministic replay of captured workpaper calls; zero model requests."""
import json,shutil,tempfile,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
rows=[]
with tempfile.TemporaryDirectory() as tmp:
    shutil.copy2(BASE/'seed/finance.sqlite',Path(tmp)/'finance.sqlite');s=FinanceService(tmp)
    for run in sorted((BASE/'runs').glob('Q*-financial')):
        audit=json.loads((run/'audit-summary.json').read_text(encoding='utf8'))
        requests=[c for c in audit['calls'] if c['name']=='financial_workpaper']
        observed=json.loads((run/'workpapers.json').read_text(encoding='utf8'))
        assert len(requests)==len(observed)
        for request in requests:
            expected=next(w for w in observed if w['toolCallId']==request['toolCallId'])
            args=dict(request['args'])
            if args.get('kind')!='expectations':args.pop('as_of',None);args.pop('metrics',None)
            actual=s.financial_workpaper(**args)
            if expected['status']!='ok':
                assert '当前口径主体为：[]' in expected['data']['error']
                assert '当前口径主体为：[]' not in actual['data'].get('error','')
                rows.append({'case':run.name,'kind':args['kind'],'status':actual['status'],'previous_status':expected['status'],'previous_error':expected['data']['error'],'resolved':actual['data'].get('period_roles'),'remaining_missing':actual['data'].get('error'),'registered_alias_fix':True})
                continue
            assert actual['status']=='ok',actual
            actual=actual['data'];old=expected['data']
            assert actual['period_roles']==old['period_roles']
            assert actual['numeric_tables'].keys()==old['numeric_tables'].keys(),(run.name,args['kind'],list(actual['numeric_tables']),list(old['numeric_tables']))
            for name,t in actual['numeric_tables'].items():
                assert t['rows']==old['numeric_tables'][name]['rows'],(run.name,args['kind'],name)
                assert t['columns']==old['numeric_tables'][name]['columns']
            assert actual['key_values']==old['key_values']
            rows.append({'case':run.name,'kind':args['kind'],'status':'ok','periods':args.get('periods'),'resolved':actual['period_roles'],'table_rows_units_and_handoff_equal':True})
(BASE/'replay-validation.json').write_text(json.dumps({'model_calls':0,'workpaper_calls':rows},ensure_ascii=False,indent=2),encoding='utf8')
print('Replayed',len(rows),'workpaper calls:',sum(r.get('table_rows_units_and_handoff_equal',False) for r in rows),'identical successes;',sum(r.get('registered_alias_fix',False) and r['status']=='ok' for r in rows),'previous alias failures now succeeded;',sum(r['status']!='ok' for r in rows),'remaining data limitations; zero model requests.')

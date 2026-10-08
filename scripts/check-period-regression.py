"""Compare deterministic periods on named, non-held-out local source copies."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import types

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service import cleaning_rules as current

p=argparse.ArgumentParser();p.add_argument('--annual',required=True);p.add_argument('--ruihe',required=True);p.add_argument('--carote',required=True);p.add_argument('--output',required=True)
a=p.parse_args()
previous=types.ModuleType('service.previous_rules');previous.__package__='service'
exec(subprocess.check_output(['git','show','1828c22:service/cleaning_rules.py']).decode('utf-8'),previous.__dict__)
results={}
for name in ('annual','ruihe','carote'):
    parsed=json.loads(Path(getattr(a,name)).read_text(encoding='utf-8'));same=[];changed=[]
    tables=[t for t in parsed['tables'] if name!='annual' or 100<=t['index']<=115]
    for table in tables:
        before={c['column']:c['period'] for c in previous.source_columns(table,parsed,previous.context(parsed,table))}
        after={c['column']:c['period'] for c in current.source_columns(table,parsed,current.context(parsed,table))}
        for column,period in before.items():
            item={'table':table['index'],'page':table['page'],'column':column,'before':period,'after':after.get(column)}
            (same if period==item['after'] else changed).append(item)
    if name in {'annual','ruihe'}:assert not changed,(name,changed)
    if name=='carote':
        # The formerly correct flow periods must remain H1. Changes are only
        # source-explicit June/December stock dates previously misread as FY/H1.
        assert all(c['after'] in {'2025-06-30','2024-12-31'} for c in changed),changed
        for index in (31,34,35,36,37,39,40,42):
            table=next(t for t in tables if t['index']==index)
            periods=[c['period'] for c in current.source_columns(table,parsed,current.context(parsed,table))]
            assert periods[:2]==['2025-06-30','2024-12-31'],(index,periods)
    results[name]={'tables_checked':len(tables),'source_pages':len({t['page'] for t in tables}),
                   'unchanged_known_columns':len(same),'changed_columns':changed,'unchanged_columns':same}
Path(a.output).write_text(json.dumps({'model_calls':0,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({name:{k:v for k,v in r.items() if k!='unchanged_columns'} for name,r in results.items()},ensure_ascii=False))

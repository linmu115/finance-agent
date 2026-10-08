"""Document exact alias scope and all changes in the fixed-copy rerun."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.standard_metrics import WORKPAPER_ALIASES,workpaper_concepts,ROWS

ap=argparse.ArgumentParser();ap.add_argument('--replay',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
def read(path):return json.loads(path.read_text('utf8'))
def save(name,x):(a.out/name).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
old={'__name__':'service.standard_metrics','__package__':'service'}
exec(subprocess.check_output(['git','show','85a2f07:service/standard_metrics.py'],cwd=ROOT).decode('utf8'),old)
expected={'net_profit_parent_ex_nonrecurring':'deducted_profit','net_assets_parent':'parent_equity','operating_cash_flow_net':'cfo',
          'net_cash_from_operating_activities':'cfo','cash_and_cash_equivalents_ending':'cash_end'}
assert ROWS==old['ROWS']
assert set(WORKPAPER_ALIASES)==set(old['WORKPAPER_ALIASES'])
added={m:c for c,ids in WORKPAPER_ALIASES.items() for m in set(ids)-set(old['WORKPAPER_ALIASES'][c])}
assert added==expected
assert all(set(ids)<=set(WORKPAPER_ALIASES[c]) for c,ids in old['WORKPAPER_ALIASES'].items())
summary={'baseline':'85a2f07','model_calls':0,'database_writes':0,'added_aliases':added,'canonical_labels_unchanged':True,
         'concept_count':len(WORKPAPER_ALIASES),'datasets':{},'row_changes':[]}
before=read(a.replay/'before-summary.json');after=read(a.replay/'after-summary.json')
assert before['facts_and_history_unchanged'] and after['facts_and_history_unchanged']
counts=[];evidence=[]
for name in ('yili','haier'):
    folder=a.replay/name
    summary['datasets'][name]={}
    for b,c in zip([x for x in before['workpapers'] if x['dataset']==name],[x for x in after['workpapers'] if x['dataset']==name]):
        assert b['kind']==c['kind'] and b['status']==c['status']=='ok'
        kind=c['kind'];bt=read(folder/('before-'+kind+'.json'))['data']['numeric_tables'];at=read(folder/('after-'+kind+'.json'))['data']['numeric_tables']
        assert set(bt)==set(at)
        for tab,t in bt.items():
            new=at[tab];assert len(t['rows'])==len(new['rows'])
            counts.append({'dataset':name,'kind':kind,'table':tab,'before':b['tables'][tab],'after':c['tables'][tab]})
            for x,y in zip(t['rows'],new['rows']):
                assert x['key']==y['key']
                for column,meta in t['columns'].items():
                    if meta.get('unit') or meta.get('per_cell_unit'):assert x.get(column)==y.get(column),(name,kind,tab,x['key'],column)
                if x!=y:summary['row_changes'].append({'dataset':name,'kind':kind,'table':tab,'row':x['key'],
                    'metric':x.get('metric'),'period':x.get('period'),
                    'changes':{k:{'before':x[k],'after':y[k]} for k in x if x[k]!=y[k]}})
        summary['datasets'][name][kind]={'status':'ok','tables':len(at),'row_counts_unchanged':True,'all_numeric_values_unchanged':True}
        if kind=='statement_analysis':
            save(name+'-deducted-profit.json',at['deducted_profit'])
            if name=='yili':assert all(Decimal(x['residual'])==0 and x['disclosed']==x['calculated'] for x in at['deducted_profit']['rows'])
            else:assert all(x['disclosed'] is None for x in at['deducted_profit']['rows'])
    facts=read(ROOT/'tmp/f14-replay-20261008'/name/'after-facts.json')
    for f in facts:
        if f['metric'] in expected:
            s=json.loads(f['source_json']);n=s['normalization']
            evidence.append({'dataset':name,'fact_id':f['fact_id'],'metric':f['metric'],'concept':workpaper_concepts(f['metric'])[0],
                 'value':f['value'],'period':f['period'],'scope':f['scope'],'table':s['table_id'],'cell':s['cell'],
                 'raw_row':s['text'],'label':n.get('label'),'dimensions':n.get('dimensions',{})})
summary['all_facts_and_history_unchanged']=True
summary['haier_known_limitation']='X7: disclosed deducted profit remains null because financial_item/version dimensions are excluded by existing selection. Calculated profit is kept separately, never adopted as disclosed.'
summary['haier_period_limitation']='Eight quarter/cumulative rows retain null amounts; basis changes to original after alias recognition. Five missing reasons now preserve conflicting fact/blank source-table candidates. No numeric value or count changes.'
save('summary.json',summary);save('alias-source-evidence.json',evidence);save('table-counts.json',counts)
md=['# 五类别名补充前后逐表对比','','每格为“行数 / 有值数值格数”。所有数值和行数不变；海尔期间表 8 行的版本/缺项说明变化另见 summary.json。','',
    '|材料|底稿|结果表|补充前|补充后|','|---|---|---|---:|---:|']
md += [f'|{x["dataset"]}|{x["kind"]}|{x["table"]}|{x["before"]["rows"]} / {x["before"]["numeric_cells"]}|{x["after"]["rows"]} / {x["after"]["numeric_cells"]}|' for x in counts]
(a.out/'table-counts.md').write_text('\n'.join(md)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'added_aliases':added,'datasets':summary['datasets'],'metadata_changed_rows':len(summary['row_changes']),'facts_and_history_unchanged':True},ensure_ascii=False))

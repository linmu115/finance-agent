"""Verify saved zero-model workpapers and source semantics on scoped copies."""
import argparse
import ast
from collections import Counter
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.standard_metrics import ROWS,WORKPAPER_ALIASES,STANDARD_METRICS

ap=argparse.ArgumentParser();ap.add_argument('--replay',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--review',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text('utf-8'))
def save(name,value):(args.out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
def assignment(text,key):
    return ast.literal_eval(next(n.value for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in n.targets)))
def old_file(name):return subprocess.check_output(['git','show','a13c1ee:service/'+name],cwd=ROOT).decode('utf-8')
assert ROWS==assignment(old_file('standard_metrics.py'),'ROWS')
old_aliases=assignment(old_file('financial_workpapers.py'),'ALIASES')
for concept,ids in old_aliases.items():assert set(ids)<=set(WORKPAPER_ALIASES[concept]),concept
summary={'baseline':'a13c1ee','model_calls':0,'production_writes':0,'canonical_labels_unchanged':len(ROWS),
 'all_previous_aliases_preserved':True,'canonical_ids':len(STANDARD_METRICS),'concepts':len(WORKPAPER_ALIASES),'datasets':{}}
counts=[];changes=[];numeric_changes=[]
for name in ('yili','haier'):
    folder=args.replay/name;before=read(folder/'before-workpapers.json');after=read(folder/'after-workpapers.json')
    info=read(folder/'reapply.json');manifest=read(folder/'manifest.json')
    assert info['repeat']['updated']==0 and info['history_exact'] and info['values_coordinates_entities_unchanged']
    changes.append({'dataset':name,**info})
    reports={}
    for b,a in zip(before,after):
        assert b['kind']==a['kind'] and b['status']==a['status']=='ok'
        kind=a['kind'];bt=read(folder/('before-'+kind+'.json'))['data']['numeric_tables'];at=read(folder/('after-'+kind+'.json'))['data']['numeric_tables'];reports[kind]=at
        for table in dict.fromkeys([*bt,*at]):
            counts.append({'dataset':name,'kind':kind,'table':table,'before':b['rows'].get(table,0),'after':a['rows'].get(table,0),
                           'numeric_before':b['numeric_cells'].get(table,0),'numeric_after':a['numeric_cells'].get(table,0)})
            if table not in bt or table not in at:continue
            left={r['key']:r for r in bt[table]['rows']};right={r['key']:r for r in at[table]['rows']}
            for key,old in left.items():
                if key not in right:continue
                for c,m in bt[table]['columns'].items():
                    if not (m.get('unit') or m.get('per_cell_unit')) or old.get(c) is None:continue
                    new=right[key].get(c)
                    assert new is not None,(name,kind,table,key,c,'lost value')
                    if D(old[c])!=D(new):numeric_changes.append({'dataset':name,'kind':kind,'table':table,'row':key,'column':c,'before':old[c],'after':new})
        if kind=='period_analysis':
            assert {k:t['rows'] for k,t in bt.items()}=={k:t['rows'] for k,t in at.items()},'period outputs changed'
    summary['datasets'][name]={'facts':manifest['facts'],'changed':info['changed_since_snapshot'],'unchanged':info['unchanged'],
       'history':len(info['changes']),'repeat_changes':info['repeat']['updated'],'kinds':[{k:r[k] for k in ('kind','status','seconds')} for r in after],
       'deducted_profit':reports['statement_analysis']['deducted_profit']['rows'],
       'remaining_statement_missing':reports['statement_analysis']['missing']['rows'],
       'remaining_signal_unknowns':[r for r in reports['anomaly_signals']['signals']['rows'] if r['value'] is None]}
    if name!='yili':continue
    facts={f['fact_id']:f for f in read(folder/'after-facts.json')};st=reports['statement_analysis'];missing=st['missing']['rows']
    fixed=('research','surcharges','finance_costs','associates','fair_value_gains','asset_disposal','nonoperating_income','nonoperating_expenses','minority_profit')
    false_missing=[r for r in read(folder/'before-statement_analysis.json')['data']['numeric_tables']['missing']['rows'] if r['metric'] in fixed]
    assert len(false_missing)==18 and not [r for r in missing if r['metric'] in fixed]
    verified=[]
    for gap in false_missing:
        tab='profit_attribution' if gap['metric']=='minority_profit' else 'income'
        key=gap['period'] if tab=='profit_attribution' else gap['metric'];column='minority' if tab=='profit_attribution' else gap['period']
        index=next(i for i,r in enumerate(st[tab]['rows']) if r['key']==key);row=st[tab]['rows'][index];q=st[tab]['evidence'][index][column]
        f=facts[q['source']['fact_id']]
        assert D(row[column])*1000000==D(q['value'])==D(f['value'])
        verified.append({'concept':gap['metric'],'period':gap['period'],'million':row[column],'fact_id':f['fact_id'],'metric':f['metric'],'source':q['source']['source_ref']})
    save('resolved-18.json',verified)
    adoption=[]
    for row,ev in zip(st['deducted_profit']['rows'],st['deducted_profit']['evidence']):
        assert all(row[k] is not None for k in ('nonrecurring','calculated','residual','share'))
        assert D(row['parent'])-D(row['nonrecurring'])==D(row['calculated'])==D(row['disclosed']) and D(row['residual'])==0
        q=ev['disclosed'];ref=q['source']['source_ref'];f=facts[q['source']['fact_id']]
        assert ref['table_id'].endswith(':t8') and f['scope']=='consolidated_CAS'
        assert D(row['disclosed'])*1000000==D(f['value']) and not q['source'].get('formula')
        assert ev['nonrecurring']['source']['table_id'].endswith(':t12')
        adoption.append({'period':row['key'],'fact_id':f['fact_id'],'cell':ref['cell'],'value_yuan':f['value'],'source':ref})
    save('disclosed-deducted-adoption.json',adoption)
    signals=[r for r in reports['anomaly_signals']['signals']['rows'] if 'nonrecurring' in r['key']]
    assert len(signals)==3 and all(r['value'] is not None and not r['missing'] for r in signals)
    with localcontext() as ctx:
        ctx.prec=40
        assert abs(D(signals[2]['value'])-(D(signals[0]['value'])-D(signals[1]['value'])))<D('1e-35')
    save('nonrecurring-signals.json',signals)
    # Recheck the same fifty source-reviewed gold points; no claim of fifty
    # newly selected/visually reviewed samples is made here.
    db=sqlite3.connect((folder/'app-data/finance.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    tables={r[0]:json.loads(r[1]) for r in db.execute('SELECT table_id,rows_json FROM source_tables WHERE document_id=?',(manifest['document'],))};db.close()
    review=[]
    for point in read(args.review):
        valid=[]
        for prior in point['matches']:
            current=facts[prior['fact_id']];src=json.loads(current['source_json'])
            assert all(current[k]==prior[k] for k in ('metric','period','scope','currency','company','value'))
            assert src==prior['source']
            assert tables[src['table_id']][src['row']-1][src['column']-1]==current['raw_value']
            valid.append({'fact_id':prior['fact_id'],'table':src['table_id'],'cell':src['cell']})
        assert valid and point['status']=='passed' and point['pdf_literal_verified']
        review.append({k:point[k] for k in ('category','page','label','value','period','scope','company','currency')}|{'matches':valid,'status':'passed'})
    assert len(review)==50;save('source-review-50.json',review)
    summary['datasets'][name].update(resolved_false_missing=18,source_review_passed=50,nonrecurring_signals=signals)
save('reapplication.json',changes);save('table-counts.json',counts);save('existing-numeric-changes.json',numeric_changes)
summary['existing_numeric_changes']=len(numeric_changes);summary['lost_existing_numeric_values']=0
assert all(x['kind']=='variance_attribution' and x['table']=='profit_bridge' and
           (x['column']=='running' or x['column']=='contribution' and x['row'].endswith('_residual')) for x in numeric_changes)
summary['existing_numeric_changes_reason']='Previously missing contributions now enter the running profit bridge and reduce its residuals; every other pre-existing numeric value is unchanged.'
save('summary.json',summary)
md=['# F1.4 逐表前后对比','', '同一复制快照：a13c1ee 与本分支；每格为“行数；有值数值格数”。不存在的表记 0，不把空格计为零。','',
 '|材料|底稿|结果表|改前|改后|','|---|---|---|---:|---:|']
md += [f'|{x["dataset"]}|{x["kind"]}|{x["table"]}|{x["before"]}；{x["numeric_before"]}|{x["after"]}；{x["numeric_after"]}|' for x in counts]
(args.out/'table-counts.md').write_text('\n'.join(md)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in summary.items() if k!='datasets'},ensure_ascii=False))
print('Existing numeric changes by dataset:',dict(Counter(x['dataset'] for x in numeric_changes)))

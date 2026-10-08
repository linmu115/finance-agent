"""Compare trusted SDK versions on scoped copied mappings; never execute model code."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service import cleaning_sdk
from service.semantic import materialize

DOCUMENTS={
    'yili':('374beac2-a970-4972-b210-e91018bbd6e6','d84573bf6b584e7e874faa4c6adf454a'),
    'haier':('d324c744-4113-4213-aa22-af3bb91a3c84','e7b0d9679ddc4b739f8f35ecb6dc6227'),
}


def scoped_copy(source,target,project,did):
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(target) as dst:
        src.execute('BEGIN')
        for table,key,value in [('facts','document_id',did),('fact_history','document_id',did),
                                ('source_tables','document_id',did),('normalization_batches','document_id',did)]:
            ddl=src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
            dst.execute(ddl)
            rows=src.execute(f'SELECT * FROM {table} WHERE {key}=?',(value,)).fetchall()
            if rows:dst.executemany(f'INSERT INTO {table} VALUES({",".join("?" for _ in rows[0])})',rows)
        assert {r[0] for r in dst.execute('SELECT DISTINCT project_id FROM facts')}<={project}


def sdk_mapping(module,table,extractions):
    schema=copy.deepcopy(next(e['attributes'] for e in extractions if e['class']=='table_schema'))
    rows=[{'row':int(re.search(r':R(\d+)\]\]',e['text'])[1]),'attributes':copy.deepcopy(e['attributes'])}
          for e in extractions if e['class']=='financial_row']
    c=module.Cleaner.__new__(module.Cleaner)
    c.tables={table['index']:table};c.results={};c.source={'company':schema.get('company')}
    if schema.get('statement')=='nonfinancial':return None
    # Rebuild the submitted meanings as data, with exact source-label keys where
    # unambiguous. Repeated labels keep their original per-row overrides.
    label_column=int(schema.get('label_column',1))
    labels=[str(table['rows'][r['row']-1][label_column-1]).strip() for r in rows]
    metrics={label:r['attributes'] for label,r in zip(labels,rows) if labels.count(label)==1}
    overrides={r['row']:r['attributes'] for label,r in zip(labels,rows) if labels.count(label)>1}
    columns=json.loads(schema.pop('columns_json'))
    skips={r['row']:r['reason'] for r in json.loads(schema.pop('skipped_rows_json','[]'))}
    skip_cols={r['column']:r['reason'] for r in json.loads(schema.pop('skipped_columns_json','[]'))}
    c.map_table(table['index'],columns,metrics=metrics,row_overrides=overrides,
                skip_rows=skips,skip_columns=skip_cols,**schema)
    return c.results[table['index']]


def to_extractions(mapping):
    i=mapping['index'];marker=f'[[T{i}]]'
    result=[{'class':'table_schema','text':marker,'span':[0,len(marker)],'attributes':mapping['schema']}]
    for row in mapping['rows']:
        marker=f'[[T{i}:R{row["row"]}]]'
        result.append({'class':'financial_row','text':marker,'span':[0,len(marker)],'attributes':row['attributes']})
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--baseline',default='d7e40f9');ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    oldfile=args.out/'baseline-sdk.py'
    oldfile.write_bytes(subprocess.check_output(['git','show',args.baseline+':service/cleaning_sdk.py'],cwd=ROOT))
    spec=importlib.util.spec_from_file_location('baseline_sdk',oldfile)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    reports={}
    for name,(project,did) in DOCUMENTS.items():
        path=args.out/(name+'.sqlite');scoped_copy(args.source,path,project,did)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        unchanged={table:[tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                   for table in ('facts','fact_history','normalization_batches')}
        tables={int(r['table_id'].rsplit(':t',1)[1]):{'index':int(r['table_id'].rsplit(':t',1)[1]),
                 'page':r['page'],'rows':json.loads(r['rows_json'])} for r in db.execute('SELECT * FROM source_tables')}
        compared=[];nonfinancial=[]
        for batch in db.execute('SELECT result_json FROM normalization_batches'):
            b=json.loads(batch[0]);idx=b.get('script_table')
            if idx is None:raise AssertionError('non-script batch in requested script-ingestion snapshot')
            table=tables[idx];old=sdk_mapping(baseline,table,b['extractions']);new=sdk_mapping(cleaning_sdk,table,b['extractions'])
            assert old==new,('sdk_output_changed',name,idx)
            if old is None:nonfinancial.append(idx);continue
            assert not new.get('mapping_error'),(name,idx,new.get('mapping_error'))
            context=[{'table':table,'rows':list(range(1,len(table['rows'])+1))}]
            oldfacts,oldissues=materialize(to_extractions(old),context,did,b['model'])
            newfacts,newissues=materialize(to_extractions(new),context,did,b['model'])
            assert (oldfacts,oldissues)==(newfacts,newissues),(name,idx)
            compared.append({'table':idx,'facts':len(newfacts),'issues':len(newissues)})
        for table,rows in unchanged.items():assert rows==[tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
        reports[name]={'copied_facts':len(unchanged['facts']),'history_records':len(unchanged['fact_history']),
                       'compared_tables':len(compared),'compared_materialized_facts':sum(r['facts'] for r in compared),
                       'nonfinancial_tables':nonfinancial,'changed_sdk_outputs':0,'changed_materialized_facts':0,
                       'changed_stored_facts_or_history':0,'tables':compared}
        db.close()
    report={'model_calls':0,'baseline':args.baseline,'method':'rebuild submitted mapping data; no generated Python executed',
            'documents':reports}
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({n:{k:v for k,v in r.items() if k!='tables'} for n,r in reports.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

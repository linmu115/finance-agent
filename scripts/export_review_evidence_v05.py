"""Read-only accepted review caches and result hashes. No production imports."""
import argparse,hashlib,json,sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--temporal-review');a=p.parse_args()
database=Path(__file__).resolve().parents[1]/'data/finance.sqlite'
def packed(row):
    value=json.loads(row[0]) if row else None
    return {'payload':value,'computed_result_hash':hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest() if value is not None else None}
with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
    db.execute('BEGIN')
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    catalog=[]
    if 'metric_directory_reviews' in tables:
        for row in db.execute('SELECT result_json FROM metric_directory_reviews WHERE project_id=?',(a.project,)):catalog.append(packed(row))
    temporal=None
    if a.temporal_review:
        row=db.execute('SELECT report_json FROM temporal_project_reviews WHERE project_id=? AND review_id=?',(a.project,a.temporal_review)).fetchone()
        if row:
            report=json.loads(row[0]);chunks=[]
            for phase,field in [('profiles','profile_audits'),('corrections','correction_audits')]:
                for audit in report.get(field,[]):chunks.append({'phase':phase,'audit':audit,**packed(db.execute('SELECT result_json FROM temporal_review_cache WHERE cache_key=?',(audit['cache_key'],)).fetchone())})
            temporal={'review':report,'chunks':chunks}
    definitions={'reviews':[],'caches':{},'histories':[]}
    if 'fact_definition_reviews' in tables:
        definitions['reviews']=[json.loads(r[0]) for r in db.execute('SELECT report_json FROM fact_definition_reviews WHERE project_id=? ORDER BY created_at',(a.project,))]
        keys={audit['cache_key'] for report in definitions['reviews'] for audit in report.get('audits',[])}
        # Discover committed partial batches through fact references too. The
        # verifier still separately requires their own report registration.
        for row in db.execute('SELECT source_json FROM facts WHERE project_id=?',(a.project,)):
            review=json.loads(row[0]).get('normalization',{}).get('definition_review')
            if review:keys.add(review['cache_key'])
        for key in keys:definitions['caches'][key]=packed(db.execute('SELECT result_json FROM fact_definition_cache WHERE cache_key=?',(key,)).fetchone())
        for report in definitions['reviews']:
            for row in db.execute('SELECT fact_json FROM fact_history WHERE project_id=? AND processing_id=?',(a.project,report['processing_id'])):definitions['histories'].append({'review_id':report['review_id'],'fact':json.loads(row[0])})
    normalization=[];processing_owners={}
    for row in db.execute('SELECT document_id,batch_key,processing_id,result_json FROM normalization_batches WHERE document_id IN (SELECT document_id FROM documents WHERE project_id=?)',(a.project,)):
        detail=json.loads(row[3]);normalization.append({'document_id':row[0],'batch_key':row[1],'processing_id':row[2],'result':detail})
        origin=detail.get('extraction_processing_id') or row[2]
        owner=db.execute('SELECT owner_run_id FROM processing_runs WHERE processing_id=?',(origin,)).fetchone()
        if owner:processing_owners[origin]=owner[0]
print(json.dumps({'source':'host_sqlite_readonly','catalog':catalog,'temporal':temporal,'definitions':definitions,'normalization':normalization,'processing_owners':processing_owners},ensure_ascii=False))

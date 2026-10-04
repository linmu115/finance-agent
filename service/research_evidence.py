"""Deterministic dependency fingerprints from one SQLite read snapshot."""
import hashlib
import json

def document_version(store, project_id, document_id):
    store.project(project_id)
    with store.connect() as db:
        db.execute('BEGIN')
        row=db.execute('SELECT * FROM documents WHERE project_id=? AND document_id=?',(project_id,document_id)).fetchone()
        if row is None:
            raise ValueError('document_not_found')
        document=dict(row)
        rows=[dict(r) for r in db.execute('SELECT fact_id,company,metric,year,period,scope,currency,value,raw_value,raw_unit,quality,source_json FROM facts WHERE project_id=? AND document_id=? ORDER BY fact_id',(project_id,document_id))]
        encoded=json.dumps({'sha256':document['sha256'],'facts':rows},ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return {'document_id':document_id,'original_sha256':document['sha256'],'fact_count':len(rows),'version':hashlib.sha256(encoded.encode('utf-8')).hexdigest()}

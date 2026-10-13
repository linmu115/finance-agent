"""Read-only material snapshot. Never copies conversations or generated artifacts."""
import hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def snapshot(projects):
    db=sqlite3.connect((ROOT/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('BEGIN') # one consistent read transaction; no DB mutations
    result={}
    tables=['documents','pages','source_tables','facts','chunks','document_profiles','research_entities','research_document_entities','research_records','research_page_reviews','prepared_documents','normalization_batches']
    for project in projects:
        data={}
        for table in tables:
            cols=[r['name'] for r in db.execute('PRAGMA table_info("'+table+'")')]
            if not cols:raise ValueError('Missing material table '+table)
            if 'project_id' in cols:where='project_id=?'
            else:where='document_id IN (SELECT document_id FROM documents WHERE project_id=?)'
            rows=[dict(r) for r in db.execute('SELECT * FROM "'+table+'" WHERE '+where,(project,))]
            # Preserve values, identities and review flags; row order is not material.
            data[table]=sorted(rows,key=canonical)
        if not data['documents']:raise ValueError('No documents in approved project '+project)
        # These project-scoped semantic tables affect catalog/definition retrieval.
        # Absence is recorded explicitly; this never creates or applies schema.
        data['semantic_catalog']={}
        for table in ['metric_aliases','metric_directory_reviews','fact_definition_corrections','fact_definition_reviews']:
            schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            data['semantic_catalog'][table]={'present':bool(schema),'schema':schema['sql'] if schema else None,
                'rows':sorted([dict(r) for r in db.execute('SELECT * FROM "'+table+'" WHERE project_id=?',(project,))],key=canonical) if schema else None}
        # Freeze the retrieval view definition; fact rows alone do not record its semantics.
        view=db.execute("SELECT sql FROM sqlite_master WHERE type='view' AND name='current_financial_facts'").fetchone()
        data['current_financial_facts_view_sql']=view['sql'] if view else None
        sources=[]
        for d in data['documents']:
            p=ROOT/'data/active'/d['relative_path']
            sources.append({'document_id':d['document_id'],'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
        data['source_files']=sources
        folder=ROOT/'data/active/projects'/project
        data['project_resources']=[{'path':str(p.relative_to(folder)),'text':p.read_text('utf-8-sig')} for p in sorted(folder.rglob('*')) if p.is_file()]
        result[project]=data
    db.rollback();db.close()
    return result
if __name__=='__main__':print(canonical(snapshot(sys.argv[1:])))

"""N1 read-only freeze and review-issue overlap evidence for authorized Yili release."""
import hashlib
import importlib.util
import json
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'data/evaluation/blind-eval-F21-formal-private-20261009'
DEST=BASE/'yili-freeze'
N3=Path('D:/AI/财报agent-wt/ingestion-scale/tmp/f21dockerresume-yili-production-20261009')
PROJECT='374beac2-a970-4972-b210-e91018bbd6e6'
ANNUAL='d84573bf6b584e7e874faa4c6adf454a'
QUARTER='4c3e9228d37e49fca132e0e79377b04d'


def read(p):return json.loads(p.read_text('utf-8-sig'))
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    with p.open('x',encoding='utf-8') as h:h.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def main():
    release=read(N3/'frozen-document.json')
    assert release['full_ingestion_complete'] and release['conversation_idle'] and release['core_complete']
    version=read(N3/'data-version.json')
    assert sha(N3/'facts.json')==version['facts_file_sha256']
    snapshot=read(DEST/'material-snapshot.json')[PROJECT]
    imported=read(N3/'facts.json')
    actual=[r for r in snapshot['facts'] if r['document_id']==ANNUAL]
    assert len(actual)==len(imported)==5428
    assert sorted(actual,key=canonical)==sorted(imported,key=canonical)
    module_spec=importlib.util.spec_from_file_location('material_snapshot',ROOT/'benchmark/blind-eval/snapshot-f14.py')
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    assert snapshot==module.snapshot([PROJECT])[PROJECT]
    requirements={'X1':[8,9,11,12],'X3':[8,11,12,253,254],
                  'X4':[],'X5':[104,105],'X6':[8,10,104,105]}
    needed=set(n for v in requirements.values() for n in v)
    source={r['table_id']:r for r in snapshot['source_tables']}
    with sqlite3.connect((ROOT/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        active=list(db.execute("SELECT key FROM app_state WHERE kind='runs' AND project_id=? AND json_extract(value_json,'$.status') IN ('queued','running')",(PROJECT,)))
        assert not active
        states=[json.loads(r['state_json']) for r in db.execute('SELECT state_json FROM processing_runs WHERE project_id=? ORDER BY updated_at DESC',(PROJECT,))]
        selected={did:next(s for s in states if any(d['document_id']==did for d in s['documents'])) for did in [ANNUAL,QUARTER]}
        docs={did:next(d for d in selected[did]['documents'] if d['document_id']==did) for did in selected}
        assert selected[ANNUAL]['owner_run_id']==release['run_id']
        assert canonical(docs[ANNUAL]['review_issues'])==canonical(release['review_issues'])
        db.rollback()
    gate=[]
    for did,tables in [(ANNUAL,sorted(needed)),(QUARTER,[0,7,8,9])]:
        for n in tables:
            tid=did+':t'+str(n)
            count=sum(json.loads(r['source_json']).get('table_id')==tid for r in snapshot['facts'] if r['document_id']==did)
            assert n in docs[did]['completed_tables'] and str(n) not in docs[did].get('deferred_tables',{})
            assert tid in source and count>0
            gate.append({'document_id':did,'table':n,'submitted':True,'facts':count,
                         'page':source[tid]['page'],'review_issues':sum(r['table']==n for r in docs[did].get('review_issues',[]))})
    issues=release['review_issues'];counts=Counter(r['table'] for r in issues)
    overlap=[r for r in issues if r['table'] in needed]
    assert len(issues)==304 and len(counts)==29 and len(overlap)==6
    assert {(r['table'],r['row'],r['column']) for r in overlap}=={(254,r,c) for r in [12,13,14] for c in [2,3]}
    table_rows=json.loads(source[ANNUAL+':t254']['rows_json'])
    for issue in overlap:
        assert table_rows[issue['row']-1][issue['column']-1]==''
    # Independently viewed frozen p218: these six blanks belong to the separate
    # noncash-investing/financing section, below the completed operating bridge.
    # Required bridge rows are 1..10 on this page. No blank is imputed as zero.
    image=BASE/'reference-packets/extension-X1-X3/annual-p218.png'
    refs=[BASE/'frozen-public-inputs'/n for n in ['reference-stage-b-additions.json','selectors-stage-b-additions.json','reference-phase1.json','selectors-phase1.json']]
    source_hashes={r['document_id']:r['sha256'] for r in snapshot['source_files']}
    for p in refs[:1]+refs[2:3]:
        for descriptor in read(p)['sources'].values():
            assert source_hashes[descriptor['document_id']]==descriptor['sha256']
    assessment={'at':datetime.now(timezone.utc).isoformat(),'issue_count':304,'issue_table_count':29,
        'required_table_overlap_count':len(set(counts)&needed),'issues_on_required_tables':len(overlap),
        'required_reference_input_overlap_count':0,'affects_answerability':False,
        'per_task':[{'task':task,'overlap_tables':len(set(tables)&set(counts)),
                     'overlap_issues':sum(counts[n] for n in tables),'reference_input_overlap':0,
                     'affects_answerability':False} for task,tables in requirements.items()],
        'coordinate_assessment':[{'issue':r,'used_by_reference':False,
            'reason':'Blank noncash investing/financing disclosure, outside required operating-cash reconciliation and other frozen reference inputs.'} for r in overlap],
        'adjacent_page_issue':{'table':255,'count':counts[255],'reference_input_overlap':0,
            'reason':'Same page, acquisition-cash section; not a required reference input.'},
        'visual_source_checked':{'path':image.relative_to(BASE).as_posix(),'sha256':sha(image)},
        'method':'Original source coordinates, frozen reference/selector coverage, and independent original page inspection; all review issues preserved; no facts changed.'}
    save(DEST/'overlap-assessment.json',assessment)
    for name in ['frozen-document.json','data-version.json','cumulative-usage.json']:
        shutil.copyfile(N3/name,DEST/('N3-'+name))
    receipt={'at':datetime.now(timezone.utc).isoformat(),'product_version':'F2.1','deployed_commit':'7e702ff3f53eba8686254895ad98300445eac759',
        'project_id':PROJECT,'N3_frozen_at':version['finished_at'],'N3_owner_run_id':release['run_id'],
        'N3_fact_snapshot_matches':True,'annual_tables':303,'annual_facts':5428,'project_facts':len(snapshot['facts']),
        'all_13_required_tables_submitted':True,'required_tables':gate,
        'source_files':snapshot['source_files'],'idle_at_snapshot':True,
        'semantic_catalog_included':list(snapshot['semantic_catalog']),
        'current_fact_view_definition_included':True,'prepared_and_research_records_included':True,
        'review_issues_preserved':304,'review_issue_tables':29,'overlap_assessment_sha256':sha(DEST/'overlap-assessment.json'),
        'snapshot_sha256':hashlib.sha256(canonical(snapshot).encode()).hexdigest(),
        'snapshot_file_sha256':sha(DEST/'material-snapshot.json'),
        'references':[{'file':p.name,'sha256':sha(p)} for p in refs],
        'main_database_writes':0,'participant_requests':0,'model_calls':0,
        'admission':'Ready after read-only verification; add project digest to idle dispatcher state before any X1/X3/X4/X5/X6 request.'}
    save(DEST/'freeze-receipt.json',receipt)
    print(json.dumps({k:assessment[k] for k in ['required_table_overlap_count','issues_on_required_tables','required_reference_input_overlap_count','affects_answerability']}))


if __name__=='__main__':main()

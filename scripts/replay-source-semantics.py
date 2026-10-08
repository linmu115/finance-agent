"""Reapply the six reviewed defects on a scoped, isolated snapshot; zero models."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.accounting_basis import identify, reapply_document_facts
from service.store import dumps


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--snapshot',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('scoped_copy',ROOT/'scripts/replay-table-deferral.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    start=json.loads((args.snapshot/'start.json').read_text('utf-8'))
    project,did=start['project_id'],start['document_id']
    s=helper.copy_document(args.source,args.out,project,did)
    s._runner=lambda:(_ for _ in ()).throw(AssertionError('model_or_sandbox_forbidden'))
    try:
        baseline=json.loads((args.snapshot/'facts.json').read_text('utf-8'))
        # Only the isolated database is changed. Freeze exactly the reviewed
        # facts rather than mixing in later live ingestion results.
        with s.store.connect(write=True) as db:
            db.execute('DELETE FROM facts WHERE project_id=? AND document_id=?',(project,did))
            for old in baseline:
                names=list(old)
                db.execute(f'INSERT INTO facts ({",".join(names)}) VALUES ({",".join("?" for _ in names)})',list(old.values()))
        _,parsed=s._clean_source(project,did)
        result=reapply_document_facts(s,project,did,parsed,identify(parsed),'scope-period-replay')
        again=reapply_document_facts(s,project,did,parsed,identify(parsed),'repeat')
        assert again['updated']==0,again
        with s.store.connect() as db:
            after={r['fact_id']:dict(r) for r in db.execute('SELECT * FROM facts WHERE project_id=? AND document_id=?',(project,did))}
            history=[json.loads(r[0]) for r in db.execute("SELECT fact_json FROM fact_history WHERE processing_id='scope-period-replay'")]
        before={r['fact_id']:r for r in baseline}
        assert before.keys()==after.keys()
        changed=[]
        for fid,old in before.items():
            new=after[fid]
            assert all(old[k]==new[k] for k in ('company','metric','currency','value','raw_value','raw_unit','priority','quality'))
            a,b=json.loads(old['source_json']),json.loads(new['source_json'])
            assert {k:v for k,v in a.items() if k!='normalization'}=={k:v for k,v in b.items() if k!='normalization'}
            if old!=new:
                allowed={'period_start','period_end','source_semantics','document_semantics_revision'}
                am,bm=a['normalization'],b['normalization']
                assert {k:v for k,v in am.items() if k not in allowed}=={k:v for k,v in bm.items() if k not in allowed},(fid,am,bm)
                changed.append({'fact_id':fid,'table':a['table_id'],'row':a['row'],'column':a['column'],'value':new['value'],
                                'before':{k:old[k] for k in ('scope','period')},'after':{k:new[k] for k in ('scope','period')},
                                'evidence':bm.get('source_semantics')})
        assert len(changed)==result['updated']==len(history)
        assert all(h==before[h['fact_id']] for h in history)
        reviews=json.loads((args.snapshot/'source-review-results.json').read_text('utf-8'))
        fixed=[]
        for review in reviews:
            if review['status']!='semantic_mismatch':continue
            matches=[after[c['fact_id']] for c in review['candidates'] if c['fact_id'] in after]
            assert any(all(f[k]==review[k] for k in ('period','scope','value','currency','company')) for f in matches),review
            fixed.append({k:review[k] for k in ('category','page','label','period','value','scope')})
        assert len(fixed)==6
        report={'model_requests':0,'facts':len(before),'reapplied':result,'repeat':again,'source_review_fixed':fixed,
                'original_passed_preserved':sum(r['status']=='passed' and any(all(after[fid][k]==r[k] for k in ('period','scope','currency','company','value')) for fid in r['matched_fact_ids']) for r in reviews),
                'remaining_missing':sum(r['status']=='missing' for r in reviews),'unchanged_records':len(before)-len(changed),
                'changed_by_table':dict(Counter(c['table'] for c in changed)),'changes':changed,
                'values_coordinates_entities_unchanged':True,'complete_old_records_preserved':True}
        assert report['original_passed_preserved']==40
        (args.out/'report.json').write_text(dumps(report),'utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('changes','source_review_fixed')},ensure_ascii=False,indent=2))
    finally:helper.shutdown(s)


if __name__=='__main__':main()

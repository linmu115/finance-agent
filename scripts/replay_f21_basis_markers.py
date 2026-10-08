"""Full basis-workpaper replay for the three authorized development reports.

Supply a copied SQLite database. No service, model call, source write, or
held-out document discovery. Before/after use identical inputs and host code.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.replay_v3_workpapers import DOCS,service_at,write
from service import workpaper_basis as current


def indexed(rows):
    counts=Counter();result={}
    for row in rows:
        key=(row['source']['page'],row['kind'],row['source']['match'])
        counts[key]+=1
        result[(*key,counts[key])]=row
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--snapshot',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--baseline',default='14b9bde')
    args=ap.parse_args()
    before=types.ModuleType('service._basis_before');before.__package__='service'
    code=subprocess.check_output(['git','show',args.baseline+':service/workpaper_basis.py'],cwd=ROOT).decode('utf-8')
    exec(compile(code,'baseline:service/workpaper_basis.py','exec'),before.__dict__)
    summary=[];audit=[]
    service=service_at(args.snapshot,args.snapshot.parent/'deliveries')
    for name in ('yili','haier','carote'):
        project,did=DOCS[name]
        with service.store.connect() as db:
            pages=dict(db.execute('SELECT page,text FROM pages WHERE document_id=? ORDER BY page',(did,)))
            original_name=db.execute('SELECT original_name FROM documents WHERE document_id=?',(did,)).fetchone()[0]
        results={};reports={}
        for version,module in (('before',before),('after',current)):
            report,_=module.basis_changes(service,project,document_id=did)
            reports[version]=report
            rows=[{**r,'source':json.loads(r['source'])} for r in report['tables']['markers']['rows']]
            results[version]=rows
            write(args.out/(name+'-'+version+'.json'),rows)
        # The fix must not alter the monetary workpaper or the raw input pages.
        unchanged=[key for key in reports['before']['tables'] if key not in ('markers','summary')]
        assert all(reports['before']['tables'][key]==reports['after']['tables'][key] for key in unchanged)
        old,new=indexed(results['before']),indexed(results['after'])
        assert current.scan_basis_markers(pages,did)==[
            {k:v for k,v in r.items() if k!='key'} for r in results['after']]
        transitions=Counter()
        for key,row in new.items():
            prior=old.get(key);old_status=prior['status'] if prior else 'new_marker'
            transitions[(old_status,row['status'])]+=1
            if row['status'] in ('change_disclosed','restatement_disclosed'):
                audit.append({'company':name,'page':row['source']['page'],'kind':row['kind'],
                    'before':old_status,'after':row['status'],'quote':row['quote'],'reason':row['reason'],
                    'completion_evidence':current._completion_evidence(row['quote']),
                    'newly_disclosed':old_status not in ('change_disclosed','restatement_disclosed')})
        summary.append({'company':name,'document_id':did,'original_name':original_name,'pages':len(pages),
            'before':dict(Counter(r['status'] for r in results['before'])),
            'after':dict(Counter(r['status'] for r in results['after'])),
            'before_kinds':dict(Counter(r['kind'] for r in results['before'])),
            'after_kinds':dict(Counter(r['kind'] for r in results['after'])),
            'transitions':[{'before':a,'after':b,'count':n} for (a,b),n in sorted(transitions.items())],
            'removed_marker_count':len(old.keys()-new.keys()),'unchanged_tables':unchanged,
            'restatement_detected_before':reports['before']['tables']['summary']['rows'][0]['restatement_detected'],
            'restatement_detected_after':reports['after']['tables']['summary']['rows'][0]['restatement_detected']})
        print(name,summary[-1]['before'],'->',summary[-1]['after'],flush=True)
    write(args.out/'summary.json',{'baseline':args.baseline,'reports':summary,'disclosed_audit':audit,
        'final_scanner_full_workpaper_rows_equal':True})


if __name__=='__main__':main()

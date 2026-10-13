"""Seal terminal participant evidence before releasing independent judge packets."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from blind import read, output

p=argparse.ArgumentParser();p.add_argument('study');a=p.parse_args()
study=output(a.study);state=read(study/'experiment.json')
assert len(state['runs'])==len(state['plannedOrder'])
assert all(r['status'] in ['completed','failed','cancelled','blocked_dependency'] for r in state['runs'])
paths={study/'experiment.json', study/'authorization.json', study/'deployment-receipt.json'}
paths.update(study.glob('materials-*.json'))
for folder in ['effective-config','judge-reference']:
    paths.update(p for p in (study/folder).rglob('*') if p.is_file())
for run in state['runs']:
    if run['status']=='blocked_dependency':
        continue
    for suffix in ['run.json','conversation.json','audit.jsonl','answer.md','deliverables.json','analysis-only-receipt.json']:
        file=study/(run['label']+'-'+suffix)
        assert file.is_file(),file
        paths.add(file)
    paths.update(p for p in (study/(run['label']+'-artifacts')).rglob('*') if p.is_file())
rows=[]
for file in sorted(paths):
    raw=file.read_bytes()
    rows.append({'path':file.relative_to(study).as_posix(),'bytes':len(raw),
                 'sha256':hashlib.sha256(raw).hexdigest()})
record={'sealed_at':datetime.now(timezone.utc).isoformat(),
        'purpose':'Original participant responses, all delivered versions, audits, frozen input receipts and judge reference before scoring',
        'files':rows,'files_count':len(rows),'answers_or_gold_rewritten':False}
with (study/'participant-raw-seal.json').open('x',encoding='utf-8') as f:
    json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for r in rows)}))

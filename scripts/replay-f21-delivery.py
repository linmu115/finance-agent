"""Offline full-text replay of prior deliveries selected before running the lint."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.delivery_text import direction_issues, xlsx_direction_issues

p=argparse.ArgumentParser();p.add_argument('evaluation_root',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
batch=args.evaluation_root/'blind-eval-F14-B-review-corrected-20261008'/'round1'
reviews=json.loads((batch/'review.json').read_text('utf8'))['reviews']
cases=[r['case_id'] for r in reviews if not r.get('material_defects')]
records=[];seen=set()
for case in cases:
    folder=batch/case
    files=['answer.md',*[r['file'] for r in json.loads((folder/'files.json').read_text('utf8')) if r.get('role')=='delivered_attachment']]
    for name in files:
        path=folder/name
        if path.suffix.lower() not in ('.md','.csv','.xlsx'):continue
        content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
        if digest in seen:continue
        seen.add(digest)
        source=str(path.relative_to(args.evaluation_root)).replace('\\','/')
        issues=xlsx_direction_issues(path,source) if path.suffix.lower()=='.xlsx' else direction_issues(content.decode('utf-8-sig'),source,csv_text=path.suffix.lower()=='.csv')
        records.append({'case':case,'source':source,'sha256':digest,'bytes':len(content),'issues':issues})
errors=[i for r in records for i in r['issues'] if i.get('severity')!='notice']
notices=[i for r in records for i in r['issues'] if i.get('severity')=='notice']
result={'selection':'All round1 cases with no material_defects in prior F14-B corrected review; all delivered MD/CSV/XLSX and final answers; exact-content deduplication. Selected before lint, no removal of flagged files.',
        'cases':cases,'unique_files':len(records),'bytes':sum(r['bytes'] for r in records),
        'flagged_files':sum(any(i.get('severity')!='notice' for i in r['issues']) for r in records),
        'error_count':len(errors),'notice_count':len(notices),'records':records}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False))
print(json.dumps(errors+notices,ensure_ascii=False))

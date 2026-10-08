"""No model calls: scan every XLSX from review-qualified current/historical cases."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from openpyxl import load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.delivery_text import xlsx_direction_issues

p=argparse.ArgumentParser();p.add_argument('evaluation_root',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
batch=a.evaluation_root/'blind-eval-F203-gate-20261009';reviews={}
for round in (1,2):
    for r in json.loads((batch/f'review-v4-round{round}-decoded.json').read_text('utf8'))['rows']:
        reviews.setdefault(r['label'],{})[str(round)]=len(r['material_defects'])
candidates=[];selection=[]
for label,counts in reviews.items():
    if 0 not in counts.values():continue
    delivered=json.loads((batch/(label+'-deliverables.json')).read_text('utf8'))
    entries=[x for x in delivered['artifacts'] if x['name'].lower().endswith('.xlsx') and x.get('httpStatus')==200]
    selection.append({'batch':batch.name,'case':label,'material_defect_counts':counts,'xlsx_files':len(entries)})
    candidates.extend((batch/(label+'-artifacts')/r['localFile'],label,counts) for r in entries)
for name in ('blind-eval-F14-B-review-corrected-20261008','blind-eval-F14-X7-review-20261008'):
    for round in (1,2):
        folder=a.evaluation_root/name/f'round{round}'
        for r in json.loads((folder/'review.json').read_text('utf8'))['reviews']:
            if r.get('material_defects'):continue
            case=folder/r['case_id']
            entries=[x for x in json.loads((case/'files.json').read_text('utf8')) if x.get('role')=='delivered_attachment' and x['file'].lower().endswith('.xlsx')]
            selection.append({'batch':name,'round':round,'case':r['case_id'],'material_defect_counts':{str(round):0},'xlsx_files':len(entries)})
            candidates.extend((case/x['file'],r['case_id'],{str(round):0}) for x in entries)
records=[];seen=set()
for path,label,counts in candidates:
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest in seen:continue
    seen.add(digest)
    source=path.relative_to(a.evaluation_root).as_posix();issues=xlsx_direction_issues(path,source)
    workbook=load_workbook(path,read_only=True,data_only=False)
    try:cells=sum(isinstance(c.value,str) and c.data_type!='f' for sheet in workbook for row in sheet for c in row)
    finally:workbook.close()
    errors=[i for i in issues if i.get('severity')!='notice'];notices=[i for i in issues if i.get('severity')=='notice']
    records.append({'source':source,'case':label,'material_defect_counts':counts,'sha256':digest,'string_cells':cells,
        'error_cells':len({(i['sheet'],i['cell']) for i in errors}),'notice_cells':len({(i['sheet'],i['cell']) for i in notices}),
        'errors':errors,'notices':notices})
result={'selection_rule':'Every delivered XLSX of a case rated no material defects by at least one independent review in F203/F14-B corrected/F14-X7; conflicting second reviews retained explicitly; deduplicate identical bytes; no filtering after lint.',
    'selected_cases':selection,'unique_workbooks':len(records),'string_cells':sum(r['string_cells'] for r in records),
    'error_count':sum(len(r['errors']) for r in records),'error_cells':sum(r['error_cells'] for r in records),
    'notice_count':sum(len(r['notices']) for r in records),'notice_cells':sum(r['notice_cells'] for r in records),'records':records}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ('selected_cases','records')},ensure_ascii=False))
print(json.dumps(records,ensure_ascii=False))

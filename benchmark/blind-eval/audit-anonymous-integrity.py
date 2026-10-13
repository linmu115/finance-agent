"""Check CSV cell boundaries/numbers and image bytes against original deliverables."""
import argparse
import csv
import io
import json
import re
import zipfile
from pathlib import Path

NUM = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?$')
p=argparse.ArgumentParser();p.add_argument('study');p.add_argument('anonymous');a=p.parse_args()
study=Path(a.study);anonymous=Path(a.anonymous)
mapping=json.loads((anonymous/'private-map.json').read_text('utf8'))
csv_checks=[];images=[]


def inspect(original, target, suffix, origin):
    if suffix=='.csv':
        before=list(csv.reader(io.StringIO(original.decode('utf-8-sig'))))
        after=list(csv.reader(io.StringIO(target.read_text('utf-8-sig'))))
        assert len(before)==len(after),(origin,'row count changed')
        assert [len(r) for r in before]==[len(r) for r in after],(origin,'column count changed')
        numeric=0
        for br,ar in zip(before,after):
            for old,new in zip(br,ar):
                if NUM.fullmatch(old.strip()):
                    assert old==new,(origin,'numeric cell changed',old,new)
                    numeric+=1
        csv_checks.append({'source':origin,'anonymous':str(target.relative_to(anonymous)),'rows':len(before),'numeric_cells_unchanged':numeric})
    elif suffix in ['.png','.jpg','.jpeg']:
        assert original==target.read_bytes(),(origin,'image bytes changed')
        images.append({'source':origin,'anonymous':str(target.relative_to(anonymous)),'bytes_unchanged':True,'visible_identity_review':'pending separate actual image inspection'})
    elif suffix=='.zip':
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            members=[m for m in z.infolist() if not m.is_dir()]
            for j,m in enumerate(members,1):
                ext=Path(m.filename).suffix
                dest=target/f'member_{j:03}{ext}'
                if ext=='.zip':dest=dest.with_suffix('.zip.expanded')
                inspect(z.read(m),dest,ext,origin+'!'+m.filename)


for case in mapping['cases']:
    for item in case['files']:
        art=item['original'];local=art.get('localFile') or art.get('evaluatorLocalFile')
        if not local:continue
        original=study/(case['label']+'-artifacts')/local
        target=anonymous/'packet'/case['case_id']/item['anonymous']
        if target.suffix=='.zip':target=target.with_name(target.name+'.expanded')
        inspect(original.read_bytes(),target,original.suffix,case['label']+'/'+art['name'])
result={'csv_structure_and_numeric_cells_preserved':True,'csv_count':len(csv_checks),
        'numeric_cells_checked':sum(c['numeric_cells_unchanged'] for c in csv_checks),'csv_checks':csv_checks,
        'image_bytes_preserved':True,'images':images,'limit':'Does not grade financial semantics or certify no visible identity clues. No score files or reviewer inputs changed.'}
(anonymous/'integrity-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps({k:result[k] for k in ['csv_count','numeric_cells_checked','image_bytes_preserved']}))

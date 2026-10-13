"""Inventory exact downloaded deliveries and parse delivered Python without executing it.

This is not an A5 consistency scanner. Financial/direction checks still use the
existing mainline A5 CLI and independent reviewers.
"""
import argparse
import hashlib
import io
import json
import zipfile
import subprocess
from pathlib import Path
from blind import read, dump, output

p = argparse.ArgumentParser()
p.add_argument('study')
a = p.parse_args()
study = output(a.study)
state = read(study / 'experiment.json')
deliveries, codes, images, code_inputs = [], [], [], []


def inspect_code(label, filename, raw, member=None):
    record = {'label': label, 'file': filename, 'archive_member': member,
              'sha256': hashlib.sha256(raw).hexdigest()}
    codes.append(record)
    code_inputs.append({'filename':filename,'source':raw.decode('utf-8-sig')})


for run in state['runs']:
    path = study / (run['label'] + '-deliverables.json')
    if not path.exists():
        continue
    manifest = read(path)
    for artifact in manifest['artifacts']:
        local = artifact.get('localFile') or artifact.get('evaluatorLocalFile')
        row = {'label': run['label'], 'name': artifact['name'],
               'http_status': artifact['httpStatus'], 'local_file': local,
               'sha256': artifact.get('sha256')}
        deliveries.append(row)
        if not local:
            continue
        file = study / (run['label'] + '-artifacts') / local
        raw = file.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact['sha256']
        ext = Path(artifact['name']).suffix.lower()
        if ext == '.py':
            inspect_code(run['label'], local, raw)
        elif ext in {'.png', '.jpg', '.jpeg'}:
            images.append({**row, 'visual_review': 'pending'})
        elif ext == '.zip':
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name in archive.namelist():
                    if name.lower().endswith('.py'):
                        inspect_code(run['label'], local, archive.read(name), name)

image_tag='finance-analysis:0.1'
image_id=subprocess.run(['docker','image','inspect',image_tag,'--format','{{.Id}}'],
                        capture_output=True,text=True,check=True).stdout.strip()
parser_code="""import ast,json,sys
results=[]
for item in json.load(sys.stdin):
    try:
        ast.parse(item['source'],filename=item['filename'])
        results.append({'syntax_valid':True})
    except SyntaxError as error:
        results.append({'syntax_valid':False,'error':str(error),'line':error.lineno})
print(json.dumps({'python':sys.version,'results':results}))
"""
parsed=subprocess.run(['docker','run','--rm','--network','none','--read-only',
                       '--cap-drop','ALL','--security-opt','no-new-privileges',
                       '--memory','128m','--cpus','1','--pids-limit','32','-i',
                       '--entrypoint','python',image_id,'-I','-c',parser_code],
                      input=json.dumps(code_inputs),capture_output=True,text=True,encoding='utf-8',check=True)
validation=json.loads(parsed.stdout)
assert len(validation['results'])==len(codes)
for code, finding in zip(codes,validation['results']):
    code.update(finding)

dump(study / 'delivery-inventory.json', {
    'deliveries': deliveries, 'images': images,
    'downloaded': sum(r['http_status'] == 200 for r in deliveries),
    'total': len(deliveries),
    'limits': 'Availability and original hashes only; no financial quality conclusion.'})
dump(study / 'delivered-code-static-check.json', {
    'files': codes, 'syntax_valid': sum(r['syntax_valid'] for r in codes),
    'syntax_invalid': sum(not r['syntax_valid'] for r in codes),
    'parser_environment':{'image':image_tag,'image_id':image_id,'python':validation['python'],
                          'execution':'ast.parse only; participant code never executed'},
    'runtime_validity': 'Unknown from parsing. Original generator replay is a separate check.'})
print(json.dumps({'downloads': len(deliveries), 'python_files': len(codes),
                  'syntax_errors': sum(not r['syntax_valid'] for r in codes)}))

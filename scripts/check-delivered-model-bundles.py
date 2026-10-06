"""Execute actual delivered model ZIPs inside the isolated analysis container."""
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sandbox import create_runner
trial=ROOT/'data/evaluation'/os.environ.get('FINANCE_COMPARISON_DIR','pi-analysis-20261006')
state=json.loads((trial/'experiment.json').read_text(encoding='utf-8'))
result_path=trial/'bundle-replay-results.json'
results=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else []
runner=create_runner(trial/'bundle-replay')
code='''import json,runpy,zipfile
from pathlib import Path
dest=Path('/output/recomputed');dest.mkdir()
with zipfile.ZipFile('/input/model_bundle.zip') as z:z.extractall(dest)
runpy.run_path(str(dest/'recompute_models.py'),run_name='__main__')
models=json.loads((dest/'models.json').read_text(encoding='utf-8'))
checks={key:json.loads((dest/(key+'_recomputed.json')).read_text())==model['result'] for key,model in models.items()}
Path('/output/checks.json').write_text(json.dumps(checks))
assert all(checks.values()),checks
'''
for run in state['runs']:
    if run['status']!='completed':continue
    manifest=trial/(run['label']+'-deliverables.json')
    if not manifest.exists():continue
    files=json.loads(manifest.read_text(encoding='utf-8'))['artifacts']
    bundles=[a for a in files if a['name']=='model_bundle.zip']
    if not bundles:continue
    selected=bundles[-1];source=trial/(run['label']+'-artifacts')/selected['localFile']
    if any(r['label']==run['label'] and r['bundle_sha256']==selected['sha256'] for r in results):continue
    r=runner.run(code,{'model_bundle.zip':source},project_id='bundle-replay')
    item={'label':run['label'],'bundle_sha256':selected['sha256'],'status':r['status'],'removed':r.get('container_removed'),'error':r.get('error'),'stderr':r.get('stderr')}
    if r['status']=='succeeded':item['models']=json.loads((trial/'bundle-replay'/r['run_id']/'output/checks.json').read_text())
    results.append(item);print(json.dumps(item),flush=True)
result_path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

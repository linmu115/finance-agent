"""Re-run delivered analysis in the same isolated container, never on the host."""
import json
import os
import sys
import zipfile
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sandbox import create_runner
trial=ROOT/'data/evaluation'/os.environ.get('FINANCE_COMPARISON_DIR','pi-analysis-20261005-r2')
experiment=json.loads((trial/'experiment.json').read_text(encoding='utf-8'))
out=trial/'replay-results.json'
results=json.loads(out.read_text(encoding='utf-8')) if out.exists() else []
runner=create_runner(trial/'artifact-replay')
for run in experiment['runs']:
    delivered=trial/(run['label']+'-deliverables.json')
    if run['status']!='completed' or not delivered.exists():continue
    manifest=json.loads(delivered.read_text(encoding='utf-8'))
    ids=[x['runId'] for x in manifest['evaluatorScripts'] if x['status']=='succeeded']
    if not ids:continue
    chosen={}
    for item in manifest['artifacts']:
        name=item['name']
        if name=='executed_script.py' or name.startswith('_') or name=='probe.json':continue
        chosen[name]=item['url'].split('/')[-2]
    targets=[i for i in ids if i in set(chosen.values())]
    for original_id in targets:
        if any(x['label']==run['label'] and x['original_run']==original_id for x in results):continue
        original=ROOT/'data/active/analysis'/original_id
        state=json.loads((original/'state.json').read_text(encoding='utf-8'))
        if state['project_id']!=experiment['projectId']:raise ValueError('Project mismatch')
        inputs={p.name:p for p in (original/'input').iterdir() if p.name!='__analysis__.py'}
        reproduced=runner.run((original/'input/__analysis__.py').read_text(encoding='utf-8'),inputs,project_id='analysis-comparison-replay')
        actual={a['name']:a for a in reproduced.get('artifacts',[])}
        checks=[{'name':a['name'],'matches':actual.get(a['name'],{}).get('sha256')==a['sha256'],'type':Path(a['name']).suffix} for a in state.get('artifacts',[])]
        # ZIP creation timestamps change; compare the saved entry bytes too.
        for check in checks:
            if check['type']=='.zip' and not check['matches'] and check['name'] in actual:
                def entries(file):
                    with zipfile.ZipFile(file) as archive:
                        return {n:sha256(archive.read(n)).hexdigest() for n in archive.namelist()}
                check['entryBytesMatch']=entries(original/'output'/check['name'])==entries(trial/'artifact-replay'/reproduced['run_id']/'output'/check['name'])
        result={'label':run['label'],'original_run':original_id,'replay_run':reproduced['run_id'],'status':reproduced['status'],'removed':reproduced.get('container_removed'),'checks':checks,'error':reproduced.get('error')}
        results.append(result);out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'label':run['label'],'status':result['status'],'matched':sum(x['matches'] for x in checks),'total':len(checks)},ensure_ascii=False),flush=True)

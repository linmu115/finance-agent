"""Post-comparison replay: change only shared plot defaults, no model requests."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sandbox import create_runner

trial=ROOT/'data/evaluation/pi-analysis-20261005-cpa'
state=json.loads((trial/'experiment.json').read_text(encoding='utf-8'))
if any(r['status']!='completed' for r in state['runs']) or len(state['runs'])!=9:
    raise RuntimeError('Run only after the frozen comparison has finished')
runner=create_runner(trial/'post-trial-layout-replay')
results=[]
for label in ['A3','B3','C3']:
    manifest=json.loads((trial/f'{label}-deliverables.json').read_text(encoding='utf-8'))
    original_id=manifest['evaluatorScripts'][0]['runId']
    original=ROOT/'data/active/analysis'/original_id
    prior=json.loads((original/'state.json').read_text(encoding='utf-8'))
    if 'Colorbar layout of new layout engine' not in prior.get('stderr',''):
        raise RuntimeError('Unexpected regression sample')
    inputs={p.name:p for p in (original/'input').iterdir() if p.name!='__analysis__.py'}
    inputs['plot_runtime.py']=ROOT/'service/plot_runtime.py'
    result=runner.run((original/'input/__analysis__.py').read_text(encoding='utf-8'),inputs,project_id='post-trial-layout-replay')
    row={'label':label,'original_run':original_id,'original_status':prior['status'],
         'script_sha256':hashlib.sha256((original/'input/analysis.py').read_bytes()).hexdigest(),
         'replay_run':result['run_id'],'status':result['status'],
         'container_removed':result.get('container_removed'),'error':result.get('error'),
         'stderr':result.get('stderr'),'artifacts':len(result.get('artifacts',[]))}
    results.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
(trial/'post-trial-layout-replay.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

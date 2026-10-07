"""Replay the 24 diagnosed chart revisions in isolated Docker runs. No service/LLM."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sandbox.launcher import SandboxRunner


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=ROOT/'.tmp/charts-consistency/a3')
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--indices',type=int,nargs='+',help='Optional chart revision indices for focused reruns')
    a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=True)
    diagnosis=json.loads((a.source_root/'docs/evidence/seam-diagnosis-20261007.json').read_text('utf-8'))
    samples=[]
    for i,chart in enumerate(diagnosis['question6']['charts']):
        key=f'{i:02d}-{chart["study"]}-{chart["label"]}'
        source=a.source_root/'data/active/analysis'/chart['producerAnalysisId']
        target=a.destination/'snapshots'/key
        if not target.exists():
            shutil.copytree(source/'input',target/'input')
            shutil.copytree(source/'output',target/'original_output')
            shutil.copyfile(a.source_root/chart['artifactPath'],target/'original.png')
        samples.append({**chart,'key':key,'snapshot':str(target)})
    (a.destination/'samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if a.prepare_only:
        print(json.dumps({'copied':len(samples),'destination':str(a.destination)}));return
    runner=SandboxRunner(a.destination/'runs')
    available=runner.availability()
    if not available['available']:raise RuntimeError(available)
    result_path=a.destination/'results.json'
    results=json.loads(result_path.read_text('utf-8')) if a.resume and result_path.exists() else []
    for sample in samples:
        if a.indices is not None and int(sample['key'][:2]) not in a.indices:continue
        if any(r['key']==sample['key'] and r['status']=='succeeded' for r in results):continue
        target=Path(sample['snapshot']);original=target/'input'
        inputs={f.name:f for f in original.iterdir() if f.is_file() and f.name!='__analysis__.py'}
        inputs['plot_runtime.py']=ROOT/'service/plot_runtime.py'
        state=runner.run((original/'__analysis__.py').read_text('utf-8'),inputs,project_id='n2-chart-replay')
        row={k:sample[k] for k in ('key','study','label','artifactName','producerAnalysisId')}
        row.update({k:state.get(k) for k in ('run_id','status','error','stderr','container_removed')})
        if state['status']=='succeeded':
            output=runner.root/state['run_id']/'output';name=sample['artifactName']
            row['rendered_image']=str(output/name)
            diagnostic=json.loads((output/'plot_diagnostics.json').read_text('utf-8'))
            row['diagnostics']=next(f for f in diagnostic['files'] if Path(f['file']).name==name)
            equal=[];changed=[]
            for old in (target/'original_output').iterdir():
                new=output/old.name
                if old.suffix.lower() in ('.csv','.json') and new.is_file():
                    same=json.loads(old.read_text('utf-8-sig'))==json.loads(new.read_text('utf-8-sig')) if old.suffix=='.json' else old.read_text('utf-8-sig')==new.read_text('utf-8-sig')
                    (equal if same else changed).append(old.name)
            row.update(unchanged_numeric_files=equal,changed_numeric_files=changed)
        results=[r for r in results if r['key']!=row['key']]+[row]
        result_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:row[k] for k in ('key','run_id','status','error')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()

"""All exposed analysis versions and native model bundles, using the existing Docker runner."""
import argparse,json,re,sys,zipfile
from hashlib import sha256
from pathlib import Path
from blind import ROOT,read,dump,output
sys.path.insert(0,str(ROOT))

def targets(trial):
    experiment=read(trial/'experiment.json');selected=[];bundles=[]
    for run in experiment['runs']:
        manifest=trial/(run['label']+'-deliverables.json')
        if not manifest.exists():continue
        delivered=read(manifest)
        exposed={m[1] for a in delivered['artifacts'] if (m:=re.search(r'/artifacts/([a-f0-9]{32})/',a['url']))}
        for s in delivered['evaluatorScripts']:
            if s['status']=='succeeded' and s['runId'] in exposed:selected.append((run,s))
        for a in delivered['artifacts']:
            if a['name'].endswith('model_bundle.zip') and a['httpStatus']==200:bundles.append((run,a))
    return experiment,selected,bundles

def replay(trial):
    from sandbox import create_runner
    experiment,selected,bundles=targets(trial)
    p=trial/'replay-results.json';results=read(p) if p.exists() else [];runner=create_runner(trial/'artifact-replay')
    for run,s in selected:
        original_id=s['runId']
        if any(r['label']==run['label'] and r['original_run']==original_id for r in results):continue
        original=ROOT/'data/active/analysis'/original_id;saved=read(original/'state.json')
        if saved['project_id']!=(run.get('projectId') or experiment.get('projectId')):raise ValueError('Project mismatch')
        inputs={p.name:p for p in (original/'input').iterdir() if p.name!='__analysis__.py'}
        reproduced=runner.run((original/'input/__analysis__.py').read_text('utf-8'),inputs,project_id='blind-eval-replay')
        actual={a['name']:a for a in reproduced.get('artifacts',[])};checks=[]
        for a in saved.get('artifacts',[]):
            name=a['name'];check={'name':name,'matches':actual.get(name,{}).get('sha256')==a['sha256']}
            if name.endswith('.zip') and not check['matches'] and name in actual:
                def entries(p):
                    with zipfile.ZipFile(p) as z:return {n:sha256(z.read(n)).hexdigest() for n in z.namelist()}
                check['entryBytesMatch']=entries(original/'output'/name)==entries(trial/'artifact-replay'/reproduced['run_id']/'output'/name)
            checks.append(check)
        results.append({'label':run['label'],'original_run':original_id,'replay_run':reproduced['run_id'],'status':reproduced['status'],'removed':reproduced.get('container_removed'),'checks':checks,'error':reproduced.get('error'),'stderr':reproduced.get('stderr')});dump(p,results)
    bp=trial/'bundle-replay-results.json';br=read(bp) if bp.exists() else [];runner=create_runner(trial/'bundle-replay')
    # This string runs only inside the existing sandbox; no participant code runs in this process.
    code="""import json,runpy,zipfile
from pathlib import Path
dest=Path('/output/recomputed');dest.mkdir()
with zipfile.ZipFile('/input/model_bundle.zip') as z:
    for name in z.namelist():
        if not (dest/name).resolve().is_relative_to(dest):raise ValueError('Archive path escapes output')
    z.extractall(dest)
runpy.run_path(str(dest/'recompute_models.py'),run_name='__main__')
models=json.loads((dest/'models.json').read_text())
comparisons=json.loads((dest/'comparisons.json').read_text())
checks={key:json.loads((dest/(key+'_recomputed.json')).read_text())==model['result'] for key,model in models.items()}
checks.update({'comparison:'+key:json.loads((dest/(key+'_recomputed.json')).read_text())==v for key,v in comparisons.items()})
Path('/output/checks.json').write_text(json.dumps(checks))
assert checks and all(checks.values()),checks
"""
    for run,a in bundles:
        if any(r['label']==run['label'] and r['bundle_sha256']==a['sha256'] for r in br):continue
        source=trial/(run['label']+'-artifacts')/a['localFile'];r=runner.run(code,{'model_bundle.zip':source},project_id='blind-eval-bundle-replay')
        record={'label':run['label'],'bundle_sha256':a['sha256'],'status':r['status'],'removed':r.get('container_removed'),'error':r.get('error'),'stderr':r.get('stderr')}
        if r['status']=='succeeded':record['checks']=read(trial/'bundle-replay'/r['run_id']/'output/checks.json')
        br.append(record);dump(bp,br)
    dump(p,results);dump(bp,br)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trial');p.add_argument('--plan',action='store_true');a=p.parse_args();trial=Path(a.trial).resolve() if a.plan else output(a.trial)
    if a.plan:
        _,analyses,bundles=targets(trial);print(json.dumps({'analysis_versions':len(analyses),'model_bundles':len(bundles),'executed':False}))
    else:replay(trial)

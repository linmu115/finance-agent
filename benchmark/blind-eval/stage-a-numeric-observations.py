"""Explicit post-delivery cell bindings to unchanged development gold; no number scanner."""
import argparse, hashlib, json
from decimal import Decimal
from pathlib import Path
from blind import ROOT, read, dump, output
from metrics import numeric,UNITS

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def at(obj, path):
    for key in path:obj=obj[key]
    return obj

p=argparse.ArgumentParser();p.add_argument('study');p.add_argument('bindings');a=p.parse_args()
study=output(a.study);bindings=read(a.bindings);state=read(study/'experiment.json')
gold_path=ROOT/'benchmark/blind-eval/reference-development.json'
frozen=next(x['sha256'] for x in state['phaseFreezes']['1']['references'] if x['path'].endswith('reference-development.json'))
if sha(gold_path)!=frozen:raise ValueError('Development gold differs from pre-answer freeze')
gold=read(gold_path);reports=[]
for group in bindings['runs']:
    folder=study/(group['label']+'-artifacts');manifest={'checks':[]};proof=[]
    delivered=read(study/(group['label']+'-deliverables.json'))
    available={x.get('localFile') or x.get('evaluatorLocalFile') for x in delivered['artifacts']}
    for b in group['bindings']:
        file=folder/b['file']
        if b['file'] not in available:raise ValueError('Binding is not an original manifest artifact')
        if sha(file)!=b['sha256']:raise ValueError('Artifact changed since binding')
        unit_file=folder/b.get('unit_evidence_file',b['file'])
        if b['unit_quote'] not in unit_file.read_text('utf-8-sig'):raise ValueError('Unit evidence absent')
        expected=Decimal(str(at(gold,b['gold_path'])))*Decimal(str(b.get('gold_sign',1)))
        # The frozen notes permit half the final displayed digit plus 1e-8.
        tolerance=Decimal(5).scaleb(-b['display_decimals']-1)*Decimal(str(UNITS[b['unit']][1]))/Decimal(str(UNITS[b['gold_unit']][1]))
        spec={k:b[k] for k in ['file','format','unit']}
        spec.update({k:b[k] for k in ['row','column','path'] if k in b})
        spec.update(key=b['key'],expected={'value':str(expected),'unit':b['gold_unit'],'absolute_tolerance':float(tolerance)})
        manifest['checks'].append(spec)
        proof.append({k:b[k] for k in ['key','file','sha256','gold_path','gold_sign','unit_evidence_file','unit_quote','display_decimals'] if k in b})
    result=numeric(manifest,folder)
    result.update(label=group['label'],gold_sha256=frozen,binding_provenance=proof,unbound=group.get('unbound',[]),scope='Explicit CSV/JSON cell observations only. No automatic material-defect verdict; semantic identity, alternative source values, prose and figures remain independently judged.')
    dump(study/(group['label']+'-gold-numeric.json'),result)
    reports.append({'label':group['label'],'checks':len(result['checks']),'statuses':{status:sum(c['status']==status for c in result['checks']) for status in sorted({c['status'] for c in result['checks']})}})
dump(study/'stage-A-numeric-summary.json',{'bindings_sha256':sha(Path(a.bindings)),'gold_sha256':frozen,'reports':reports})
print(json.dumps(reports,ensure_ascii=False))

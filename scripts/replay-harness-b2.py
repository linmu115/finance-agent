"""Read frozen records without writes; evaluate the trusted calculator and its bundle."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import json,sqlite3,subprocess,sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.model_inputs import resolve_inputs,apply_overrides
from service.research_models import evaluate_model
from service.model_comparison import compare_models
from service.model_delivery import deliver_saved
from service.analysis_report import bind_text
from service.tests.test_dcf_fcf import BASE
PROJECT='03b52dde-19da-49c1-949a-ee6d93bf036b'
TARGET=ROOT/'data/evaluation/harness-v2-b2-20261007';TARGET.mkdir(parents=True,exist_ok=True)
class ReadOnlyStore:
    @contextmanager
    def connect(self):
        db=sqlite3.connect((ROOT/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()
    def project(self,project):
        with self.connect() as db:assert db.execute('SELECT project_id FROM projects WHERE project_id=?',(project,)).fetchone()

bindings={f'fcf.{i}':{'record_id':rid} for i,rid in enumerate(['f05db7476c5f46ada5ad6aa06f06d0fd','bcf3cb56d6d7426c979475301230d1db','24a152bc4bd342e7b05c740434adf250','83b6aafdb85e47c29ff60037f3882c8f','ed868a6d121f4a5b933294da2f9f577d'])}
bindings.update({k:{'record_id':v} for k,v in {'wacc':'aa0de70513544c1aacea3c52dc3696e5','g':'c039a12597a84c8f8301547d91e1bae7','net_cash':'1a969dda51404aa4b92712e24842f605','shares.count':'478dd84b1bb944e1afd9675eb94ef539','fx':'e7f1defea118493496f2893c6890dc43','eps':'c31c28710bb141918fe6d744d3ead8a3','target_price':'ad7b490e909a4d6893a0173d7657d6b9'}.items()})
service=SimpleNamespace(store=ReadOnlyStore());bound=resolve_inputs(service,PROJECT,BASE,bindings,'dcf_fcf');spec=bound['spec'];result=evaluate_model('dcf_fcf',spec)
updated=apply_overrides(spec,{'wacc':{'+':'.005'},'fcf':{'*':'.9'}})['spec']
for path,op in [('wacc',{'+':'.005'}),('fcf',{'*':'.9'})]:
    updated.setdefault('input_transformations',{})[path]=[{'operator':op,'source_model':'frozen-baseline'}]
    for key in updated['source_refs']:
        if key==path or key.startswith(path+'.'):updated['input_basis'][key]={'basis':'assumption','rationale':'Explicit sensitivity applied to source record.'}
new=evaluate_model('dcf_fcf',updated);comparison=compare_models('dcf_fcf',spec,updated,['wacc','fcf'])
gold=json.loads((ROOT/'data/active/analysis/e309e919e04d453dac26c42583498ea8/output/update_results.json').read_text(encoding='utf8'))
checks=[]
def check(key,actual,expected):checks.append({'cell':key,'actual':str(actual),'expected':str(expected),'pass':abs(Decimal(str(actual))-Decimal(str(expected)))<Decimal('1e-25')})
mapping={'enterprise_value':'EV_RMB_mn','equity_value':'equity_RMB_mn','value_per_share':'HKD_per_share','explicit_forecast_pv':'explicit_pv_RMB_mn','terminal_pv':'terminal_pv_RMB_mn'}
for name,value,reference in [('base',result,gold['base']),('updated',new,gold['updated'])]:
    for key,gkey in mapping.items():check(name+'.'+key,value['results'][key],reference[gkey])
    grids=sum(gold['sensitivity']['base' if name=='base' else 'updated'],[])
    for i,(row,expected) in enumerate(zip(value['tables']['sensitivity'],grids)):check(name+'.sensitivity.'+str(i),row['value_per_share'],expected)
step=evaluate_model('dcf_fcf',apply_overrides(spec,{'wacc':{'+':'.005'}})['spec'])
for key,gkey in mapping.items():check('wacc_only.'+key,step['results'][key],gold['after_wacc_only'][gkey])
contrib=list(gold['contribution_HKD_per_share'].values())
for i,row in enumerate(comparison['decomposition']['steps']):check('contribution.'+row['path'],row['contribution'],contrib[i])
eps_new=resolve_inputs(service,PROJECT,spec,{'eps':{'record_id':'7e189e2c06114d1cbcb22a079d7c6924'}},'dcf_fcf')
eps_result=evaluate_model('dcf_fcf',eps_new['spec']);check('eps2024',result['results']['eps'],'.63');check('eps2025',eps_result['results']['eps'],'.83')
stamp=datetime.now().strftime('%Y%m%dT%H%M%S');revision=lambda name:name+'_'+stamp
folder=TARGET/'research'/PROJECT/'artifacts';folder.mkdir(parents=True,exist_ok=True)
for name,s,r in [('base',spec,result),('updated',updated,new)]:
    (folder/(revision(name)+'.json')).write_text(json.dumps({'id':name,'revision_id':revision(name),'kind':'dcf_fcf','spec':s,'result':r},ensure_ascii=False),encoding='utf8')
delivery=deliver_saved(TARGET,PROJECT,{'saved':{'artifact_id':'updated','revision_id':revision('updated')},'previous':{'artifact_id':'base','revision_id':revision('base')}},{'update':{'baseline':'previous','scenario':'saved','order':['wacc','fcf']}})
directory=TARGET/delivery['folder'];recomputed=subprocess.run([sys.executable,str(directory/'recompute_models.py')],cwd=directory,capture_output=True,text=True)
assert recomputed.returncode==0,recomputed.stderr
bundle_result=json.loads((directory/'saved_recomputed.json').read_text(encoding='utf8'));assert bundle_result==new
bound_text=bind_text('基准EPS {{dcf_summary.eps.value}}；更新估值 {{dcf_summary.value_per_share.value}}。',new['report']['tables'])
bad_units=[]
for path,rid in [('fcf.0',bindings['wacc']['record_id']),('target_price','906842196a3a457eb742a64d72922ab0')]:
    try:resolve_inputs(service,PROJECT,spec,{path:{'record_id':rid}},'dcf_fcf')
    except ValueError as exc:bad_units.append({'path':path,'error':str(exc)})
    else:raise AssertionError('incompatible unit accepted')
evidence={'method':'Read-only existing records; trusted Decimal calculator, no LLM. Reference C3 32-digit Decimal, tolerance 1e-25. No participant Python executed on host.',
 'bindings':bound['bindings'],'spec':spec,'baseline':result,'updated':new,'comparison':comparison,'checks':checks,'all_pass':all(c['pass'] for c in checks),
 'eps_2025_binding':eps_new['bindings'],'binding_text':bound_text,'bad_units_rejected':bad_units,'bundle_recompute_equal':True,'delivery':delivery,
 'limitations':['Source FX record is labelled 倍; fx direction is explicitly defined by currency/price_currency, not inferred from magnitude.','Target record alone cannot identify a five-factor bridge; only price gap returned.','No NCI record supplied: equity value explicitly excludes this unknown adjustment.','Tool/unit agreement does not prove the prior ingestion records are semantically correct.']}
full_path=TARGET/('replay-'+stamp+'.json');full_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
summary={k:evidence[k] for k in ('method','bindings','spec','checks','all_pass','eps_2025_binding','binding_text','bad_units_rejected','bundle_recompute_equal','limitations')}
summary.update(baseline_results=result['results'],updated_results=new['results'],contributions=comparison['decomposition'],
    delivery={k:v for k,v in delivery.items() if k not in ('results','numeric_tables')},full_evidence_path=str(full_path.relative_to(ROOT)),
    evidence_cells_retained=sum(len(t.get('evidence',[])) for t in new['report']['tables'].values()))
(ROOT/'docs/evidence/harness-v2-20261007/b2-replay.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
print(json.dumps({'checks':len(checks),'all_pass':evidence['all_pass'],'EPS':bound_text,'bundle_recomputed':True,'attachments':delivery['attachments']},ensure_ascii=False))
assert evidence['all_pass']

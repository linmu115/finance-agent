"""Export immutable models and the actual calculator used to produce them."""
import csv
import io
import json
import re
import zipfile
from pathlib import Path


RECOMPUTE = '''import json, sys
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'finance_model_code.zip'))
from finance_model.research_models import evaluate_model, export_csv
from finance_model.model_comparison import compare_models
models=json.loads((root/'models.json').read_text(encoding='utf-8'))
for name,model in models.items():
    result=evaluate_model(model['kind'],model['spec'])
    (root/(name+'_recomputed.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for table in result['tables']:
        (root/(name+'_'+table+'.csv')).write_text(export_csv(result,table),encoding='utf-8-sig')
for name,request in json.loads((root/'comparison_requests.json').read_text(encoding='utf-8')).items():
    left,right=models[request['baseline']],models[request['scenario']]
    result=compare_models(left['kind'],left['spec'],right['spec'],request.get('order'))
    (root/(name+'_recomputed.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('Recomputed saved model inputs and comparisons with the bundled original calculator.')
'''


def safe_name(name):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('model_alias_or_revision_invalid: '+str(name))
    return name


def select_models(root, project_id, references):
    models={}
    for name,ref in references.items():
        safe_name(name)
        revision=safe_name(ref['revision_id'])
        saved=json.loads((root/'research'/project_id/'artifacts'/(revision+'.json')).read_text(encoding='utf-8'))
        if saved['id']!=ref['artifact_id'] or not saved.get('spec'):raise ValueError('model_revision_not_found_in_project')
        models[name]=saved
    return models


def csv_rows(rows):
    out=io.StringIO(newline='')
    keys=list(dict.fromkeys(key for row in rows for key in row))
    writer=csv.DictWriter(out,fieldnames=keys,lineterminator='\n');writer.writeheader()
    for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    return out.getvalue()


def prepare_delivery(export,models,comparison_requests):
    from .model_comparison import compare_models, leaves
    from .research_models import export_csv
    comparisons={}
    for name,request in comparison_requests.items():
        safe_name(name)
        left,right=models[request['baseline']],models[request['scenario']]
        if left['kind']!=right['kind']:raise ValueError('comparison_models_require_same_kind')
        comparisons[name]=compare_models(left['kind'],left['spec'],right['spec'],request.get('order'))
    # Only trusted, database-free calculator code is packaged. Nothing written
    # by the model is imported or executed in the host process.
    code=export/'finance_model_code.zip'
    with zipfile.ZipFile(code,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('finance_model/__init__.py','')
        for filename in ('research_models.py','model_review.py','model_inputs.py','model_comparison.py','three_statement.py'):
            z.write(Path(__file__).with_name(filename),'finance_model/'+filename)
    files={'models.json':json.dumps(models,ensure_ascii=False,indent=2),
           'comparison_requests.json':json.dumps(comparison_requests,ensure_ascii=False,indent=2),
           'comparisons.json':json.dumps(comparisons,ensure_ascii=False,indent=2),
           'recompute_models.py':RECOMPUTE}
    for name,model in models.items():
        files[name+'_inputs.csv']=csv_rows([{'path':p,'value':v,'source':model['spec'].get('source_refs',{}).get(p),'basis':model['spec'].get('input_basis',{}).get(p)} for p,v in leaves(model['spec'])])
        for table in model['result']['tables']:
            files[name+'_'+safe_name(table)+'.csv']=export_csv(model['result'],table)
    for name,result in comparisons.items():
        files[name+'_inputs_changed.csv']=csv_rows(result['changed_inputs'])
        files[name+'_results_changed.csv']=csv_rows([{'metric':k,**v} for k,v in result['result_changes'].items()])
        if result.get('forecast_changes'):files[name+'_forecast_changes.csv']=csv_rows(result['forecast_changes'])
        if result.get('decomposition'):files[name+'_decomposition.csv']=csv_rows(result['decomposition']['steps'])
    for name,text in files.items():(export/name).write_text(text,encoding='utf-8-sig' if name.endswith('.csv') else 'utf-8')
    with zipfile.ZipFile(export/'model_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in [*files,'finance_model_code.zip']:z.write(export/name,name)
        z.writestr('README.txt','Run python recompute_models.py (standard library only). models.json preserves the exact inputs, results, revisions and citations. Model choices and assumptions remain explicit; this package does not infer new data.\n')
    return {name:export/name for name in [*files,'finance_model_code.zip','model_bundle.zip']}

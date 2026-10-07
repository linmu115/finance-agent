"""Export immutable models and the actual calculator used to produce them."""
import csv
import hashlib
import io
import json
import os
import re
import threading
import uuid
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


def scenario_delivery(models,requests):
    from .scenario_tables import scenario_tables
    for request in requests.values():
        left,right=models[request['baseline']],models[request['scenario']]
        if request.get('scenario_update') and left['result'].get('report') and right['result'].get('report'):
            return scenario_tables(left['result']['report']['tables'],right['result']['report']['tables'],
                left['revision_id'],right['revision_id'],'dcf_summary' if right['kind']=='dcf_fcf' else None)
    return {},None


def prepare_delivery(export,models,comparison_requests,bundle='model_bundle.zip'):
    from .model_comparison import compare_models, leaves
    from .model_units import unit_label
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
        for filename in ('research_models.py','model_review.py','model_inputs.py','model_comparison.py','three_statement.py','dcf_fcf.py','analysis_report.py','analysis_parameters.py','analysis_comparison.py','analysis_tables.py','model_units.py','scenario_tables.py'):
            z.write(Path(__file__).with_name(filename),'finance_model/'+filename)
    files={'models.json':json.dumps(models,ensure_ascii=False,indent=2),
           'comparison_requests.json':json.dumps(comparison_requests,ensure_ascii=False,indent=2),
           'comparisons.json':json.dumps(comparisons,ensure_ascii=False,indent=2),
           'recompute_models.py':RECOMPUTE}
    for name,model in models.items():
        # Every input states its unit: a rate is a fraction (unit "ratio", 0.10 = 10%), never an unlabelled number.
        files[name+'_inputs.csv']=csv_rows([{'path':p,'value':v,'unit':unit_label(model,p),'source':model['spec'].get('source_refs',{}).get(p),'basis':model['spec'].get('input_basis',{}).get(p)} for p,v in leaves(model['spec'])])
        columns=[]
        for table in model['result']['tables']:
            files[name+'_'+safe_name(table)+'.csv']=export_csv(model['result'],table)
            columns+=[{'table':table,'column':key,'unit':unit_label(model,key)} for key in dict.fromkeys(key for row in model['result']['tables'][table] for key in row)]
        columns+=[{'table':'results','column':key,'unit':unit_label(model,key)} for key in model['result'].get('results',{})]
        # The result tables keep their original headers; this file gives the unit of each column.
        files[name+'_units.csv']=csv_rows(columns)
    for name,result in comparisons.items():
        files[name+'_inputs_changed.csv']=csv_rows(result['changed_inputs'])
        files[name+'_results_changed.csv']=csv_rows([{'metric':k,**v} for k,v in result['result_changes'].items()])
        if result.get('forecast_changes'):files[name+'_forecast_changes.csv']=csv_rows(result['forecast_changes'])
        if result.get('decomposition'):files[name+'_decomposition.csv']=csv_rows(result['decomposition']['steps'])
    from .analysis_report import write_csv
    reports={name:model['result']['report'] for name,model in models.items() if model['result'].get('report')}
    reports.update({name:result['report'] for name,result in comparisons.items() if result.get('report')})
    versioned,context=scenario_delivery(models,comparison_requests)
    if context:
        from .scenario_tables import scenario_report,PREFERRED
        reports[PREFERRED]=scenario_report(versioned,context)
    for name,report in reports.items():
        files[name+'_report.md']='# '+report.get('title',name)+'\n\n'+report.get('body','')
        files[name+'_report.json']=json.dumps(report,ensure_ascii=False,indent=2)
        for table,data in report['tables'].items():
            if not re.fullmatch(r'[\w-]+',table):raise ValueError('report_table_name_invalid: '+table)
            filename=name+'_'+table+'.csv';write_csv(export/filename,data)
            files[filename]=(export/filename).read_text(encoding='utf-8-sig')
    for name,text in files.items():(export/name).write_text(text,encoding='utf-8-sig' if name.endswith('.csv') else 'utf-8')
    with zipfile.ZipFile(export/bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for name in [*files,'finance_model_code.zip']:z.write(export/name,name)
        z.writestr('README.txt','Run python recompute_models.py (standard library only). models.json preserves the exact inputs, results, revisions and citations. Model choices and assumptions remain explicit; this package does not infer new data.\nUnits: *_inputs.csv has a unit column and *_units.csv lists the unit of every result column. Amounts are in the stated currency and scale; "ratio" is a fraction (0.10 = 10%), not a percentage.\n')
    return {name:export/name for name in [*files,'finance_model_code.zip',bundle]}


# Changes whenever the set or layout of delivered files changes, so an older delivery is not reused.
DELIVERY_FORMAT='5'
# One service process owns the data directory; this orders its own threads.
_publishing=threading.Lock()


def deliver_saved(root,project_id,references,comparison_requests):
    """Publish the complete delivery of saved model versions and return what was written.

    Input, result and difference tables and the calculator bundle are produced by this trusted host
    code from the stored inputs and results of immutable revisions. No sandbox run, no model call and no
    script written by the model is involved, so saving or updating a model needs no second export step.
    The same versions and comparisons always resolve to the same delivery.
    """
    models=select_models(root,project_id,references)
    identity=json.dumps({'format':DELIVERY_FORMAT,'models':{name:[model['id'],model['revision_id']] for name,model in models.items()},'comparisons':comparison_requests},sort_keys=True,ensure_ascii=False)
    delivery_id=hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    folder=root/'research'/project_id/'deliveries'/delivery_id
    with _publishing:
        if not (folder/'delivery.json').is_file():
            folder.mkdir(parents=True,exist_ok=True)
            # The primary model's own bundle name: a later run_analysis export of other aliases cannot collide with it.
            primary=next(iter(models))
            files=prepare_delivery(folder,models,comparison_requests,primary+'_model_bundle.zip')
            attached=[name for name in files if name.endswith('_model_bundle.zip') or name.endswith(('.csv','_report.md')) and name.startswith(tuple(key+'_' for key in [primary,*comparison_requests,'基准_情景_差额']))]
            manifest={'delivery_id':delivery_id,'models':{name:{'artifact_id':model['id'],'revision_id':model['revision_id']} for name,model in models.items()},
                      'comparisons':comparison_requests,'attachments':sorted(attached),
                      'files':[{'name':name,'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in sorted(files.items())]}
            # The manifest appears last and in one step. A folder without it is an unfinished delivery and is written again.
            pending=folder/('delivery.'+uuid.uuid4().hex+'.tmp')
            pending.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(pending,folder/'delivery.json')
    manifest=json.loads((folder/'delivery.json').read_text(encoding='utf-8'))
    manifest['folder']=str(folder.relative_to(root))
    manifest['results']=json.loads((folder/'comparisons.json').read_text(encoding='utf-8'))
    primary=next(iter(models));tables=dict(models[primary]['result'].get('report',{}).get('tables',{}))
    versioned,context=scenario_delivery(models,comparison_requests)
    if context:
        tables=versioned
        manifest['scenario_context']=context
    for result in manifest['results'].values():tables.update(result.get('report',{}).get('tables',{}))
    if tables:manifest['numeric_tables']=tables
    return manifest

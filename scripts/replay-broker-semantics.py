"""Replay explicitly copied broker sources/receipts in a new scratch database.

No model, production database, HTTP service or generated Python is involved.
Legacy receipts are seeded via the existing persistence method, then resumed
through the production deterministic validators and ordinary pending-table queue.
"""
import argparse
import copy
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.semantic import materialize
from service.script_cleaning import _hash, CleaningValidationError
from service.store import dumps

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
args=p.parse_args();source=Path(args.input).resolve();out=Path(args.output).resolve()
out.mkdir(parents=True,exist_ok=False);report=[]
for folder in sorted(source.iterdir()):
    if not (folder/'parsed.json').is_file():continue
    original=json.loads((folder/'document.json').read_text(encoding='utf-8-sig'))
    parsed=json.loads((folder/'parsed.json').read_text(encoding='utf-8'))
    saved=json.loads((folder/'normalization-batches.json').read_text(encoding='utf-8-sig'))
    service=FinanceService(out/folder.name);service.create_project('replay','Broker semantic replay')
    upload=service.store.root/'uploads/source.pdf';shutil.copyfile(folder/'source.pdf',upload)
    did=service.register_document('replay',str(upload),original['name'])['data']['document_id']
    service._persist_prepared('replay',did,parsed)
    profile=service.set_document_profile('replay',did,original['profile'])['data']['profile']
    payload=[];before={}
    for legacy in saved:
        index=legacy['script_table'];table=next(t for t in parsed['tables'] if t['index']==index)
        ext=copy.deepcopy(legacy['extractions']);schema=next(e['attributes'] for e in ext if e['class']=='table_schema')
        rows=[{'row':int(re.search(r':R(\d+)',e['text'])[1]),'attributes':e['attributes']} for e in ext if e['class']=='financial_row']
        batch=[{'table':table,'rows':list(range(1,len(table['rows'])+1))}]
        facts,_=materialize(ext,batch,did,'copied-legacy')
        detail={k:v for k,v in legacy.items() if k not in {'source_input_fingerprint','coordinates','issues'}}
        detail.update(profile_revision=profile['revision_id'],script_source_hash=_hash(table))
        service._commit_semantic_batch('replay',did,'copied-legacy',batch,facts,legacy['issues'],detail)
        payload.append({'index':index,'schema':schema,'rows':rows,'exclusion_reason':legacy.get('exclusion_reason')})
        before[str(index)]={'facts':len(facts),'legacy_status':legacy['status']}
    started=service.begin_script_cleaning('replay',[did],'semantic-replay','no-model')['data'];pid=started['processing_id']
    state=service._clean_state('replay',pid);doc=state['documents'][0]
    issues=[v for values in doc['validation_issues'].values() for v in values]
    state['jobs']['replay-candidate']={'document_id':did,'profile_revision':profile['revision_id'],'source_hash':_hash(parsed),
        'code_hash':'copied-original-mappings','committed_tables':[],'rule_payload':{'tables':payload}}
    service._save_processing(state)
    candidate=service.get_cleaning_result('replay',pid,'replay-candidate',limit=20)['data']
    try:commit=service.commit_cleaning_result('replay',pid,'replay-candidate')['data']
    except CleaningValidationError as error:commit=error.details
    progress=service.get_cleaning_progress('replay',pid)['data']
    result={'name':folder.name,'copied_document_id':original['id'],'scratch_document_id':did,'before':before,
        'resume_pending_tables':started['pending_tables'][did],'resume_completed_tables':started['coverage']['tables_completed'],
        'reasons':dict(Counter(i['reason'] for i in issues)),'issues':issues,'candidate':candidate,'commit':commit,
        'pending_after_commit':progress['pending_tables'][did],'model_calls':0}
    (out/(folder.name+'.json')).write_text(dumps(result),encoding='utf-8');report.append({k:v for k,v in result.items() if k not in {'issues','candidate','commit'}})
    print(dumps(report[-1]),flush=True)
    for pool in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(service,pool).shutdown(wait=True)
(out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

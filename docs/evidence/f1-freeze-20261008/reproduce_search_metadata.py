"""Isolated invented data: retain an existing search defect, no production reads."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from service.tests.test_research_ingestion import ResearchIngestionTests
from service.store import dumps

here=Path(__file__).resolve().parent
current=Path('service/research_ingestion.py').read_bytes()
baseline=subprocess.check_output(['git','show','28cf04b:service/research_ingestion.py'])
assert current==baseline
f=ResearchIngestionTests();f.setUp()
try:
    payload=copy.deepcopy(f.payload)
    payload['tables'][0]['rows'][0]['attributes']['metric']='free_cash_flow_firm'
    f.commit(payload=payload)
    # A source key is opaque metadata. It must not make a net-profit record an FCFF result.
    with f.s.store.connect(write=True) as db:
        row=db.execute("SELECT record_id,record_json FROM research_records WHERE metric='net_profit' AND is_current=1 LIMIT 1").fetchone()
        record=json.loads(row['record_json']);record['source_key']='0000fcff'+'0'*56
        db.execute('UPDATE research_records SET record_json=? WHERE record_id=?',(dumps(record),row['record_id']))
    found=f.s.query_research_records('p',{'query':'FCFF','record_type':'observation'})['data']
    exact=f.s.query_research_records('p',{'metric':'free_cash_flow_firm','record_type':'observation'})['data']
    assert any(r['metric']=='net_profit' for r in found['items'])
    assert exact['total']==2
    result={'status':'known_existing_defect_not_fixed_in_F1','baseline':'28cf04b',
            'research_ingestion_file_unchanged':True,'file_sha256':hashlib.sha256(current).hexdigest(),
            'synthetic_setup':'Injected FCFF into one unrelated record source_key; no user or production data used.',
            'keyword_results':{'total':found['total'],'metrics':[r['metric'] for r in found['items']]},
            'exact_metric_results':{'total':exact['total'],'metrics':[r['metric'] for r in exact['items']]},
            'first_failure_boundary':'First test total=3 instead of 2; its temporary database was removed by teardown, so its exact extra row is unavailable. This replay proves metadata matching can cause that symptom in the unchanged premerge query.'}
    (here/'search-metadata-known-issue.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
finally:f.tearDown()

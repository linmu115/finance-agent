"""Replay only N3's existing development copies; no HTTP, inference or main DB write."""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.script_cleaning import _hash
from service.source_numbers import policy_table_exclusion
from service.accounting_basis import identify,reapply_document_facts
from service.derived_comparisons import decoded
from service.cleaning_mapping import mapping_issues

parser=argparse.ArgumentParser()
parser.add_argument('--source-copy',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
args.out=args.out.resolve();args.source_copy=args.source_copy.resolve()
assert args.out.is_relative_to(ROOT/'tmp') and args.source_copy.is_relative_to(ROOT/'tmp')
args.out.mkdir(parents=True,exist_ok=False)

def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')

reports=[]
for name,policy,comparison,derived in [('yili',116,14,4),('haier',131,19,10)]:
    origin=args.source_copy/name;folder=args.out/name;folder.mkdir()
    manifest=json.loads((origin/'manifest.json').read_text('utf-8'))
    project,did=manifest['project'],manifest['document']
    shutil.copytree(origin/'app-data',folder/'app-data')
    service=FinanceService(folder/'app-data')
    service._schedule_embedding_index=lambda *a:None
    service._runner=lambda:(_ for _ in ()).throw(AssertionError('No sandbox or model in copied replay'))
    try:
        _,parsed=service._clean_source(project,did)
        unchanged=reapply_document_facts(service,project,did,parsed,identify(parsed),'p0-addendum-repeat')
        assert unchanged['updated']==0
        with service.store.connect() as db:
            before={r['fact_id']:dict(r) for r in db.execute('SELECT * FROM facts')}
            saved=[json.loads(r[0]) for r in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=? ORDER BY created_at DESC',(did,))]
        previous=next(b for b in saved if b.get('script_table')==comparison and not b.get('superseded_by') and b.get('extractions'))
        ext=copy.deepcopy(previous['extractions'])
        schema=next(e['attributes'] for e in ext if e['class']=='table_schema')
        rows=[{'row':int(re.search(r':R(\d+)',e['text'])[1]),'attributes':e['attributes']} for e in ext if e['class']=='financial_row']
        for attrs in [schema,*[r['attributes'] for r in rows]]:
            if attrs.get('columns_json'):attrs['columns_json']=json.dumps([c for c in decoded(attrs['columns_json']) if int(c['column'])!=derived],ensure_ascii=False)
        schema['skipped_columns_json']=json.dumps([*decoded(schema.get('skipped_columns_json')),{'column':derived,'reason':'同比列未映射'}],ensure_ascii=False)
        tab=next(t for t in parsed['tables'] if t['index']==comparison)
        before_issues=mapping_issues(tab,schema,rows)
        assert any(i['reason']=='skipped_numeric_data_column' for i in before_issues)
        policy_table=next(t for t in parsed['tables'] if t['index']==policy)
        exclusion=policy_table_exclusion(policy_table);assert exclusion
        payload={'tables':[{'index':policy,'schema':{'statement':'nonfinancial'},'rows':[],'exclusion_reason':json.dumps(exclusion,ensure_ascii=False)},
                           {'index':comparison,'schema':schema,'rows':rows}]}
        state=service._related_cleanings(project,[did])[0];pid=state['processing_id'];rid='p0-policy-comparison-replay'
        state['state']='normalizing'
        part=next(d for d in state['documents'] if d['document_id']==did)
        state['jobs'][rid]={'document_id':did,'profile_revision':part.get('profile_revision'),'source_hash':_hash(parsed),
                            'code_hash':_hash(payload),'committed_tables':[],'rule_payload':payload}
        service._save_processing(state)
        _,validated,_=service._clean_result(project,state,rid)
        errors=[i for t in validated for i in t['issues'] if i.get('severity')!='review']
        assert not errors,errors
        committed=service.commit_cleaning_result(project,pid,rid)['data']
        with service.store.connect() as db:after={r['fact_id']:dict(r) for r in db.execute('SELECT * FROM facts')}
        target_ids={f'{did}:t{policy}',f'{did}:t{comparison}'}
        others=lambda facts:{k:v for k,v in facts.items() if json.loads(v['source_json']).get('table_id') not in target_ids}
        assert others(before)==others(after)
        key=lambda f:tuple(f[k] for k in ('company','metric','period','scope','currency','value','raw_value','raw_unit'))+(json.loads(f['source_json'])['cell'],)
        old_amounts={key(f) for f in before.values() if json.loads(f['source_json']).get('table_id')==f'{did}:t{comparison}' and json.loads(f['source_json'])['column']!=derived}
        new_amounts={key(f) for f in after.values() if json.loads(f['source_json']).get('table_id')==f'{did}:t{comparison}' and json.loads(f['source_json'])['column']!=derived}
        assert old_amounts==new_amounts
        assert not [f for f in after.values() if json.loads(f['source_json']).get('table_id')==f'{did}:t{policy}']
        assert service.get_source_table(project,did,f't{policy}')['data']['items'][0]['rows']==policy_table['rows']
        same=service.commit_cleaning_result(project,pid,rid)['data']
        with service.store.connect() as db:assert after=={r['fact_id']:dict(r) for r in db.execute('SELECT * FROM facts')}
        checks=[{'cell':f['source']['cell'],'metric':f['metric'],'value':f['value'],**f['source']['normalization']['derived_comparison_check']}
                for t in validated for f in t['facts'] if f['source']['normalization'].get('derived_comparison_check')]
        report={'document':name,'policy_table':policy,'exclusion':exclusion,'comparison_table':comparison,
                'previous_omission_issues':before_issues,'committed_table_indices':committed.get('committed_tables'),
                'validated_tables':[{'table':t['index'],'facts':len(t['facts']),'issues':t['issues']} for t in validated],
                'checks':checks,'check_counts':dict(Counter(c['status'] for c in checks)),
                'other_facts_unchanged':len(others(before)),'amount_cells_unchanged':len(old_amounts),
                'source_preserved':True,'repeat_commit_changes':0,'reapply_changes':0,'model_calls':0}
        save(folder/'report.json',report);reports.append(report)
        print(name,{k:report[k] for k in ['check_counts','other_facts_unchanged','amount_cells_unchanged','model_calls']},flush=True)
    finally:
        for pool in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(service,pool).shutdown(wait=True)
save(args.out/'report.json',reports)

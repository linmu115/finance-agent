"""Replay only the three authorized historical studies, with no LLM or scripts."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.analysis_tables import collect_tables
from service.delivery_consistency import scan_delivery

STUDIES=('pi-cowork-acceptance-20261006','pi-cowork-postfix-20261007','pi-finance-generalization-20261006')
SOURCE_TOOLS={'query_financial_data','get_financial_record','get_source_page','get_source_table','get_source_segment',
              'search_document_sources','search_evidence','get_data_catalog','query_research_records',
              'calculate_financial_metrics','get_document_overview','get_records','query_records','get_document_data','get_financial_records'}


def replay(source,destination):
    destination.mkdir(parents=True,exist_ok=True)
    inventory_path=destination/'inventory.json'
    if not inventory_path.exists():shutil.copyfile(source/'tmp/seam-diagnosis-20261007/inventory.json',inventory_path)
    inventory=json.loads(inventory_path.read_text('utf8'));summary=[]
    for case in inventory:
        if case['study'] not in STUDIES:continue
        study,label=case['study'],case['label'];folder=destination/study/label;folder.mkdir(parents=True,exist_ok=True)
        session=folder/'session.jsonl'
        if not session.exists() and case.get('nativeSession'):shutil.copyfile(source/case['nativeSession'],session)
        calls={c['toolCallId']:c['name'] for c in case['calls']}
        records=[];queried=[]
        for line in session.read_text('utf8').splitlines() if session.exists() else []:
            m=json.loads(line).get('message',{});cid=m.get('toolCallId')
            if m.get('role')!='toolResult' or cid not in calls or calls[cid] not in SOURCE_TOOLS:continue
            for content in m.get('content',[]):
                if content.get('type')!='text':continue
                try:result=json.loads(content['text'])
                except json.JSONDecodeError:result={'text':content['text']}
                records.append(result);queried.append({'call_id':cid,'tool':calls[cid]})
        tables={};warnings=[]
        # Use the last exposed successful revision for a same-named table.
        for rid in case['successfulExposedAnalysisIds']:
            snapshot=destination/'analysis'/rid
            if not snapshot.exists():shutil.copytree(source/'data/active/analysis'/rid,snapshot)
            paths={f.name:f for f in (snapshot/'output').iterdir() if f.suffix.lower() in ('.json','.csv')}
            found,notes=collect_tables(paths);tables.update(found);warnings.extend(notes)
        historical=source/'data/evaluation'/study
        answer_path=historical/f'{label}-answer.md'
        answer=answer_path.read_text('utf-8-sig') if answer_path.exists() else ''
        attachments=[]
        manifest_path=historical/f'{label}-deliverables.json'
        manifest=json.loads(manifest_path.read_text('utf8')) if manifest_path.exists() else {}
        artifact_names={a['localFile']:a['name'] for a in manifest.get('artifacts',[]) if a.get('localFile')}
        for f in sorted((historical/f'{label}-artifacts').rglob('*')):
            if artifact_names and f.name not in artifact_names:continue
            if f.suffix.lower() in ('.md','.csv'):
                attachments.append({'name':f.name,'artifact':artifact_names.get(f.name,f.name),'format':f.suffix[1:],'text':f.read_text('utf-8-sig')})
        payload={'answer':answer,'tables':tables,'source_records':records,'attachments':attachments}
        (folder/'input.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
        result=scan_delivery(**payload)
        result['replay']={'study':study,'label':label,'status':case['status'],'analysis_ids':case['successfulExposedAnalysisIds'],
                          'source_calls':queried,'table_warnings':warnings,'attachments':[a['name'] for a in attachments]}
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        row={'study':study,'label':label,'counts':result['counts'],'issues':result['issue_count'],'reference_counts':result['reference_counts'],
             'result':f'{study}/{label}/result.json'}
        summary.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    (destination/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=Path)
    p.add_argument('--destination',type=Path,default=ROOT/'.tmp/charts-consistency/a5')
    a=p.parse_args();replay(a.source_root,a.destination)

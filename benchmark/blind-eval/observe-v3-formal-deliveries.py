"""Offline delivery/A5 coverage counts; never reads judge scores or adjudicates defects."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def seconds(start, end):
    return (datetime.fromisoformat(end.replace('Z','+00:00'))-
            datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds()


def observe(study):
    state=read(study/'experiment.json')
    rows=[]
    for row in state['runs']:
        if row['status'] not in {'completed','failed','cancelled','blocked_dependency'}:
            continue
        label=row['label']
        item={k:row[k] for k in ['label','taskId','split','profile','status']}
        manifest=study/(label+'-deliverables.json')
        if not manifest.exists():
            item['delivery_observation']='not_collected'
            rows.append(item)
            continue
        data=read(manifest)
        artifacts=data['artifacts']
        for artifact in artifacts:
            if artifact.get('localFile'):
                actual=hashlib.sha256((study/(label+'-artifacts')/artifact['localFile']).read_bytes()).hexdigest()
                if actual!=artifact['sha256']:
                    raise ValueError('Collected artifact changed: '+label+' '+artifact['localFile'])
        item.update(delivery_observation='collected',artifact_links=len(artifacts),
                    downloaded=sum(a['httpStatus']==200 for a in artifacts),
                    download_failed=sum(a['httpStatus']!=200 for a in artifacts),
                    format_counts=dict(Counter(Path(a['name']).suffix.lower() or '(none)' for a in artifacts)),
                    downloaded_bytes=sum(a.get('bytes',0) for a in artifacts if a['httpStatus']==200),
                    recorded_sandbox_scripts=len(data['evaluatorScripts']),
                    sandbox_script_statuses=dict(Counter(s['status'] for s in data['evaluatorScripts'])))
        raw=study/(label+'-run.json')
        conversation=study/(label+'-conversation.json')
        if raw.exists() and conversation.exists():
            run=read(raw)
            messages=[m for m in read(conversation)['messages']
                      if m.get('role')=='assistant' and m.get('runId')==row['runId'] and m.get('artifacts')]
            item['first_artifact_message_created_seconds']=min(
                (seconds(run['createdAt'],m['createdAt']) for m in messages),default=None)
            item['elapsed_seconds']=seconds(run['createdAt'],run['finishedAt']) if run.get('finishedAt') else None
        a5=study/(label+'-a5.json')
        if a5.exists():
            result=read(a5)
            assert result['scanner_run']=='scripts/scan-delivery-consistency.py'
            item['a5']={'mode':result['result']['mode'],'counts':result['result']['counts'],
                        'issue_count':result['result']['issue_count'],
                        'formats_outside_cli_scope':len(result['metadata']['unreviewed'])}
        else:
            item['a5']=None
        rows.append(item)
    aggregate=[]
    for split in sorted({r['split'] for r in rows}):
        for profile in ['original_pi','prepared','financial']:
            group=[r for r in rows if r['split']==split and r['profile']==profile]
            collected=[r for r in group if r['delivery_observation']=='collected']
            a5=[r['a5'] for r in collected if r.get('a5') is not None]
            counts=Counter()
            for r in a5:counts.update(r['counts'])
            aggregate.append({'split':split,'profile':profile,'terminal_positions':len(group),
                'collected_positions':len(collected),
                'artifact_links':sum(r['artifact_links'] for r in collected),
                'downloaded':sum(r['downloaded'] for r in collected),
                'download_failed':sum(r['download_failed'] for r in collected),
                'a5_observed_positions':len(a5),'a5_raw_classification_counts':dict(counts),
                'a5_raw_issue_count':sum(r['issue_count'] for r in a5)})
    return {'rows':rows,'aggregate':aggregate,
        'limitations':['All still-exposed artifact versions are counted; no content-based defect deduplication.',
            'A5 uses the existing mainline CLI. Its flags and unmatched claims are observations, not independent material-defect decisions.',
            'The assistant message creation timestamp is not a measured first correct or first usable financial delivery; that latency remains unknown.',
            'Elapsed times are non-isolated: participant chains and authorized ingestion may overlap.',
            'Successful download or sandbox execution does not establish financial correctness.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('study');args=parser.parse_args()
    study=Path(args.study).resolve()
    result=observe(study)
    (study/'delivery-observations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'terminal_positions':len(result['rows']),
        'collected_positions':sum(g['collected_positions'] for g in result['aggregate']),
        'a5_observed_positions':sum(g['a5_observed_positions'] for g in result['aggregate']),
        'download_failed':sum(g['download_failed'] for g in result['aggregate'])}))

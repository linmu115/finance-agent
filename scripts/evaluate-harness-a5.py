"""Historical evaluator, deliberately separate from the answer-blind A5 scanner.

Known-defect locations and human false-positive explanations live here / in the
review notes. They are never provided to scan_delivery or a participant model.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
C='pi-cowork-acceptance-20261006';G='pi-finance-generalization-20261006';P='pi-cowork-postfix-20261007'


def location(study,label,q):
    return (study,label,q['file'],q['where'],q['line'],q.get('column',q.get('normalizedColumn')),q['value'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=Path)
    p.add_argument('--replay',type=Path,default=ROOT/'.tmp/charts-consistency/a5')
    p.add_argument('--output',type=Path,default=ROOT/'docs/evidence/n2-charts-consistency')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    summary=json.loads((a.replay/'summary.json').read_text('utf8'))
    runs={(r['study'],r['label']):json.loads((a.replay/r['result']).read_text('utf8')) for r in summary}
    # Finite adjudicated target set: 47 bad occurrences in seven named defects.
    targets=[
      ('C2_forecast_x10',C,'C2',12,lambda q:q['value'] in ('240.2','34.78','324.2','46.18','391.0','54.61') and q['unit']==['money','CNY','100000000']),
      ('D2_csv_RMB_bn_x10',C,'D2',22,lambda q:q['file'].endswith('.csv') and q['unit']==['money','CNY','1000000000']),
      ('E2_sensitivity_wrong_cell',C,'E2',1,lambda q:q['file']=='answer.md' and q['line']==17 and q['value']=='12.07'),
      ('C1_margin_7_74',C,'C1',1,lambda q:q['file']=='answer.md' and q['value']=='-7.74'),
      ('F2_EPS_2024',C,'F2',5,lambda q:q['metric']=='eps' and q.get('period')=='2024' and q['value']=='0.83'),
      ('F2_gap_1_3_vs_6_8',C,'F2',3,lambda q:q['value']=='1.3' and q['unit'][0]=='money'),
      ('prior_C2_csv_x100',G,'C2',3,lambda q:q['file'].endswith('.csv') and q['value'] in ('347.8','461.8','546.1') and q['unit']==['money','CNY','100000000']),
    ]
    recall=[]
    for name,study,label,total,predicate in targets:
        found=[(i,c) for i,c in enumerate(runs[study,label]['checks']) if predicate(c['claim'])]
        detected=sum(c['issue'] for i,c in found)
        recall.append({'defect':name,'study':study,'label':label,'expected_occurrences':total,'extracted':len(found),
                       'detected':detected,'recall':detected/total,
                       'checks':[{'index':i,'file':c['claim']['file'],'line':c['claim']['line'],'value':c['claim']['value'],
                                  'classification':c['classification'],'issue':c['issue']} for i,c in found]})
    # Only cases explicitly passed for numerical core and currency, with no
    # known source/interpretation failure, form the strict correct-answer set.
    reviews=json.loads((a.source_root/f'data/evaluation/{C}/judge/reviews.json').read_text('utf8'))['cases']
    correct=[(C,label) for label,r in reviews.items() if all(r.get(k)=='pass' for k in ('financialCore','currencyAndScale','sourceAndInterpretation'))]
    for path in sorted((a.source_root/f'data/evaluation/{G}/judge').glob('*-review.json')):
        r=json.loads(path.read_text('utf8'))
        if r['numerics']['status']=='pass' and not r['materialNumericalError']:correct.append((G,r['label']))
    postfix=json.loads((a.source_root/f'data/evaluation/{P}/judge/review.json').read_text('utf8'))
    if postfix['financialCore']=='pass' and postfix['currencyAndScale']=='pass':correct.append((P,'G1'))
    notes=json.loads((a.output/'a5-review-notes.json').read_text('utf8'))
    notes={location(n['study'],n['label'],n):n['reason'] for n in notes}
    false_positives=[];correct_counts=[];unreviewed=[]
    for study,label in correct:
        run=runs[study,label];count=0
        for i,check in enumerate(run['checks']):
            if not check['issue']:continue
            q=check['claim'];reason=notes.get(location(study,label,q))
            if reason is None:unreviewed.append((study,label,i,q));continue
            false_positives.append({'study':study,'label':label,'check_index':i,'claim':q,
                                    'classification':check['classification'],'reason':reason});count+=1
        correct_counts.append({'study':study,'label':label,'extracted_quantities':len(run['checks']),'false_positives':count})
    if unreviewed:raise ValueError('Unreviewed correct-case alerts: '+json.dumps(unreviewed,ensure_ascii=False))
    dest=a.output/'a5-runs';dest.mkdir(exist_ok=True)
    cases=[]
    for (study,label),run in runs.items():
        path=dest/f'{study}-{label}.json';path.write_text(json.dumps(run,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8',newline='\n')
        cases.append({'study':study,'label':label,'counts':run['counts'],'issues':run['issue_count'],
                      'references':run['reference_counts'],'artifact':str(path.relative_to(a.output)).replace('\\','/')})
    counts=Counter()
    for run in runs.values():counts.update(run['counts'])
    total_correct=sum(c['extracted_quantities'] for c in correct_counts)
    result={'schema_version':1,'mode':'observation_only','feedback_enabled':False,'llm_calls':0,
            'replayed_cases':len(runs),'counts':dict(counts),'known_defect_groups_detected':sum(x['detected']>0 for x in recall),
            'known_defect_occurrences':sum(x['expected_occurrences'] for x in recall),'detected_occurrences':sum(x['detected'] for x in recall),
            'known_defect_recall':recall,'correct_case_count':len(correct),'correct_case_quantities':total_correct,
            'false_positive_count':len(false_positives),'false_positive_share_of_extracted_correct_quantities':len(false_positives)/total_correct,
            'correct_cases':correct_counts,'false_positives':false_positives,'cases':cases,
            'limits':['47 occurrences cover only the seven requested defect families, not every historical defect.',
                      'Correct-case alerts are false positives against the frozen historical numerical judgments; every alert has an individual diagnosis.',
                      'The denominator is extracted unit-bearing quantities, not a fully annotated true-negative universe.',
                      'No detection of causal correctness, interest-receipt direction, evidence completeness, or text without an identifiable unit.',
                      'Replay restores the last exposed successful revision of each table and only same-run source-tool responses; ambiguous metadata remains unknown.']}
    (a.output/'a5-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({k:result[k] for k in ('replayed_cases','known_defect_groups_detected','known_defect_occurrences','detected_occurrences','correct_case_count','correct_case_quantities','false_positive_count','false_positive_share_of_extracted_correct_quantities')},ensure_ascii=False))


if __name__=='__main__':main()

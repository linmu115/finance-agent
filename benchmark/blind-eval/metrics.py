"""Offline usage, rubric stability, numeric comparisons and conservative claim gate."""
from __future__ import annotations
import argparse,csv,io,json,math,statistics
from pathlib import Path
from blind import read,dump,output

DIMS=['reading','substantive','explanation','adjustments','anomalies','common']
LEGACY_DIMS=['substantive','consistency','depth','expression','traceability']
RUBRIC_VERSION='analyst-requirements-v2-20261008'
REQUIREMENTS=dict(zip(DIMS,['R1','R2','R3','R4','R5','C']))
UNITS={'CNY':('CNY',1),'CNY_million':('CNY',1e6),'CNY_100million':('CNY',1e8),'CNY_billion':('CNY',1e9),'HKD':('HKD',1),'HKD/share':('HKD/share',1),'CNY/share':('CNY/share',1),'ratio':('ratio',1),'%':('ratio',.01),'pp':('pp',1),'days':('days',1)}

def compare_claim(expected, actual):
    if actual is None or actual.get('value') is None:return {'status':'missing','expected':expected}
    aunit=UNITS[actual['unit']];eunit=UNITS[expected['unit']]
    if aunit[0]!=eunit[0]:return {'status':'unit_or_currency_mismatch','actual':actual,'expected':expected}
    value=float(actual['value'])*aunit[1]/eunit[1];target=float(expected['value'])
    error=value-target;tol=expected.get('absolute_tolerance',0)
    status='exact' if error==0 else 'rounding_consistent' if abs(error)<=tol+1e-8 else 'numeric_mismatch'
    ratio=value/target if target else None
    if status=='numeric_mismatch' and ratio and ratio>0 and math.isclose(math.log10(ratio),round(math.log10(ratio)),abs_tol=.01):status='scale_mismatch'
    if actual.get('direction') is not None and expected.get('direction') is not None and actual['direction']!=expected['direction']:status='direction_mismatch'
    if expected.get('accepted_source_pages') and not actual.get('source_page'):source_status='missing'
    elif expected.get('accepted_source_pages') and actual['source_page'] not in expected['accepted_source_pages']:source_status='mismatch'
    else:source_status='not_checked' if not expected.get('accepted_source_pages') else 'matched'
    return {'status':status,'error_in_reference_unit':error,'source_status':source_status,'actual':actual,'expected':expected}

def numeric(manifest,folder):
    """Reference values freeze before answers; selectors locate cells in variable-format outputs."""
    checks=[]
    for spec in manifest['checks']:
        p=Path(folder)/spec['file'];actual=None
        if p.exists():
            if spec['format']=='csv':
                rows=list(csv.DictReader(io.StringIO(p.read_text('utf-8-sig'))))
                matching=[r for r in rows if all(r.get(k)==v for k,v in spec['row'].items())]
                if len(matching)>1:raise ValueError('Ambiguous CSV row '+spec['key'])
                if matching and matching[0].get(spec['column'],'')!='':
                    unit=spec['unit_map'][matching[0][spec['unit_column']]] if 'unit_column' in spec else spec['unit']
                    actual={'value':matching[0][spec['column']],'unit':unit}
                    if 'unit_column' in spec:actual['raw_unit']=matching[0][spec['unit_column']]
            elif spec['format']=='json':
                obj=read(p)
                for key in spec['path']:obj=obj[key]
                actual={'value':obj,'unit':spec['unit']}
            else:raise ValueError('Only deterministic CSV/JSON selectors are supported')
            if actual is not None:
                for key in ['source_page','direction']:
                    if key in spec:actual[key]=spec[key]
        checks.append({'key':spec['key'],'file':spec['file'],**compare_claim(spec['expected'],actual)})
    return {'checks':checks,'limitations':'CSV/JSON selectors only; prose/figure/semantic source claims need A5 and independent review. Extracted unit/source labels must be grounded in the submitted file, not guessed.'}

def summarize(source):
    source=Path(source);s=read(source/'experiment.json');rows=[]
    for r in s['runs']:
        file=source/(r['label']+'-run.json');run=read(file) if file.exists() else {};u=run.get('usage') or r.get('usage')
        audit=source/(r['label']+'-audit.jsonl');events=[json.loads(line) for line in audit.read_text('utf-8-sig').splitlines() if line.strip()] if audit.exists() else None
        requests=[e['data'] for e in events or [] if e['type']=='model_request'];seq=[{'at':e.get('at'),'name':e['data'].get('name')} for e in events or [] if e['type']=='tool_request']
        from datetime import datetime
        started=run.get('createdAt',r.get('requestedAt'));finished=run.get('finishedAt',r.get('completedAt'))
        elapsed=(datetime.fromisoformat(finished.replace('Z','+00:00'))-datetime.fromisoformat(started.replace('Z','+00:00'))).total_seconds() if started and finished else None
        rows.append({'label':r['label'],'profile':r['profile'],'task':r.get('taskId',r['label'][1:]),'status':run.get('status',r['status']),'usage':u,'elapsed_seconds':elapsed,'request_count':len(requests) if events is not None else None,'request_policy':[{'phase':x.get('phase'),'model':x.get('model'),'effort':x.get('sentReasoningEffort',x.get('reasoningEffort'))} for x in requests],'tool_sequence':seq,'errors':[e for e in events or [] if e['type'] in ['tool_error','model_error','model_retry','error']],'provider_billed_cost':None})
    grouped=[]
    for profile,task in sorted({(r['profile'],r['task']) for r in rows}):
        group=[r for r in rows if (r['profile'],r['task'])==(profile,task)]
        summary={'profile':profile,'task':task,'attempts':len(group),'completed':sum(r['status']=='completed' for r in group),'provider_billed_cost':None,'monetary_cost_median':None,'monetary_cost_range':None}
        for k in ['input','output','uncachedInput','calls','unknownCalls']:
            known=[r['usage'][k] for r in group if r['usage'] is not None and r['usage'].get(k) is not None]
            summary[k]={'known_sum':sum(known) if known else None,'missing_attempts':len(group)-len(known),'median':statistics.median(known) if known else None,'range':[min(known),max(known)] if known else None}
        grouped.append(summary)
    return {'rows':rows,'by_task_and_group':grouped,'preparation':s.get('preparation'),'price_note':'Provider billing rate unverified; catalog estimates retained in raw usage but not used as a bill. Known sums are lower bounds when unknown calls exist. Repeated attempts remain included.','advantage_claim':False,'claim_blockers':['No approved frozen held-out results','Provider monetary cost unknown']}

def stability(folder):
    folder=Path(folder);decoded=[]
    reference=read(folder/'reference/reference.json')
    version=reference.get('rubric_version','legacy-v1')
    if version not in ['legacy-v1',RUBRIC_VERSION]:raise ValueError('Unknown rubric version')
    dims=DIMS if version==RUBRIC_VERSION else LEGACY_DIMS
    case_map=read(folder/'private-map.json')['cases']
    tasks={m['case_id']:m['task'] for m in case_map}
    for rd in ['round1','round2']:
        mp=read(folder/f'private-{rd}-map.json');review=read(folder/rd/'review.json')
        meta=review['metadata']
        if meta['model']!='gpt-6-astra' or meta['reasoning_effort']!='high':raise ValueError('Unexpected reviewer model/effort')
        if version==RUBRIC_VERSION and meta.get('rubric_version')!=version:raise ValueError('Reviewer rubric version mismatch')
        rs=review['reviews']
        if {r['case_id'] for r in rs}!=set(mp) or len(rs)!=len(mp):raise ValueError('Missing/duplicate case reviews')
        for r in rs:
            if set(r['scores'])!=set(dims):raise ValueError('Invalid score dimensions')
            for k,v in r['scores'].items():
                untested=version==RUBRIC_VERSION and reference['task_requirements'][tasks[mp[r['case_id']]]][REQUIREMENTS[k]]['coverage']=='not_tested'
                if untested:
                    if v is not None:raise ValueError('Untested dimension must be null')
                elif type(v)!=int or not 0<=v<=4:raise ValueError('Invalid applicable score')
            if r['material_defects'] and r['scores']['substantive']>1:raise ValueError('Material defect score exceeds rubric cap')
        decoded.append({mp[r['case_id']]:r for r in rs})
    rows=[];diffs=[]
    for m in case_map:
        a,b=[x[m['case_id']] for x in decoded];delta={k:None if a['scores'][k] is None else b['scores'][k]-a['scores'][k] for k in dims};diffs.extend(abs(x) for x in delta.values() if x is not None)
        rows.append({'case_id':m['case_id'],'original_label':m['label'],'profile':m['profile'],'task':m['task'],'round1_scores':a['scores'],'round2_scores':b['scores'],'score_delta':delta,'material_presence_agrees':bool(a['material_defects'])==bool(b['material_defects']),'round1_material':a['material_defects'],'round2_material':b['material_defects'],'unreviewed':[a.get('unreviewed'),b.get('unreviewed')]})
    avg=statistics.mean(diffs)
    return {'purpose':'workflow_rehearsal_not_score','rubric_version':version,'scored_dimension_pairs':len(diffs),'cases':rows,'mean_absolute_score_difference':avg,'max_dimension_difference':max(diffs),'material_presence_agreement':sum(r['material_presence_agrees'] for r in rows),'stable_by_preregistered_threshold':avg<=.5 and max(diffs)<=1 and all(r['material_presence_agrees'] for r in rows),'note':'N/A is excluded, not zero/full marks. Defect-level agreement and comparison to historical review are separately adjudicated; aggregate agreement does not replace them.'}

def aggregate_scores(rows):
    """Rows must carry split/type/profile, scores, defect list and verified per-attempt cost."""
    result=[]
    for key in sorted({(r['split'],r['task_type'],r['profile']) for r in rows}):
        group=[r for r in rows if (r['split'],r['task_type'],r['profile'])==key];costs=[r['verified_cost'] for r in group if r.get('verified_cost') is not None]
        values={k:[r['scores'][k] for r in group if r['scores'][k] is not None] for k in DIMS}
        result.append({'split':key[0],'task_type':key[1],'profile':key[2],'n':len(group),'material_defects':sum(len(r['material_defects']) for r in group),'mean_scores':{k:statistics.mean(v) if v else None for k,v in values.items()},'scored_counts':{k:len(v) for k,v in values.items()},'known_cost_median':statistics.median(costs) if costs else None,'known_cost_range':[min(costs),max(costs)] if costs else None,'unknown_cost_count':len(group)-len(costs)})
    eligible=True;reasons=[]
    for split in ['development','heldout']:
        groups={p:[r for r in rows if r['split']==split and r['profile']==p] for p in ['prepared','financial']}
        a,b=groups['prepared'],groups['financial']
        if not a or not b:eligible=False;reasons.append(split+': incomplete paired split');continue
        keys=lambda xs:sorted((r['task_id'],r['repeat']) for r in xs)
        if keys(a)!=keys(b):eligible=False;reasons.append(split+': unmatched tasks/repeats')
        for task_id in {r['task_id'] for r in a+b}:
            if any(len({r['repeat'] for r in xs if r['task_id']==task_id})<2 for xs in [a,b]):eligible=False;reasons.append(split+': fewer than two repeats')
        if any(r.get('verified_cost') is None or r.get('unknown_usage_calls',0) or r.get('status')!='completed' for r in a+b):eligible=False;reasons.append(split+': cost/usage/completion incomplete');continue
        defects=lambda xs:sum(len(r['material_defects']) for r in xs)
        professional=[]
        for dim in ['explanation','adjustments','anomalies']:
            pa={(r['task_id'],r['repeat']):r['scores'][dim] for r in a if r['scores'][dim] is not None}
            pb={(r['task_id'],r['repeat']):r['scores'][dim] for r in b if r['scores'][dim] is not None}
            if pa.keys()!=pb.keys():eligible=False;reasons.append(split+': mismatched applicability '+dim)
            elif pa:professional.append((statistics.mean(pa.values()),statistics.mean(pb.values())))
        cost=lambda xs:statistics.median(r['verified_cost'] for r in xs)
        if not(defects(b)<=defects(a) and professional and all(y>=x for x,y in professional) and any(y>x for x,y in professional) and cost(b)<=cost(a)):eligible=False;reasons.append(split+': quality/professional-dimensions/cost criterion not met')
    return {'rubric_version':RUBRIC_VERSION,'groups':result,'may_claim_advantage':eligible,'blockers':reasons,'significance':'Not estimated; small repeat counts support directions only. Supporting coverage does not establish the full original capability.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['summarize','stability','numeric','aggregate']);p.add_argument('source');p.add_argument('destination');p.add_argument('--files');a=p.parse_args()
    if a.command=='summarize':result=summarize(a.source)
    elif a.command=='stability':result=stability(a.source)
    elif a.command=='numeric':result=numeric(read(a.source),a.files)
    else:result=aggregate_scores(read(a.source)['rows'])
    dump(output(a.destination),result);print(json.dumps({'written':a.destination},ensure_ascii=False))

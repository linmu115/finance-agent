"""Protocol-defined observational usage bounds, with preparation/incident separation.

Never replaces unknown raw usage. Upper values are the preregistered sensitivity
scenario, not guaranteed physical maxima or provider invoices.
"""
import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def requests(study, row):
    path = study / (row['label']+'-audit.jsonl')
    if not path.exists():
        return []
    ordered = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        event = json.loads(line)
        data = event.get('data', {})
        if event['type'] not in {'model_request','model_usage'} or not data.get('requestId'):
            continue
        value = ordered.setdefault(data['requestId'], {'request_id':data['requestId'], 'known':False})
        if event['type'] == 'model_request':
            value['model'] = data.get('model');value['phase'] = data.get('usagePhase',data.get('phase'))
        elif not value['known']:
            value['known'] = data.get('usageKnown') is not False and isinstance(data.get('usage'),dict)
            value['raw_usage'] = data.get('usage')
            value['error_recorded'] = bool(data.get('error'))
    for value in ordered.values():
        raw = value.get('raw_usage') or {}
        if value['known']:
            value.update(input=sum(raw.get(k,0) or 0 for k in ['input','cacheRead','cacheWrite']),
                         uncached_input=raw.get('input'), cache_read=raw.get('cacheRead'),
                         cache_write=raw.get('cacheWrite'), output=raw.get('output'),
                         reasoning=raw.get('reasoning'), catalog_cost=(raw.get('cost')or{}).get('total'))
    return list(ordered.values())


def rates_from(request_rows):
    samples = defaultdict(list)
    for value in request_rows:
        if not value['known']:
            continue
        raw = value['raw_usage'];cost = raw.get('cost') or {}
        for field in ['input','output','cacheRead','cacheWrite']:
            if isinstance(raw.get(field), (int,float)) and raw[field]>0 and isinstance(cost.get(field),(int,float)):
                samples[field].append(cost[field]/raw[field]*1_000_000)
    result = {}
    for field in ['input','output','cacheRead','cacheWrite']:
        values = samples[field]
        result[field] = values[0] if values and all(math.isclose(v,values[0],rel_tol=1e-8,abs_tol=1e-12) for v in values) else None
    return result


def rates_for_input(schedule, input_tokens):
    rates = schedule
    threshold = -1
    for tier in schedule.get('tiers', []):
        if input_tokens > tier['inputTokensAbove'] > threshold:
            rates = tier
            threshold = tier['inputTokensAbove']
    return rates


def verify_catalog_schedule(request_rows, schedule):
    """Reconcile the frozen Pi price function against recorded costs, not invoices."""
    tiers = defaultdict(int)
    for value in request_rows:
        if not value['known']:
            continue
        raw = value['raw_usage']
        rates = rates_for_input(schedule, value['input'])
        expected = {field:rates[field]*(raw.get(field, 0) or 0)/1e6
                    for field in ['input','output','cacheRead']}
        long_write = raw.get('cacheWrite1h', 0) or 0
        expected['cacheWrite'] = (rates['cacheWrite']*((raw.get('cacheWrite', 0) or 0)-long_write)
                                 + rates['input']*2*long_write)/1e6
        expected['total'] = sum(expected.values())
        cost = raw.get('cost') or {}
        for field, amount in expected.items():
            if not isinstance(cost.get(field), (int,float)) or not math.isclose(cost[field], amount, abs_tol=1e-10):
                raise ValueError('Recorded catalog cost differs from sealed price function: '+value['request_id']+' '+field)
        tiers[str(rates.get('inputTokensAbove', 'base'))] += 1
    return dict(tiers)


def bounds_for(known, unknown_count, peers, schedule):
    lower_input=sum(v['input'] for v in known)
    lower_output=sum(v['output'] for v in known)
    catalog=sum(v['catalog_cost'] for v in known) if all(v.get('catalog_cost') is not None for v in known) else None
    max_input=max((v['input'] for v in peers),default=None)
    max_output=max((v['output'] for v in peers),default=None)
    upper_input=lower_input+unknown_count*max_input if max_input is not None else (lower_input if not unknown_count else None)
    upper_output=lower_output+unknown_count*max_output if max_output is not None else (lower_output if not unknown_count else None)
    upper_cost=catalog
    if unknown_count:
        rates=rates_for_input(schedule,max_input) if max_input is not None else {}
        upper_cost=(catalog+unknown_count*(max_input*rates['input']+max_output*rates['output'])/1e6
                    if catalog is not None and max_input is not None and max_output is not None and rates.get('input') is not None and rates.get('output') is not None else None)
    return {'input_lower':lower_input,'input_upper_observed_scenario':upper_input,
            'output_lower':lower_output,'output_upper_observed_scenario':upper_output,
            'catalog_cost_lower':catalog,'catalog_cost_upper_observed_scenario':upper_cost,
            'unknown_calls':unknown_count,'max_peer_request_input':max_input,'max_peer_request_output':max_output}


def summarize(study):
    state=read(study/'experiment.json');all_requests=[];records=[];peers=defaultdict(list)
    for row in state['runs']:
        if row['status'] not in {'completed','failed','cancelled','blocked_dependency'}:
            continue
        calls=requests(study,row)
        known=[v for v in calls if v['known']]
        peers[(row['profile'],row['taskId'])].extend(known);all_requests.extend(calls)
        records.append((row,calls))
    rates=rates_from(all_requests)
    pricing=read(study/'catalog-pricing.json')
    schedule=pricing['cost']
    if any(v.get('model') != pricing['model'] for v in all_requests):
        raise ValueError('Request model differs from the sealed price schedule')
    tier_counts=verify_catalog_schedule(all_requests,schedule)
    rows=[]
    for row,calls in records:
        known=[v for v in calls if v['known']];unknown=sum(not v['known'] for v in calls)
        raw=read(study/(row['label']+'-run.json')) if (study/(row['label']+'-run.json')).exists() else {}
        host=raw.get('usage') or row.get('usage')
        if host and host.get('calls') != len(calls):
            raise ValueError('Request count differs from host audit: '+row['label'])
        if row.get('runId') and not calls:
            raise ValueError('Submitted terminal run has no captured request audit: '+row['label'])
        bounds=bounds_for(known,unknown,peers[(row['profile'],row['taskId'])],schedule)
        if host:
            assert host['unknownCalls']==unknown,row['label']
            for field,key in [('input','input_lower'),('output','output_lower')]:
                if host[field]!=bounds[key]:raise ValueError('Known usage mismatch: '+row['label']+' '+field)
        rows.append({'label':row['label'],'task':row['taskId'],'split':row['split'],'profile':row['profile'],'repeat':row['repeat'],
                     'status':row['status'],'request_count':len(calls),**bounds,'request_usage':calls,
                     'host_catalog_cost':host.get('costUsd') if host else None,
                     'host_and_raw_catalog_agree':None if not host or host.get('costUsd') is None or bounds['catalog_cost_lower'] is None else math.isclose(host['costUsd'],bounds['catalog_cost_lower'],abs_tol=1e-10)})
    return {'scope':'participant attempts only; void initial environment check excluded by explicit authorization',
            'bound_policy':'Lower = known subtotal. Each unknown uses observed maxima within the same formal batch, arm and task; no peer observations leaves upper unknown.',
            'cost_upper_cache_assumption':'Unknown input is all uncached. Apply the sealed common Pi price function, including its input-length tier, to the same-arm/task observed maximum input and output. This is a sensitivity estimate, not invoiced cost.',
            'rates_per_million_usd_observed_catalog':rates,
            'catalog_price_function':pricing,'catalog_tier_request_counts':tier_counts,
            'provider_billed_cost':None,'rows':rows,
            'incident_usage':[x['usage'] for x in state.get('prestartIncidents',[])],
            'supplementary_metric_definition':'For each review pass separately: total known participant input (including failed attempts) divided by completed, material-defect-free case count; undefined if denominator is zero. Not an E4 replacement.',
            'reasoning_tokens':'Reported separately; already included in output, never added twice.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('study');parser.add_argument('output');args=parser.parse_args()
    study=Path(args.study).resolve();out=Path(args.output).resolve()
    if not out.is_relative_to(study):raise ValueError('Usage output must stay in the private study')
    result=summarize(study);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'terminal_positions':len(result['rows']),'unknown_calls':sum(r['unknown_calls'] for r in result['rows']),'incident_attempts':len(result['incident_usage'])}))

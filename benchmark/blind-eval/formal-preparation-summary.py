"""Summarize already sealed preparation ledgers, separate from formal analysis."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'data/evaluation/blind-eval-F21-formal-private-20261009'
PUBLIC = ROOT/'data/evaluation/blind-eval-F21-formal-20261009'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def receipt(path):
    return {'path':path.relative_to(ROOT).as_posix(),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


rows = []
sources = []
for key in ['yili', 'haier']:
    path = BASE/f'{key}-freeze/N3-cumulative-usage.json'
    ledger = read(path)
    segments = ledger['segments']
    assert len({s['run_id'] for s in segments}) == len(segments)
    total = ledger['cumulative_known_usage']
    for field in ['calls','input','output','reasoning','unknownCalls']:
        assert sum(s['usage'][field] for s in segments) == total[field]
    prices = [s['usage'].get('costUsd') for s in segments]
    rows.append({'material':key+'_annual', 'scope':ledger['scope'],
        'segments':len(segments), 'known_usage':total,
        'known_catalog_cost_usd':sum(v for v in prices if v is not None),
        'segments_without_cost':sum(v is None for v in prices),
        'invoice_cost':None, 'includes_prior_versions_and_repairs':True})
    sources.append(receipt(path))
path = ROOT/'data/evaluation/blind-eval-v3-heldout-private-20261008/completed-F21-20261009/preparation-usage-summary.json'
ledger = read(path)
total = {k:v['known_sum'] for k,v in ledger['totals'].items()}
rows.append({'material':'BH_annual', 'scope':'All retained ingestion segments before the formal data freeze.',
    'segments':len(ledger['segments']),
    'known_usage':{k:v for k,v in total.items() if k!='costUsd'},
    'known_catalog_cost_usd':total['costUsd'],
    'segments_without_cost':ledger['totals']['costUsd']['missing_segments'],
    'invoice_cost':None, 'includes_prior_versions_and_repairs':True})
sources.append(receipt(path))
result = {'at':datetime.now(timezone.utc).isoformat(), 'scope':'Preparation, excluded from all E4 analysis comparisons.',
    'annual_report_ledgers':rows, 'sources':sources,
    'other_preparation':'Carote historical preparation, Yili Q3 and broker reports are reused assets; their complete preparation costs are not consolidated here and remain unknown, not zero.',
    'shared_N3_preflight':{'calls':1, 'input':307, 'output':5, 'reasoning':0,
        'note':'Same shared probe referenced by both annual ledgers; disclosed once, not added twice.'},
    'judging':{'threads':18, 'model':'gpt-6-astra', 'reasoning_effort':'high',
        'tokens':None, 'actual_billed_cost':None},
    'notes':['Cumulative and current-segment totals are not added together.',
        'Prior preparation failures and resumes remain in these historical totals.',
        'Known catalog charges are not invoices; unknown requests remain unknown.',
        'Preparation is shared infrastructure and is not assigned afresh to each answer.',
        'Reasoning is included in output, not added again.',
        'Connectivity probes and the excluded initial environment incident have separate raw ledgers.']}
(BASE/'preparation-cost-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
public = {k:v for k,v in result.items() if k!='sources'}
(PUBLIC/'preparation-cost-summary.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print({'annual_ledgers':len(rows),'judging_usage':'unknown','analysis_cost_included':False})

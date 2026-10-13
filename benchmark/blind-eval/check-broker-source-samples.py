"""Match evaluator-only PDF spot checks to the current saved research records."""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/evaluation/blind-eval-broker-resume-20261008'
reference = json.loads((OUT/'source-review/sample-reference.json').read_text('utf8'))
keys = {s['key'] for s in reference['samples']}
records = {key:json.loads((OUT/key/'research-records.json').read_text('utf8')) for key in keys}
checks = []
for sample in reference['samples']:
    candidates = []
    for record in records[sample['key']]:
        source = record.get('source', {})
        if record['record_type'] != 'observation' or source.get('page') != sample['page']:
            continue
        if sample['row'] is not None:
            if not (source.get('table_id', '').endswith(':t'+str(sample['table_index'])) and source.get('row') == sample['row'] and source.get('column') == sample['column']):
                continue
        elif record.get('metric') != sample['metric'] or record.get('period') != str(sample['year'])+'-FY':
            continue
        candidates.append(record)
    matches = []
    for r in candidates:
        fields = {'numeric_value':Decimal(str(r['value']))==Decimal(sample['value']), 'period':r.get('period')==str(sample['year'])+'-FY', 'entity':r.get('entity',{}).get('name')==sample['entity'], 'actual_or_forecast':r.get('data_kind')==sample['data_kind'], 'metric_name':r.get('metric')==sample['metric'], 'currency':r.get('currency')==sample['currency'] if sample['currency'] else None}
        matches.append({'record_id':r['record_id'], 'checks':fields, 'stored':{k:r.get(k) for k in ['metric','label','period','value','currency','scope','data_kind','entity','quality','dimensions']}})
    if not matches:
        status='missing_structured_record'
    elif all(any(m['checks'][field] is True for m in matches) for field in ['numeric_value','period','entity','actual_or_forecast','metric_name']) and (sample['currency'] is None or any(m['checks']['currency'] is True for m in matches)):
        status='checked_fields_match_currency_not_scored' if sample['currency'] is None else 'checked_fields_match'
    else:
        status='field_difference_needs_review'
    checks.append({'reference':sample,'status':status,'matches':matches})
summary = {key:dict(Counter(c['status'] for c in checks if c['reference']['key']==key)) for key in sorted(keys)}
report={'method':reference['method'], 'scope':'60 selected numeric points, not a complete semantic review; missing source rows counted as missing, not zero. Exact metric-name differences require semantic review, not automatic financial-error verdict.', 'summary':summary, 'checks':checks, 'qualitative_checks':reference['qualitative_checks']}
(OUT/'source-review/spot-check-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(summary,ensure_ascii=False))

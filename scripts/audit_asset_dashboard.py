"""Independent read-only comparison with visually inspected original PDF tables."""
import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/acceptance/asset-dashboard'
manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
db = sqlite3.connect((ROOT/'data/active/finance.sqlite').resolve().as_uri()+'?mode=ro', uri=True)
db.row_factory = sqlite3.Row
facts = [dict(r) for r in db.execute('SELECT * FROM current_financial_facts WHERE project_id=?', (manifest['project']['id'],))]
records = [dict(r) for r in db.execute('SELECT * FROM research_records WHERE project_id=? AND is_current=1', (manifest['project']['id'],))]
for f in facts:
    f['source'] = json.loads(f['source_json'])
for r in records:
    r['source'] = json.loads(r['source_json'])
    r['payload'] = json.loads(r['record_json'])

# Physical PDF page numbers; units on financial pages 28-32 are RMB'000.
financial = [
    (28,'Revenue','2025-H1','120392000'),(28,'Revenue','2024-H1','181011000'),
    (28,'Cost of sales','2025-H1','-111281000'),(28,'Cost of sales','2024-H1','-166434000'),
    (28,'Gross profit','2025-H1','9111000'),(28,'Gross profit','2024-H1','14577000'),
    (28,'Operating loss','2025-H1','-18170000'),(28,'Operating loss','2024-H1','-32320000'),
    (28,'Finance costs net','2025-H1','-3914000'),(28,'Finance costs net','2024-H1','-6801000'),
    (28,'FVTPL gain','2025-H1','63015000'),(28,'Profit before tax','2025-H1','40931000'),
    (28,'Profit for period','2025-H1','41098000'),(28,'Profit for period','2024-H1','-38635000'),
    (28,'Owners profit','2025-H1','43186000'),(28,'Owners profit','2024-H1','-36040000'),
    (29,'Total assets','2025-06-30','343872000'),(29,'Total assets','2024-12-31','298852000'),
    (29,'Cash','2025-06-30','25723000'),(29,'Cash','2024-12-31','16399000'),
    (29,'Trade receivables','2025-06-30','80662000'),(29,'Trade receivables','2024-12-31','90660000'),
    (29,'Total equity','2025-06-30','117634000'),(29,'Total equity','2024-12-31','42881000'),
    (30,'Total liabilities','2025-06-30','226238000'),(30,'Total liabilities','2024-12-31','255971000'),
    (32,'Operating cash flow','2025-H1','-30650000'),(32,'Operating cash flow','2024-H1','-32104000'),
    (32,'Investing cash flow','2025-H1','-6796000'),(32,'Investing cash flow','2024-H1','-5308000'),
    (32,'Financing cash flow','2025-H1','47079000'),(32,'Financing cash flow','2024-H1','-7228000'),
    (32,'PPE capex','2025-H1','-670000'),(32,'PPE capex','2024-H1','-1300000'),
]

def period_matches(actual, expected):
    if '-H1' in expected:
        year = expected[:4]
        return actual in (expected,year+'-6M',year+'-01-01/'+year+'-06-30')
    return actual==expected

checks=[]
financial_metrics = {
    'Revenue':'revenue','Cost of sales':'cost_of_sales','Gross profit':'gross_profit','Operating loss':'operating_loss',
    'Finance costs net':'finance_costs_net','FVTPL gain':'fair_value_gains_on_financial_assets_at_fvtpl',
    'Profit before tax':'profit_before_income_tax','Profit for period':'net_profit',
    'Owners profit':'profit_attributable_to_owners_of_the_company','Total assets':'total_assets',
    'Cash':'cash_and_cash_equivalents','Trade receivables':'trade_receivables','Total equity':'total_equity',
    'Total liabilities':'total_liabilities','Operating cash flow':'net_cash_used_in_operating_activities',
    'Investing cash flow':'net_cash_used_in_investing_activities','Financing cash flow':'net_cash_generated_from_financing_activities',
    'PPE capex':'payment_for_property_and_equipment',
}
financial_doc = next(t['documentId'] for t in manifest['tasks'] if t['kind']=='financial')
research_doc = next(t['documentId'] for t in manifest['tasks'] if t['kind']=='research')
for page,label,period,value in financial:
    found=[f for f in facts if f['document_id']==financial_doc and f['source'].get('page')==page and f['metric']==financial_metrics[label] and Decimal(f['value'])==Decimal(value) and period_matches(f['period'],period) and f['currency']=='CNY' and f['scope']=='consolidated_IFRS']
    checks.append({'source':'financial','page':page,'label':label,'period':period,'expected_value':value,'ok':bool(found),
                   'matches':[{'id':f['fact_id'],'metric':f['metric'],'label':f['source'].get('normalization',{}).get('label'),'scope':f['scope']} for f in found]})

# Independently transcribed from the Guosen report cover, not from the application's parsed tables.
for metric,values in [('revenue',['126179','115780','119338','122498','125438']),('net_profit',['10429','8453','11309','12222','13152']),('eps',['1.64','1.33','1.78','1.92','2.07'])]:
    # The cover abbreviates profit/EPS; the detailed page 36 confirms parent profit.
    source_metrics={'revenue':{'revenue'},'net_profit':{'net_profit_parent'},'eps':{'eps_basic','eps'}}[metric]
    for year,value in zip(range(2023,2028),values):
        expected=Decimal(value)*(1 if metric=='eps' else 1000000)
        found=[r for r in records if r['document_id']==research_doc and r['source'].get('page')==1 and r['metric'] in source_metrics and Decimal(r['value'] or 'NaN')==expected and r['period'] in (str(year)+'-FY',str(year)) and r['data_kind']==('quoted_actual' if year<2025 else 'analyst_forecast') and r['published_at']=='2025-07-16' and r['publisher']=='国信证券']
        checks.append({'source':'research','page':1,'label':metric,'period':str(year),'expected_value':str(expected),'ok':bool(found),
                       'matches':[{'id':r['record_id'],'metric':r['metric'],'label':r['payload'].get('label'),'publisher':r['publisher']} for r in found]})

claims=[]
for r in records:
    if r['record_type']!='claim':continue
    source=r['source'];page=source.get('page');quote=source.get('quote') or r['payload'].get('source',{}).get('quote')
    raw=db.execute('SELECT text FROM pages WHERE document_id=? AND page=?',(r['document_id'],page)).fetchone()
    claims.append({'record_id':r['record_id'],'page':page,'ok':bool(raw and quote and quote in raw[0])})
research_docs=[t['documentId'] for t in manifest['tasks'] if t['kind']=='research']
leaked=[f['fact_id'] for f in facts if f['document_id'] in research_docs]
result={'counts':{'facts':len(facts),'research_records':len(records)},'pdf_anchors':checks,
        'anchors_passed':sum(c['ok'] for c in checks),'anchors_total':len(checks),'claim_quotes':claims,
        'claims_passed':sum(c['ok'] for c in claims),'claims_total':len(claims),'research_records_in_disclosures':leaked,
        'independent_metrics':{'revenue_yoy':str(Decimal(120392)/Decimal(181011)-1),'gross_margin_2025':str(Decimal(9111)/Decimal(120392)),
            'cfo_margin_2025':str(Decimal(-30650)/Decimal(120392)),'cash_profit_gap_2025':str(Decimal(-30650000)-Decimal(41098000)),
            'net_profit_less_fair_value_gain_pre_tax_only':str(Decimal(41098000)-Decimal(63015000))}}
(OUT/'quality-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('pdf_anchors','claim_quotes')},ensure_ascii=False,indent=2))

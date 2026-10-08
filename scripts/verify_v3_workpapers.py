"""Check the saved five-company replay; export compact, reviewable evidence."""
import argparse
from decimal import Decimal as D
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.replay_v3_workpapers import DOCS, KINDS, service_at, write
from service.financial_workpapers import Statement, load_facts, ALIASES

# Transcribed after opening the original Moutai 2024 PDF pages 63/64/67/68.
# These are acceptance expectations, never imported by product code.
MOUTAI = {
    'income': {
        'revenue': ('170899152276.34', '147693604994.14', 63),
        'cogs': ('13789482367.98', '11867273851.78', 63),
        'selling': ('5639300059.49', '4648613585.82', 63),
        'administrative': ('9315650060.38', '9729389252.31', 63),
        'research': ('218375472.87', '157371873.01', 63),
        'surcharges': ('26926161474.99', '22234175898.60', 63),
        'finance_costs': ('-1470219863.34', '-1789503701.48', 63),
        'other_income': ('21229466.81', '34644873.86', 63),
        'investment_income': ('9130340.37', '34025967.82', 63),
        'fair_value_gains': ('60980724.35', '3151962.50', 64),
        'credit_impairment': ('-23248436.03', '37871293.26', 64),
        'asset_disposal': ('388852.05', '-479736.97', 64),
        'operating_profit': ('119688579453.23', '103708655208.38', 64),
        'nonoperating_income': ('70936575.97', '86779655.95', 64),
        'nonoperating_expenses': ('120937834.74', '132881174.52', 64),
        'profit_before_tax': ('119638578194.46', '103662553689.81', 64),
        'tax': ('30303850168.56', '26141077412.01', 64),
    },
    'profit_attribution': {
        'consolidated': ('89334728025.90', '77521476277.80', 64),
        'parent': ('86228146421.62', '74734071550.75', 64),
        'minority': ('3106581604.28', '2787404727.05', 64),
    },
    'bridge': {
        'cfo': ('92463692168.43', '66593247721.09', 67),
        'cfi': ('-1785202630.71', '-9724414015.16', 67),
        'cff': ('-71067506484.81', '-58889101991.94', 67),
        'cash_fx': ('-1082747.55', '1718255.65', 68),
        'cash_begin': ('150360188952.47', '152378738982.83', 68),
        'end': ('169970089257.83', '150360188952.47', 68),
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--replay', type=Path, required=True)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--tokenizer-path', type=Path)
    args = ap.parse_args()
    if args.tokenizer_path: sys.path.insert(0, str(args.tokenizer_path.resolve()))
    import tiktoken
    encoding = tiktoken.get_encoding('o200k_base')
    def measure(value):
        text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        return {'utf8_bytes': len(text.encode('utf-8')), 'tokens': len(encoding.encode(text))}
    all_results, amounts, sizes = {}, {}, []
    for name in DOCS:
        result = {kind: json.loads((args.replay / name / (kind + '.json')).read_text('utf-8')) for kind in KINDS}
        assert all(r['status'] == 'ok' for r in result.values()), name
        all_results[name] = result
        data = result['analysis_pipeline']['data']; tables = data['numeric_tables']; context = data['context']
        for metric in context['key_metrics']:
            for q in metric['values'].values():
                table, row, column = q['ref'].split('.')
                assert any(r['key'] == row and column in r for r in tables[table]['rows']), q
        wire = []
        for kind in ('statement_analysis', 'variance_attribution', 'anomaly_signals'):
            r = result[kind]
            wire.append(r | {'data': {k: v for k, v in r['data'].items() if k not in ('report', 'numeric_tables')}})
        old_size = {'utf8_bytes': sum(measure(r)['utf8_bytes'] for r in wire), 'tokens': sum(measure(r)['tokens'] for r in wire)}
        small = measure(context)
        sizes.append({'company': name, 'encoding': 'o200k_base', 'compact_context': small,
                      'three_standalone_model_responses': old_size, 'complete_pipeline_response': measure(result['analysis_pipeline']),
                      'context_token_reduction_percent': round((1 - small['tokens'] / old_size['tokens']) * 100, 2)})
        write(args.out / name / 'context.json', context)
        write(args.out / name / 'missing.json', tables['pipeline_gaps'])
        amounts[name] = {key: tables[key] for key in ('statement_income', 'statement_profit_attribution', 'statement_bridge', 'variance_profit_bridge')}
        if name != 'moutai':
            assert all(D(r['contribution']) == 0 for r in tables['variance_profit_bridge']['rows'] if r['role'] == 'residual')
        assert all(D(r['amount']) == 0 for r in tables['statement_bridge']['rows'] if r['direction'] == '残差')
    write(args.out / 'tokens.json', sizes)
    write(args.out / 'key-tables.json', {name: {key: {k: t[k] for k in ('columns', 'rows')}
          for key, t in tabs.items()} for name, tabs in amounts.items()})
    # Explicit original-PDF acceptance of the raw-only report.
    tabs = all_results['moutai']['analysis_pipeline']['data']['numeric_tables']; checks = []
    for tab, metrics in MOUTAI.items():
        t = tabs['statement_' + tab]
        for key, (current, previous, page) in metrics.items():
            for period, expected in [('2024-FY', current), ('2023-FY', previous)]:
                rowkey, column = (key, period) if tab == 'income' else (period, key) if tab == 'profit_attribution' else (period + '_cash_' + key, 'amount')
                i, row = next((i, r) for i, r in enumerate(t['rows']) if r['key'] == rowkey)
                actual = D(row[column]) * 1000000
                assert actual == D(expected), (tab, rowkey, column, actual, expected)
                ref = t['evidence'][i][column]['source']['source_ref']
                assert ref['page'] == page and ref['source_method'] == '原表直读', ref
                checks.append({'table': tab, 'key': rowkey, 'column': column, 'yuan': str(actual), 'pdf_page': page,
                               'source_cell': {k: ref[k] for k in ('table_id', 'row', 'column', 'cell')}, 'status': 'matched'})
    write(args.out / 'moutai-52-pdf-checks.json', checks)
    # Removal is in a Python list, never a DB write. Restore both revenue columns.
    s = service_at(args.snapshot, args.snapshot.parent / 'verification')
    partial = []
    for name in ('yili', 'haier', 'carote', 'ruihe'):
        project, did = DOCS[name]; facts = load_facts(s, project, did)
        reduced = [r for r in facts if r['metric'] not in ALIASES['revenue']]
        st = Statement(s, project, reduced, document_id=did)
        baseline = next(r for r in amounts[name]['statement_income']['rows'] if r['key'] == 'revenue')
        for period in st.periods[:2]:
            r = st.pick('revenue', period, 'income')
            assert r and D(r['value']) == D(baseline[period]) * 1000000, (name, period)
            assert r['source_ref']['source_method'] == '原表直读'
            partial.append({'company': name, 'removed_revenue_facts': len(facts) - len(reduced), 'period': period,
                            'value': r['value'], 'scope': r['scope'], 'source': r['source_ref'], 'selection': st.selection})
    write(args.out / 'partial-ingestion-revenue.json', partial)
    write(args.out / 'summary.json', {'runs': json.loads((args.replay / 'summary.json').read_text('utf-8')),
          'all_ok': 30, 'pdf_numeric_checks': len(checks), 'removed_fact_recoveries': len(partial),
          'model_calls': 0, 'source_db_writes': 0, 'token_measurement': 'Local o200k_base, not billed model tokens',
          'moutai_profit_bridge_residual_yuan': '8346828.30',
          'moutai_residual_source': 'PDF63：利息支出下降8372327.90元，手续费及佣金支出上升25499.60元；现有利润桥尚未列入这两项'})
    print('Verified: 30 outputs,', len(checks), 'PDF numbers,', len(partial), 'removed-fact recoveries', flush=True)
    for row in sizes: print(row['company'], row['compact_context'], row['context_token_reduction_percent'], flush=True)


if __name__ == '__main__': main()

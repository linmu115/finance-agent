import copy
import csv
from decimal import Decimal, localcontext
import json
import random
from pathlib import Path
import tempfile
import unittest

from service.analysis_report import canonical_unit, compile_report, convert, render_report, model_quantity, save_table
from service.research_models import evaluate_model
from service.tests.test_research_models import dcf_spec


class PresentationTests(unittest.TestCase):
    def test_unit_invariance_for_new_random_amounts_not_company_answers(self):
        rng = random.Random(417)
        units = {'元': 1, '千元': 1000, '万元': 10000, '百万元': 1000000, '亿元': 100000000, 'billion': 1000000000}
        for _ in range(80):
            raw = Decimal(rng.randint(-10**15, 10**15)) / 100
            for source, factor in units.items():
                for display in units:
                    amount = convert(raw / factor, source, display)
                    self.assertEqual(Decimal(convert(amount, display, '元')), raw)
        self.assertEqual(convert(None, '百万元', '亿元'), None)
        self.assertEqual(Decimal(convert('0.157', 'ratio', '%')), Decimal('15.7'))
        self.assertEqual(convert('12.4', '百万股', '股'), '12400000.0')
        self.assertEqual(convert('1.78', '元/股', '元/股'), '1.78')
        for a, b in [('个百分点', '%'), ('元/股', '元'), ('股', '元')]:
            with self.assertRaises(ValueError):convert('1', a, b)

    def test_record_values_drive_csv_report_and_plot_data_without_rescaling_raw_unit(self):
        # Unrelated invented company/period/values; two source units, one normalized contract.
        records = [{'record_id': 'r', 'value': '78560234000', 'currency': 'HKD', 'raw_unit': '千元',
                    'data_kind': 'analyst_forecast', 'period': '2029', 'quality': 'needs_review',
                    'source_ref': {'document_id': 'd', 'page': 9, 'row': 2, 'column': 3}}]
        report = {'title': '示例', 'body': '机构预测收入 {{t.0.revenue}}，EPS {{t.0.eps}}。', 'tables': {'t': {
            'columns': {'year': {'label': '期间'}, 'revenue': {'label': '收入', 'unit': '亿元'}, 'eps': {'label': 'EPS', 'unit': '元/股', 'currency': 'HKD'}},
            'rows': [{'year': '2029E', 'revenue': {'record_id': 'r'}, 'eps': {'value': '2.47', 'unit': '元/股'}}]}}}
        result = compile_report(report, records)
        self.assertEqual(result['tables']['t']['rows'][0]['revenue'], '785.60234')
        evidence = result['tables']['t']['evidence'][0]['revenue']
        self.assertEqual(evidence['value'], '78560234000')
        self.assertEqual(evidence['source']['quality'], 'needs_review')
        self.assertEqual(evidence['source']['data_kind'], 'analyst_forecast')
        self.assertIn('785.60 HKD 亿元', result['body'])
        with tempfile.TemporaryDirectory() as directory:
            render_report(result, directory)
            root = Path(directory)
            with (root / 't.csv').open(encoding='utf-8-sig') as f:rows = list(csv.reader(f))
            self.assertEqual(rows[1], ['2029E', '785.60234', '2.47'])
            self.assertIn('HKD 亿元', rows[0][1])
            self.assertIn('785.60 HKD 亿元', (root / 'report.md').read_text(encoding='utf-8'))
            self.assertEqual(json.loads((root / 'chart_data.json').read_text(encoding='utf-8')), result)
        self.assertEqual(report['tables']['t']['rows'][0]['revenue'], {'record_id': 'r'})

    def test_mixed_currency_and_dimension_have_no_silent_conversion(self):
        r = {'tables': {'t': {'columns': {'v': {'unit': 'million'}}, 'rows': [
            {'v': {'value': '10', 'unit': 'million', 'currency': 'USD'}},
            {'v': {'value': '10', 'unit': 'million', 'currency': 'HKD'}}]}}}
        with self.assertRaisesRegex(ValueError, '不同币种'):compile_report(r)
        r['tables']['t']['rows'][1]['v'] = {'value': '10', 'unit': '元/股', 'currency': 'USD'}
        with self.assertRaisesRegex(ValueError, '不能把'):compile_report(r)
        r['tables']['t']['rows'][1]['v'] = {'value': None, 'unit': 'million', 'currency': 'USD'}
        self.assertIsNone(compile_report(r)['tables']['t']['rows'][1]['v'])

    def test_model_reference_uses_saved_scale_and_never_scales_per_share(self):
        spec = dcf_spec(); spec['amount_scale'] = '1000'
        model = {'id': 'm', 'revision_id': 'v', 'kind': 'dcf', 'spec': spec, 'result': evaluate_model('dcf', spec)}
        q = model_quantity(model, 'tables.forecast.0.revenue')
        self.assertEqual(Decimal(q['value']), Decimal(model['result']['tables']['forecast'][0]['revenue']) * 1000)
        per_share = model_quantity(model, 'results.value_per_share')
        self.assertEqual(per_share['value'], model['result']['results']['value_per_share'])
        self.assertEqual(per_share['source']['revision_id'], 'v')
        with self.assertRaisesRegex(ValueError, '不能改写'):model_quantity(model, 'results.value_per_share', '元')
        # The model's own unit restated at its scale changes nothing; a different scale or dimension would relabel the value.
        terminal = model_quantity(model, 'results.terminal_pv', '千元')
        self.assertEqual(terminal, model_quantity(model, 'results.terminal_pv'))
        with localcontext() as exact:
            exact.prec = 60
            self.assertEqual(Decimal(terminal['value']), Decimal(model['result']['results']['terminal_pv']) * 1000)
        for wrong in ('百万元', '亿元', '%'):
            with self.assertRaisesRegex(ValueError, '不能改写'):model_quantity(model, 'results.terminal_pv', wrong)
        with self.assertRaisesRegex(ValueError, '不能改写'):model_quantity(model, 'results.terminal_value_share', '%')

    def test_common_spellings_resolve_to_one_unit_and_currency(self):
        cases = {'亿元': ('亿元', None), '人民币百万元': ('百万元', 'CNY'), '百万人民币': ('百万元', 'CNY'), 'RMB million': ('million', 'CNY'),
                 "RMB'000": ('thousand', 'CNY'), "HK$'m": ('million', 'HKD'), '亿港元': ('亿元', 'HKD'), '百万美元': ('百万元', 'USD'),
                 '人民币': ('元', 'CNY'), 'CNY 百万元': ('百万元', 'CNY'), '（亿元）': ('亿元', None), 'Million': ('million', None),
                 '人民币/股': ('元/股', 'CNY'), '人民币元/股': ('元/股', 'CNY'), '港元/股': ('元/股', 'HKD'), 'HK$/share': ('元/股', 'HKD'), 'CNY/股': ('元/股', 'CNY'),
                 '百分点': ('个百分点', None), '个百分点': ('个百分点', None), '％': ('%', None), '百分比': ('%', None), '比例': ('ratio', None),
                 'x': ('倍', None), 'days': ('天', None)}
        for text, expected in cases.items():
            with self.subTest(text=text):self.assertEqual(canonical_unit(text), expected)
        # An amount needs 元 or a currency; magnitudes alone, other dimensions and mixed forms stay errors.
        for text in ['百万', '亿', '', 'm', '元/吨', '人民币百万股', 'RMB百万/股', '公斤', 'eps']:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, '未知单位'):canonical_unit(text)
        self.assertEqual(Decimal(convert('6012', 'RMB million', '人民币亿元')), Decimal('60.12'))
        self.assertEqual(Decimal(convert('0.122', '比例', '百分比')), Decimal('12.2'))
        self.assertEqual(convert('1.5', '百分点', 'pp'), '1.5')
        with self.assertRaises(ValueError):convert('1', '百分点', '百分比')

    def report_with_natural_units(self):
        return {'title': '示例', 'body': '净利润 {{t.0.profit}}亿元，上年 {{t.1.profit}} 人民币亿元；WACC {{t.0.wacc}}%，利润率提升 {{t.0.gain}}百分点，目标价 {{t.0.target}}。期间：{{t.0.year}}。',
                'tables': {'t': {'columns': {'year': {'label': '年度'}, 'profit': {'label': '归母净利润', 'unit': '人民币亿元'},
                                             'wacc': {'label': 'WACC', 'unit': '百分比', 'decimals': 1}, 'gain': {'label': '利润率变化', 'unit': '百分点', 'decimals': 1},
                                             'target': {'label': '目标价', 'unit': '港元/股'}},
                                 'rows': [{'year': '2025E', 'profit': {'value': '6012', 'unit': 'RMB million'}, 'wacc': {'value': '0.122', 'unit': 'ratio'},
                                           'gain': {'value': '1.5', 'unit': 'pp'}, 'target': {'value': '9.41', 'unit': 'HK$/share'}},
                                          {'year': '2024', 'profit': {'value': '54.3', 'unit': '亿元', 'currency': 'CNY'}, 'wacc': None, 'gain': None, 'target': None}]}}}

    def test_natural_units_convert_once_and_units_are_not_printed_twice(self):
        compiled = compile_report(self.report_with_natural_units())
        table = compiled['tables']['t']
        self.assertEqual({k: (c.get('unit'), c.get('currency')) for k, c in table['columns'].items()},
                         {'year': (None, None), 'profit': ('亿元', 'CNY'), 'wacc': ('%', None), 'gain': ('个百分点', None), 'target': ('元/股', 'HKD')})
        self.assertEqual([Decimal(row['profit']) for row in table['rows']], [Decimal('60.12'), Decimal('54.3')])
        self.assertEqual(Decimal(table['rows'][0]['wacc']), Decimal('12.2'))
        self.assertEqual(compiled['body'], '净利润 60.12 CNY 亿元，上年 54.30 CNY 亿元；WACC 12.2 %，利润率提升 1.5 个百分点，目标价 9.41 HKD 元/股。期间：2025E。')
        # A different unit after a placeholder is the author's own text and stays.
        other = self.report_with_natural_units();other['body'] = '{{t.0.profit}}左右，{{t.0.wacc}}的折现率，{{t.1.wacc}}%'
        self.assertEqual(compile_report(other)['body'], '60.12 CNY 亿元左右，12.2 %的折现率，—%')
        conflict = self.report_with_natural_units();conflict['tables']['t']['columns']['profit']['currency'] = 'HKD'
        with self.assertRaisesRegex(ValueError, '不同币种'):compile_report(conflict)
        mismatch = self.report_with_natural_units();mismatch['tables']['t']['rows'][0]['profit'] = {'value': '1', 'unit': '亿港元', 'currency': 'CNY'}
        with self.assertRaisesRegex(ValueError, '币种不一致'):compile_report(mismatch)
        foreign = self.report_with_natural_units();foreign['tables']['t']['rows'][0]['profit'] = {'value': '1', 'unit': '亿港元'}
        with self.assertRaisesRegex(ValueError, '不同币种'):compile_report(foreign)

    def test_markdown_table_is_one_block_and_matches_the_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            render_report(compile_report(self.report_with_natural_units()), directory)
            lines = (Path(directory) / 'report.md').read_text(encoding='utf-8').split('\n')
            start = next(i for i, line in enumerate(lines) if line.startswith('| 年度'))
            self.assertEqual(lines[start:start + 4], ['| 年度 | 归母净利润（CNY 亿元） | WACC（%） | 利润率变化（个百分点） | 目标价（HKD 元/股） |',
                                                       '| --- | --- | --- | --- | --- |', '| 2025E | 60.12 | 12.2 | 1.5 | 9.41 |', '| 2024 | 54.30 | — | — | — |'])
            self.assertEqual(lines[start - 1], '')
            self.assertTrue(start + 4 == len(lines) or lines[start + 4] == '')
            with (Path(directory) / 't.csv').open(encoding='utf-8-sig') as f:rows = list(csv.reader(f))
            self.assertEqual(rows, [['年度', '归母净利润（CNY 亿元）', 'WACC（%）', '利润率变化（个百分点）', '目标价（HKD 元/股）'],
                                    ['2025E', '60.12', '12.2', '1.5', '9.41'], ['2024', '54.3', '', '', '']])

    def test_script_csv_goes_through_the_same_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);source = root / 'input';source.mkdir()
            # Normalized record values are in base currency units; the forecast was read in 百万元.
            (source / 'facts.json').write_text(json.dumps([{'fact_id': 'f1', 'value': '5430000000', 'currency': 'CNY', 'period': '2024-FY'}]), encoding='utf-8')
            (source / 'research_records.json').write_text(json.dumps([{'record_id': 'r1', 'value': '6012000000', 'currency': 'CNY', 'data_kind': 'analyst_forecast'}]), encoding='utf-8')
            table = save_table('净利润预测', {'year': {'label': '年度'}, 'profit': {'label': '归母净利润', 'unit': '亿元'}},
                               [{'year': '2024', 'profit': {'fact_id': 'f1'}}, {'year': '2025E', 'profit': {'record_id': 'r1'}},
                                {'year': '2026E', 'profit': {'value': 6688.5, 'unit': '百万元', 'currency': 'CNY'}}],
                               input_dir=source, output_dir=root / 'output')
            with (root / 'output' / '净利润预测.csv').open(encoding='utf-8-sig') as f:rows = list(csv.reader(f))
            self.assertEqual(rows, [['年度', '归母净利润（CNY 亿元）'], ['2024', '54.3'], ['2025E', '60.12'], ['2026E', '66.885']])
            self.assertEqual([row['profit'] for row in table['rows']], ['54.3', '60.12', '66.885'])
            self.assertEqual(table['evidence'][1]['profit']['source']['data_kind'], 'analyst_forecast')
            # Works without any mounted project data, and a missing record is an error rather than an empty cell.
            plain = save_table('比率', {'name': {}, 'rate': {'unit': '%'}}, [{'name': 'WACC', 'rate': {'value': '0.122', 'unit': 'ratio'}}], input_dir=root / 'none', output_dir=root / 'output')
            self.assertEqual(Decimal(plain['rows'][0]['rate']), Decimal('12.2'))
            with self.assertRaisesRegex(ValueError, '没有记录'):
                save_table('缺失', {'v': {'unit': '亿元'}}, [{'v': {'record_id': 'missing'}}], input_dir=source, output_dir=root / 'output')

    def test_saved_model_inputs_are_cells_with_their_own_units(self):
        spec = dcf_spec(); spec['amount_scale'] = '1000000'
        model = {'id': 'm', 'revision_id': 'v', 'kind': 'dcf', 'spec': spec, 'result': evaluate_model('dcf', spec)}
        wacc = model_quantity(model, 'spec.discount.wacc')
        self.assertEqual((wacc['value'], wacc['unit'], wacc['currency']), (str(Decimal(spec['discount']['wacc'])), 'ratio', None))
        revenue = model_quantity(model, 'spec.base.revenue')
        self.assertEqual((Decimal(revenue['value']), revenue['unit'], revenue['currency']), (Decimal(spec['base']['revenue']) * 1000000, '元', spec['currency']))
        report = {'tables': {'p': {'columns': {'name': {}, 'rate': {'label': '比率', 'unit': '%'}, 'amount': {'label': '金额', 'unit': '亿元'}},
                                   'rows': [{'name': 'WACC', 'rate': {'model': 'base', 'path': 'spec.discount.wacc'}, 'amount': None},
                                            {'name': '永续增长', 'rate': {'model': 'base', 'path': 'spec.terminal.growth'}, 'amount': None},
                                            {'name': '基期收入', 'rate': None, 'amount': {'model': 'base', 'path': 'spec.base.revenue'}}]}},
                  'body': 'WACC {{p.0.rate}}%'}
        compiled = compile_report(report, models={'base': model})
        rows = compiled['tables']['p']['rows']
        self.assertEqual(Decimal(rows[0]['rate']), Decimal(spec['discount']['wacc']) * 100)
        self.assertEqual(Decimal(rows[1]['rate']), Decimal(spec['terminal']['growth']) * 100)
        self.assertEqual(Decimal(rows[2]['amount']), Decimal(spec['base']['revenue']) / 100)
        self.assertEqual(compiled['body'], f'WACC {Decimal(spec["discount"]["wacc"]) * 100:,.2f} %')
        with self.assertRaisesRegex(ValueError, '不能把'):
            compile_report({'tables': {'p': {'columns': {'x': {'unit': '%'}}, 'rows': [{'x': {'model': 'base', 'path': 'spec.base.revenue'}}]}}}, models={'base': model})


if __name__ == '__main__':unittest.main()

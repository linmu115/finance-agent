import copy
import csv
from decimal import Decimal
import json
import random
from pathlib import Path
import tempfile
import unittest

from service.analysis_report import compile_report, convert, render_report, model_quantity
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


if __name__ == '__main__':unittest.main()

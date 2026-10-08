"""F1.1: raw CSV cells must use the same numeric contract as compiled reports."""
import copy
import unittest

from service.analysis_report import bind_text


class AnswerNumericBindingTests(unittest.TestCase):
    def test_f2_d1_mixed_percentage_row_returns_reference_error(self):
        # Actual F2_D1 raw CSV row; these percentages are NOT monetary amounts.
        table = {'columns': {'指标': {'label': '指标'},
                            **{key: {'unit': '百万元', 'currency': 'CNY', 'numeric': True}
                               for key in ('2024H1人民币百万元', '2025H1人民币百万元', '变动人民币百万元')}},
                 'rows': [{'指标': '毛利率', '2024H1人民币百万元': '41.38%',
                           '2025H1人民币百万元': '33.65%', '变动人民币百万元': '-7.73个百分点'}]}
        tables = {'profit_cashflow_workpaper': table}
        before = copy.deepcopy(tables)
        for token, value in [('table:profit_cashflow_workpaper', '41.38%'),
                             ('profit_cashflow_workpaper.毛利率.2025H1人民币百万元', '33.65%'),
                             ('profit_cashflow_workpaper.毛利率.变动人民币百万元', '-7.73个百分点')]:
            with self.subTest(token=token), self.assertRaises(ValueError) as caught:
                bind_text('{{' + token + '}}', tables)
            self.assertIn(value, str(caught.exception))
            self.assertIn('百万元', str(caught.exception))
            self.assertIn('可用引用', str(caught.exception))
        self.assertEqual(tables, before)

    def test_convertible_raw_cells_and_null_keep_their_stated_units(self):
        for value, unit, expected in [
            ('1,234.56', '百万元', '1,234.56 百万元'),
            (' １，２３４．５６ ', '百万元', '1,234.56 百万元'),
            ('41.38%', '%', '41.38 %'), ('３３．６５％', '%', '33.65 %'),
            ('41.38%', 'ratio', '0.41 ratio'), ('-7.73', '个百分点', '-7.73 个百分点'),
            (None, '百万元', '—'), ('-12.345', '百万元', '-12.34 百万元'),
        ]:
            with self.subTest(value=value, unit=unit):
                tables = {'t': {'columns': {'v': {'unit': unit}}, 'rows': [{'v': value}]}}
                before = copy.deepcopy(tables)
                self.assertEqual(bind_text('{{t.0.v}}', tables), expected)
                self.assertNotIn('{{', bind_text('{{table:t}}', tables))
                self.assertEqual(tables, before)

    def test_unparseable_cells_use_existing_a1_error_for_cell_and_table(self):
        for value in ('—', '', ' ', '未披露', '约12', '12万元', '41.38%', '-7.73个百分点', 'NaN', 'Infinity'):
            tables = {'t': {'columns': {'v': {'unit': '百万元'}}, 'rows': [{'v': value}]}}
            for body in ('{{t.0.v}}', '{{table:t}}'):
                with self.subTest(value=value, body=body), self.assertRaisesRegex(ValueError, '占位符.*无法解析.*可用引用'):
                    bind_text(body, tables)


if __name__ == '__main__':
    unittest.main()

"""Regression for the observed CSV corruption; no provider/API calls."""
import csv
import io
import json
import unittest

from blind import Redactor, redact_text


class StructuredAnonymizationTest(unittest.TestCase):
    def test_csv_quotes_commas_thousands_and_chinese_headers(self):
        rows = [
            ['指标', '金额（人民币百万元）', '解释', '出处'],
            ['收入', '1,234.50', '含逗号,含"引号"及换行\n第二行',
             'https://www.cfainstitute.org/insights/evaluating-quality-financial-reports'],
            ['现金流', '-2,345.67', 'Financial Reports / baseline / prepared 均是普通正文',
             json.dumps([{'document_id': '3d9d0befd8374eed9a7488dbd8dd00d2', 'page': 23,
                          'value': 1234.5, 'note': '含"引号",来源'}], ensure_ascii=False)],
        ]
        buffer = io.StringIO(newline='')
        csv.writer(buffer).writerows(rows)
        actual = list(csv.reader(io.StringIO(redact_text(buffer.getvalue(), '.csv', Redactor({})), newline='')))
        expected = [r[:] for r in rows]
        expected[2][3] = expected[2][3].replace('3d9d0befd8374eed9a7488dbd8dd00d2', 'ref_0001')
        self.assertEqual(actual, expected)
        self.assertEqual([len(r) for r in actual], [4, 4, 4])
        self.assertEqual(json.loads(actual[2][3])[0]['value'], 1234.5)

    def test_json_preserves_keys_numbers_and_public_url(self):
        original = {'title': 'Financial Reports', 'amount': 1234.5, 'missing': None,
                    'rows': [{'方向': -1, 'available': True}],
                    'url': 'https://example.com/a,b?x=1',
                    'source_run_id': '831d6910-24bc-4b68-93cc-9e72dbeeb956'}
        actual = json.loads(redact_text(json.dumps(original), '.json', Redactor({})))
        for key in ['title', 'amount', 'missing', 'rows', 'url']:
            self.assertEqual(actual[key], original[key])
        self.assertEqual(actual['system_component'], 'ref_0001')

    def test_drive_path_is_not_https_scheme(self):
        red = Redactor({})
        self.assertEqual(red('https://example.com/a,b'), 'https://example.com/a,b')
        self.assertEqual(red('"D:/private/output.json"'), '"[local-path]"')
        self.assertEqual(red('ORIGINAL_PI_LAUNCH'), 'system_component')


if __name__ == '__main__':
    unittest.main()

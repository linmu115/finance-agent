"""Chart helpers accept the same unit spellings as reports and never exchange currencies."""
import unittest

from service.finance_charts import amount_values, model_values, money_unit, record_values


class ChartUnitTests(unittest.TestCase):
    def test_amount_spellings_scale_identically(self):
        for spelling, expected in {'亿元': '亿元', '人民币亿元': '亿元', '（亿元）': '亿元', 'CNY 亿元': '亿元'}.items():
            self.assertEqual(amount_values(['6012000000', None], 1, spelling), ([60.12, None], expected))
        self.assertEqual(amount_values(['6012'], '1000000', 'RMB million'), ([6012.0], 'million'))
        self.assertEqual(amount_values(['6012'], '1000000', '十亿元'), ([6.012], '十亿元'))
        for not_money in ('%', '百分点', '元/股', '股', '百万'):
            with self.subTest(unit=not_money), self.assertRaises(ValueError):
                amount_values(['1'], 1, not_money)

    def test_a_currency_named_in_the_unit_must_be_the_data_currency(self):
        records = [{'record_id': 'r', 'value': '6012000000', 'currency': 'CNY'}]
        values, label, data = record_values(records, '人民币亿元')
        self.assertEqual((values, label, data[0]['record_id']), ([60.12], 'CNY 亿元', 'r'))
        with self.assertRaisesRegex(ValueError, '不做隐含换汇'):
            record_values(records, '亿港元')
        model = {'spec': {'amount_scale': '1000000', 'currency': 'HKD'}}
        self.assertEqual(model_values(model, ['250'], '亿港元'), ([2.5], 'HKD 亿元'))
        with self.assertRaisesRegex(ValueError, '不做隐含换汇'):
            model_values(model, ['250'], '人民币亿元')
        self.assertEqual(money_unit('亿港元'), ('亿元', 'HKD'))
        self.assertEqual(money_unit('亿元', 'USD'), ('亿元', 'USD'))


if __name__ == '__main__':
    unittest.main()

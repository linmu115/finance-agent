import unittest
from copy import deepcopy
from decimal import Decimal
from service.research_models import evaluate_model
from service.research_schema import get_model_example


class ModelReviewTests(unittest.TestCase):
    def test_equal_duplicate_finance_expense_does_not_hide_in_change_bridge(self):
        spec = get_model_example('financial_quality')
        for row in spec['periods']:
            row.update(revenue='1000', cogs='500', opex='120', other_operating_income='0',
                       finance_expense='20', reported_operating_profit='380',
                       opex_components=[{'label': '管理费用', 'amount': '100', 'kind': 'other'},
                                        {'label': '财务费用', 'amount': '20', 'kind': 'finance_expense'}])
        original = deepcopy(spec)
        result = evaluate_model('financial_quality', spec)
        duplicate = [c for c in result['checks'] if c['rule'] == 'finance_expense_double_count']
        self.assertEqual(len(duplicate), 2)
        self.assertTrue(all(c['status'] == 'needs_review' for c in duplicate))
        residuals = [c for c in result['checks'] if c['rule'] == 'reported_profit_reconciliation']
        self.assertEqual([Decimal(c['residual']) for c in residuals], [20, 20])
        self.assertEqual(result['tables']['attribution'][0]['reported_operating_profit_residual'], '0')
        self.assertIsNotNone(result['tables']['quality'][1]['cash_conversion'])
        self.assertEqual(spec, original)

    def test_included_finance_expense_is_only_deducted_once_and_negative_keeps_sign(self):
        spec = get_model_example('financial_quality')
        spec['profit_bridge']['finance_expense_treatment'] = 'included_in_opex'
        for row in spec['periods']:
            row.update(revenue='1000', cogs='500', opex='80', other_operating_income='0',
                       finance_expense='-20', reported_operating_profit='420',
                       opex_components=[{'label': '管理费用', 'amount': '100', 'kind': 'other'},
                                        {'label': '财务费用', 'amount': '-20', 'kind': 'finance_expense'}])
        result = evaluate_model('financial_quality', spec)
        self.assertTrue(all(c['status'] == 'passed' for c in result['checks']))

    def test_missing_profit_components_are_not_imputed_zero(self):
        spec = get_model_example('financial_quality')
        del spec['periods'][0]['other_operating_income']
        checks = evaluate_model('financial_quality', spec)['checks']
        pending = [c for c in checks if c.get('year') == 2024]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['status'], 'not_checked')
        self.assertIn('periods.0.other_operating_income', pending[0]['input_paths'])

    def test_terminal_source_forecast_remains_model_assumption_without_losing_reference(self):
        spec = get_model_example('dcf')
        path = 'terminal.ebit_margin'
        spec['input_basis'][path] = {'basis': 'disclosed', 'source_kind': 'analyst_forecast', 'rationale': '来源预测有限期间，延用到终值。'}
        spec['source_refs'][path] = [{'kind': 'document', 'id': 'example', 'locator': 'page:7'}]
        original = deepcopy(spec)
        result = evaluate_model('dcf', spec)
        item = next(item for item in result['input_usage'] if item['path'] == path)
        self.assertEqual(item['usage'], 'model_assumption')
        self.assertEqual(item['source_kind'], 'analyst_forecast')
        self.assertEqual(item['source_basis'], 'disclosed')
        self.assertEqual(item['source_refs'], spec['source_refs'][path])
        self.assertEqual(spec, original)

    def test_scenario_terminal_paths_are_scoped_and_old_results_are_not_mutated(self):
        spec = get_model_example('manufacturing_scenario')
        result = evaluate_model('manufacturing_scenario', spec)
        self.assertEqual({r['path'] for r in result['input_usage']}, {'dcf.terminal.' + key for key in spec['dcf']['terminal']})


if __name__ == '__main__':
    unittest.main()

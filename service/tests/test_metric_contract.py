"""The canonical ingestion vocabulary must resolve through every workpaper."""
import ast
from pathlib import Path
import unittest

from service.standard_metrics import STANDARD_METRICS, StandardMetric, WORKPAPER_ALIASES, LEGACY_WORKPAPER_ALIASES, ROWS, standard_metric, workpaper_concepts
from service.normalization import METRICS
from service.financial_workpapers import ALIASES, INCOME, CAS_INCOME
from service.workpaper_analyst import EXTRA
from service.workpaper_periods import FLOW_METRICS
from service.workpaper_signals import DEBT_CONCEPTS
from service.workpaper_comparison import INCOME as COMPARISON_INCOME


class MetricContractTests(unittest.TestCase):
    def test_all_canonical_ids_explicitly_declare_semantic_ownership(self):
        self.assertEqual(set(STANDARD_METRICS),set(ROWS)|set(METRICS))
        for metric,definition in STANDARD_METRICS.items():
            with self.subTest(metric=metric):
                self.assertIsInstance(definition,StandardMetric)
                if definition.concept:
                    self.assertIn(metric,ALIASES[definition.concept])
                    self.assertIn(definition.concept,workpaper_concepts(metric))
        # Canonical IDs cannot silently acquire a separate alias-table owner.
        for aliases in LEGACY_WORKPAPER_ALIASES.values():
            self.assertFalse(set(aliases)&set(STANDARD_METRICS))
        self.assertIs(ALIASES,WORKPAPER_ALIASES)

    def test_all_five_workpaper_concepts_resolve(self):
        concepts={k for k,_ in INCOME+CAS_INCOME}|set(EXTRA)|set(FLOW_METRICS)|set(COMPARISON_INCOME)|set(DEBT_CONCEPTS)
        # Direct literal lookups, including signs/variance/period/comparison and
        # source adapters, supplement the loop-driven public concept lists.
        root=Path(__file__).parents[1]
        modules=['financial_workpapers','workpaper_analyst','workpaper_variance','workpaper_signals',
                 'workpaper_periods','workpaper_comparison','workpaper_annual']
        for module in modules:
            for node in ast.walk(ast.parse((root/(module+'.py')).read_text('utf-8'))):
                if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='ALIASES' and isinstance(node.slice,ast.Constant):
                    concepts.add(node.slice.value)
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='pick' and node.args and isinstance(node.args[0],ast.Constant):
                    concepts.add(node.args[0].value)
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'get','inc','checkpoint'} and node.args and isinstance(node.args[0],ast.Constant):
                    concepts.add(node.args[0].value)
                # No undocumented fallback lets a new misspelled concept look
                # like a valid metric and return an empty candidate list.
                self.assertFalse(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and
                    isinstance(node.func.value,ast.Name) and node.func.value.id=='ALIASES' and node.func.attr=='get')
        self.assertFalse(concepts-set(ALIASES),concepts-set(ALIASES))
        for concept in concepts:self.assertTrue(ALIASES[concept],concept)

    def test_actual_standard_statement_rows_resolve_to_workpaper_concepts(self):
        expected={'税金及附加':'surcharges','研发费用':'research','财务费用':'finance_costs',
          '对联营企业和合营企业的投资收益':'associates','公允价值变动收益':'fair_value_gains',
          '资产处置收益':'asset_disposal','营业外收入':'nonoperating_income','营业外支出':'nonoperating_expenses',
          '少数股东损益':'minority_profit','所有者权益合计':'equity',
          '期初现金及现金等价物余额':'cash_begin','期末现金及现金等价物余额':'cash_end',
          '汇率变动对现金及现金等价物的影响':'cash_fx','营业收入':'revenue','营业成本':'cogs',
          '归属于上市公司股东的净利润':'parent_profit','归属于上市公司股东的扣除非经常性损益的净利润':'deducted_profit'}
        for label,concept in expected.items():
            with self.subTest(label=label):self.assertIn(standard_metric(label),ALIASES[concept])

    def test_ifrs_aliases_and_different_economic_concepts_stay_separate(self):
        self.assertIn('net_finance_income',ALIASES['finance_net'])
        self.assertIn('net_cash_used_in_generated_from_operating_activities',ALIASES['cfo'])
        self.assertNotIn('total_operating_revenue',ALIASES['revenue'])
        self.assertNotIn('finance_income_net',ALIASES['finance_costs'])
        self.assertNotIn('impairment_allowance',ALIASES['inventory_charge'])
        self.assertNotIn('minority_interests',ALIASES['minority_profit'])

    def test_exact_core_spelling_aliases_and_excluded_nearby_concepts(self):
        expected={'net_profit_parent_ex_nonrecurring':'deducted_profit','net_assets_parent':'parent_equity',
                  'operating_cash_flow_net':'cfo','net_cash_from_operating_activities':'cfo',
                  'cash_and_cash_equivalents_ending':'cash_end'}
        for metric,concept in expected.items():
            with self.subTest(metric=metric):self.assertEqual(workpaper_concepts(metric),(concept,))
        for metric in ('cash_ending_balance','cash_equivalents_ending_balance','business_segment_revenue',
                       'subsidiary_total_assets','research_development_expense',
                       'net_profit_attributable_to_parent_common_shareholders',
                       'net_profit_parent_ex_nonrecurring_growth_rate','notes_amount'):
            with self.subTest(metric=metric):self.assertEqual(workpaper_concepts(metric),())


if __name__=='__main__':unittest.main()

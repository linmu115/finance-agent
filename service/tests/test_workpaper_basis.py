import copy
from decimal import Decimal as D
import unittest
from unittest.mock import patch

from service.financial_workpapers import financial_workpaper
from service.workpaper_basis import (basis_changes,extract_adjustment_pairs,quantify_restatement,scan_basis_markers)
from service.tests import test_workpaper_annual


def tables():
    return [{'table_id':'d:t1','page':1,'rows':[
        ['项目','2024年','2023年',''],['','','调整后','调整前'],
        ['营业收入','150','120','100'],['营业成本','90','80','80'],
        ['净利润','25','12','10'],['归属于股东的净利润','25','12','10'],
        ['加权平均净资产收益率(%)','30','24','20'],['未知调整项目','','9','8']]}]


class BasisCoreTests(unittest.TestCase):
    def test_multirow_columns_quantities_and_ratio_impact(self):
        pairs,unknown=extract_adjustment_pairs(tables(),{1:'单位：元 币种：人民币'},'d',2024,'CNY','consolidated_CAS')
        self.assertEqual(len(pairs),6);self.assertEqual(len(unknown),1)
        self.assertEqual(pairs[0]['period'],'2023-FY')
        self.assertEqual(pairs[0]['original']['source']['column'],4)
        self.assertEqual(pairs[0]['restated']['source']['column'],3)
        deltas,ratios=quantify_restatement(pairs)
        self.assertEqual(D(deltas[0]['delta']['value']),20)
        rows={x['ratio']:x for x in ratios}
        self.assertAlmostEqual(D(rows['gross_margin']['impact_pp']['value']),D('13.33333333333333333333'),places=18)
        self.assertEqual(D(rows['net_margin']['impact_pp']['value']),0)
        self.assertEqual(D(rows['weighted_roe']['impact_pp']['value']),4)
        self.assertIsNone(rows['roe_average_parent']['impact_pp']['value'])

    def test_missing_amount_or_unit_and_unknown_label_retained(self):
        t=tables();t[0]['rows'][2][3]=''
        pairs,unknown=extract_adjustment_pairs(t,{1:'单位：元'},'d',2024,'CNY','consolidated')
        changes,_=quantify_restatement(pairs)
        self.assertIsNone(changes[0]['delta']['value'])
        self.assertTrue(unknown)
        pairs,_=extract_adjustment_pairs(t,{},'d',2024,'CNY','consolidated')
        self.assertIsNone(pairs[0]['restated']['value'])

    def test_carry_adjacent_header_only_at_same_adjustment_columns(self):
        t=tables();t.append({'table_id':'d:t2','page':2,'rows':[['','','调整后','调整前'],['加权平均净资产收益率(%)','','25','20']]})
        pairs,_=extract_adjustment_pairs(t,{1:'单位：元'},'d',2024,'CNY','consolidated')
        self.assertEqual(pairs[-1]['period'],'2023-FY')
        self.assertEqual(pairs[-1]['original']['source']['header_source']['page'],1)
        t[-1]['page']=5
        pairs,unknown=extract_adjustment_pairs(t,{1:'单位：元'},'d',2024,'CNY','consolidated')
        self.assertEqual(len(pairs),6);self.assertTrue(any('期间' in x['reason'] for x in unknown))

    def test_explicit_adjusted_previous_period_label(self):
        t=tables();t[0]['rows'][0][2]='上年同期'
        pairs,_=extract_adjustment_pairs(t,{1:'单位：元'},'d',2024,'CNY','consolidated','H1')
        self.assertEqual(pairs[0]['period'],'2023-H1')

    def test_header_only_page_tail_replaces_balance_date_and_eps_dimension(self):
        t=[{'table_id':'d:t1','page':1,'rows':[['项目','2024年末','2023年末',''],['','','调整后','调整前'],['总资产','200','120','100']]},
           {'table_id':'d:t2','page':1,'rows':[['主要财务指标','','','2024年','','','2023年','','','本期比上年','','2022年','']]},
           {'table_id':'d:t3','page':2,'rows':[['','','调整后','调整前'],['加权平均净资产收益率(%)','25','24','20'],['扣除非经常性损益后的每\n股收益','2','1.2','1.0']]}]
        pairs,_=extract_adjustment_pairs(t,{1:'单位：元'},'d',2024,'CNY','consolidated')
        self.assertEqual(pairs[0]['period'],'2023-12-31')
        self.assertEqual(pairs[1]['period'],'2023-FY')
        self.assertEqual(pairs[1]['original']['source']['header_source']['column'],7)
        self.assertEqual(pairs[2]['metric'],'deducted_eps')
        self.assertEqual(pairs[2]['original']['unit'],'元/股')

    def test_negation_zero_and_generic_policy_are_not_restatement(self):
        pages={1:'重要会计政策变更 □适用 √不适用。前期差错更正：不适用。由于会计政策变更，影响期初未分配利润0元。',
               2:'对于同一控制下企业合并，应按被合并方账面价值计量。追溯重述法 □适用 √不适用。',
               3:'The adoption did not result in significant changes to the Group’s accounting policies. Interest at 6% per annum.'}
        rows=scan_basis_markers(pages,'d')
        self.assertTrue(any(x['status']=='not_applicable' for x in rows))
        self.assertTrue(any(x['status']=='no_impact_or_no_change' for x in rows))
        self.assertFalse(any(x['status']=='restatement_disclosed' for x in rows))
        self.assertFalse(any(x['kind']=='restatement' and x['source']['page']==3 for x in rows))

    def test_estimate_policy_error_and_common_control_occurrence(self):
        pages={1:'重要会计估计变更 √适用 □不适用。会计政策变更 √适用 □不适用。前期差错更正 √适用 □不适用。',
               2:'同一控制下企业合并 √适用 □不适用。本公司已对前期财务报表进行追溯重述。'}
        rows=scan_basis_markers(pages,'d')
        self.assertEqual({x['kind'] for x in rows if x['status']=='change_disclosed'}, {'accounting_estimate','accounting_policy','prior_error','common_control'})
        self.assertTrue(any(x['status']=='restatement_disclosed' for x in rows))

    def test_different_currency_no_delta(self):
        pairs,_=extract_adjustment_pairs(tables(),{1:'单位：元'},'d',2024,'CNY','consolidated')
        pairs[0]['original']['currency']='USD'
        changes,_=quantify_restatement(pairs)
        self.assertIsNone(changes[0]['delta']['value'])


class BasisServiceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_workpaper_annual.AnnualWorkpapersTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def test_annual_no_restatement_and_three_repeated_items(self):
        f=self.fixture
        with patch('service.workpaper_basis.load_facts',return_value=f.facts):
            report,_=basis_changes(f.s,'p',f.doc)
        self.assertFalse(report['tables']['summary']['rows'][0]['restatement_detected'])
        repeated=report['tables']['repeated_nonrecurring']['rows']
        self.assertEqual(len(repeated),3)
        self.assertTrue(all(x['occurrences']['value']=='3' for x in repeated))

    def test_tool_publishes_and_original_other_report_can_supply_pair(self):
        f=self.fixture
        original=next(copy.deepcopy(r) for r in f.facts if r['metric']=='revenue' and r['period']=='2023-FY')
        original['document_id']='older';original['source_ref']['document_id']='older';original['source_ref']['normalization']['restatement']='original'
        current=copy.deepcopy(original);current['document_id']=f.doc;current['source_ref']['document_id']=f.doc
        current['source_ref']['normalization']['restatement']='restated';current['value']=str(D(original['value'])+100)
        inputs=[r for r in f.facts if not (r['metric']=='revenue' and r['period']=='2023-FY')]+[current]
        with patch('service.workpaper_basis.load_facts',side_effect=[inputs,[*inputs,original]]):
            result=financial_workpaper(f.s,'p','basis_changes',document_id=f.doc)
        self.assertTrue(result['report']['tables']['summary']['rows'][0]['restatement_detected'])
        self.assertEqual(D(result['report']['tables']['adjustments']['rows'][0]['delta_money']),D('.0001'))


if __name__=='__main__':unittest.main()

import copy
import unittest

from service.metric_normalization import apply_metric_normalization
from service.source_dimensions import apply_source_dimensions
from service.standard_metrics import CONTEXTUAL_LABELS, STANDARD_METRICS, canonical_rows, exact_standard_metric
from service.tests.test_ingestion_semantics_v3 import fact


class MetricContextTests(unittest.TestCase):
    def test_ownership_labels_follow_profit_comprehensive_and_equity_blocks(self):
        labels = ['Non-controlling interests', 'Minority interests', 'Non controlling interests',
                  'Owners of the Company', 'Owners of the parent', 'Equity holders of the Company',
                  'Shareholders of the Company', '本公司擁有人', '非控股權益']
        for label in labels:
            minority = label in labels[:3] or label == '非控股權益'
            cases = [('Profit attributable to:', 'minority_profit' if minority else 'net_profit_parent'),
                     ('Total comprehensive income attributable to:', 'comprehensive_income_minority' if minority else 'comprehensive_income_parent'),
                     ('Other comprehensive income attributable to:', 'other_comprehensive_income_minority' if minority else 'other_comprehensive_income_parent'),
                     ('EQUITY', 'minority_interests' if minority else 'equity_parent')]
            for heading, expected in cases:
                with self.subTest(label=label, heading=heading):
                    table = {'rows':[[heading,''],[label,'12']]}
                    f = fact('original_metric', label)
                    apply_metric_normalization(table, [f])
                    self.assertEqual(f['metric'], expected)
                    self.assertEqual(f['source']['normalization']['metric_aliases'], ['original_metric'])
                    before = copy.deepcopy(f)
                    apply_metric_normalization(table, [f])
                    self.assertEqual(f, before)

    def test_statement_tag_without_source_cannot_guess_ownership(self):
        for statement in ('income', 'balance', 'notes'):
            table = {'rows':[['项目','2025'],['Non-controlling interests','12']]}
            f = fact('non_controlling_interests', 'Non-controlling interests')
            f['source']['normalization']['statement'] = statement
            before = copy.deepcopy(f)
            self.assertEqual(len(apply_metric_normalization(table,[f])), 1)
            self.assertEqual(f, before)
            self.assertIsNone(exact_standard_metric('Non-controlling interests'))

    def test_local_block_overrides_page_title_and_stops_at_new_block(self):
        table={'rows':[['Profit attributable to:',''],['Non-controlling interests','12'],
                       ['Total comprehensive income attributable to:',''],['Non-controlling interests','12'],
                       ['Other information:',''],['Non-controlling interests','12']]}
        fs=[fact('original_metric','Non-controlling interests',row=i) for i in (2,4,6)]
        apply_metric_normalization(table,fs,{'statement':'balance','text':'Consolidated Statement of Financial Position'})
        self.assertEqual([f['metric'] for f in fs],['minority_profit','comprehensive_income_minority','original_metric'])

    def test_source_statement_and_continued_attribution_heading(self):
        table={'rows':[['Non-controlling interests','12']]}
        for text, expected in [('Consolidated Statement of Financial Position','minority_interests'),
                               ('Profit attributable to:','minority_profit'),
                               ('Consolidated Statement of Comprehensive Income','original_metric'),
                               ('Profit attributable to:\nOther information:','original_metric'),
                               ('Profit attributable to:\n3 OTHER INFORMATION','original_metric')]:
            f=fact('original_metric','Non-controlling interests',row=1)
            apply_metric_normalization(table,[f],{'text':text})
            self.assertEqual(f['metric'],expected)

    def test_previous_wrong_canonical_metric_is_corrected_with_history_alias(self):
        table={'rows':[['Profit attributable to:',''],['Non-controlling interests','12']]}
        f=fact('minority_interests','Non-controlling interests')
        f['source']['normalization']['metric_aliases']=['non_controlling_interests']
        apply_metric_normalization(table,[f])
        self.assertEqual(f['metric'],'minority_profit')
        self.assertEqual(f['source']['normalization']['metric_aliases'],['non_controlling_interests','minority_interests'])

    def test_equity_movement_matrix_is_not_row_normalized(self):
        table={'rows':[['Profit attributable to:',''],['Owners of the Company','12']]}
        f=fact('equity_movement','Owners of the Company')
        f['source']['normalization']['statement']='equity'
        apply_metric_normalization(table,[f])
        self.assertEqual(f['metric'],'equity_movement')

    def test_canonical_submission_rows_use_same_context_contract(self):
        for heading, expected in [('Profit attributable to:','minority_profit'),('EQUITY','minority_interests'),('Item','custom')]:
            table={'rows':[[heading,''],['Non-controlling interests','12']]}
            rows=[{'row':2,'attributes':{'metric':'custom'}}]
            out=canonical_rows(table,rows,statement='income')
            self.assertEqual(out[0]['attributes']['metric'],expected)

    def test_descriptive_dimension_uses_same_context(self):
        label='Non-controlling interests'
        table={'rows':[['Profit attributable to:',''],[label,'12']]}
        f=fact('custom',label,dimensions={'financial_item':label})
        apply_source_dimensions(table,[f])
        self.assertEqual(f['source']['normalization']['dimension_roles'],{'financial_item':'descriptive'})

    def test_contextual_contract_targets_exist_and_oci_does_not_invent_tax_basis(self):
        for targets in CONTEXTUAL_LABELS.values():
            self.assertFalse(set(targets.values()) - STANDARD_METRICS.keys())
        self.assertEqual(exact_standard_metric('Other comprehensive income',context={'kind':'balance'}),'other_comprehensive_income')
        self.assertIsNone(exact_standard_metric('Other comprehensive income',context={'kind':'profit'}))

    def test_balance_analysis_section_preserves_oci_balance(self):
        table={'rows':[['项目名称','本期期末数'],['其他综合收益','12']]}
        f=fact('balance_sheet_item','其他综合收益')
        apply_metric_normalization(table,[f],{'text':'1、资产及负债状况','statement':'notes'})
        self.assertEqual(f['metric'],'other_comprehensive_income')


class EmptySubtotalTests(unittest.TestCase):
    def test_unnamed_subtotals_are_not_named_components(self):
        table={'rows':[['项目','2024'],['','12'],['Named component','12'],['Total','24']]}
        fs=[fact('custom','',row=2),fact('custom','Named component',row=3),fact('custom','Total',row=4)]
        apply_source_dimensions(table,fs)
        self.assertNotIn('component',fs[0]['source']['normalization']['dimensions'])
        self.assertEqual(fs[1]['source']['normalization']['dimensions'],{'composition':'component','component':'Named component'})
        self.assertNotIn('component',fs[2]['source']['normalization']['dimensions'])

    def test_reapplication_removes_only_program_generated_empty_dimensions(self):
        table={'rows':[['项目','2024'],['  \n','12'],['Total','12']]}
        f=fact('custom','',dimensions={'source_line':2,'composition':'component','component':'','region':'Asia'})
        n=f['source']['normalization'];n['source_dimension_evidence']={'composition':{'row':2,'column':1,'text':'','total_rows':[3]}}
        apply_source_dimensions(table,[f])
        self.assertEqual(n['dimensions'],{'source_line':2,'region':'Asia'})
        self.assertNotIn('source_dimension_evidence',n)
        before=copy.deepcopy(f);apply_source_dimensions(table,[f]);self.assertEqual(f,before)


class ColumnMeaningTests(unittest.TestCase):
    def test_gross_allowance_and_net_keep_original_ids_in_both_languages(self):
        for headers,label in [(['账面余额','跌价准备','账面价值'],'存货'),
                              (['Gross carrying amount','Impairment allowance','Net carrying amount'],'Inventories')]:
            table={'rows':[['项目',*headers],[label,'12','12','12']]}
            ids=['inventory_gross_carrying_amount','inventory_write_down_allowance','inventory_net_carrying_amount']
            fs=[fact(metric,label,column=c,dimensions={'financial_item':'inventory'}) for c,metric in enumerate(ids,2)]
            review=apply_metric_normalization(table,fs)
            self.assertEqual(len(review),3)
            apply_source_dimensions(table,fs)
            self.assertEqual([f['metric'] for f in fs],ids)
            for f in fs:
                self.assertNotIn('financial_item',f['source']['normalization'].get('dimension_roles',{}))

    def test_gross_alias_cannot_become_inventory_even_with_only_one_measure(self):
        for header in ['期末账面余额','期末跌价准备','期末账面价值','本期增加','本期减少','本期变动','年末其他计量方式']:
            table={'rows':[['项目',header],['库存商品','12']]}
            f=fact('original_measure','库存商品')
            apply_metric_normalization(table,[f]);self.assertEqual(f['metric'],'original_measure',header)

    def test_simple_period_columns_still_map_and_unknown_columns_do_not(self):
        for header in ['2024年12月31日','本期期末数','2024（调整后）','As at June 30, 2024']:
            table={'rows':[['项目',header],['存货','12']]}
            f=fact('inventories','存货');apply_metric_normalization(table,[f])
            self.assertEqual(f['metric'],'inventory',header)
        f=fact('custom_inventory','存货')
        apply_metric_normalization({'rows':[['项目','Different measure'],['存货','12']]},[f])
        self.assertEqual(f['metric'],'custom_inventory')

    def test_repeated_metric_label_is_not_a_net_amount_column(self):
        label='经营活动产生的现金流量净额'
        table={'rows':[['项目','2024年'],[label,'12']]}
        f=fact('operating_cash_flow_net',label,column_label=label)
        apply_metric_normalization(table,[f]);self.assertEqual(f['metric'],'operating_cash_flow')
        table={'rows':[['','For the Six months Ended June 30,'],['','(in millions, except percentages)'],['Profit for the period','12']]}
        f=fact('profit_for_the_period','Profit for the period',row=3)
        apply_metric_normalization(table,[f]);self.assertEqual(f['metric'],'net_profit')

    def test_movement_neighbor_does_not_change_the_period_balance_column(self):
        table={'rows':[['项目','期末余额','变动金额'],['存货','12','2']]}
        fs=[fact('original_balance','存货'),fact('original_change','存货',column=3,value='2')]
        apply_metric_normalization(table,fs)
        self.assertEqual([f['metric'] for f in fs],['inventory','original_change'])

    def test_shifted_header_does_not_erase_movement_and_profit_impact(self):
        table={'rows':[['','项目名称','','','期初余额','','','期末余额','','','当期变动','','','对当期利润的影响金额',''],
                       ['其他权益工具投资','','','12','','','14','','','2','','','1','','']]}
        ids=['instrument_opening','instrument_closing','instrument_change','instrument_profit_impact']
        fs=[fact(metric,'其他权益工具投资',column=c) for metric,c in zip(ids,[4,7,10,13])]
        review=apply_metric_normalization(table,fs)
        self.assertEqual([f['metric'] for f in fs],ids);self.assertEqual(len(review),4)

    def test_bad_previous_normalization_is_reverted_and_second_apply_is_stable(self):
        table={'rows':[['项目','账面价值'],['库存商品','12']]}
        f=fact('finished_goods_inventory','库存商品')
        n=f['source']['normalization']
        n['metric_aliases']=['inventory_net_carrying_amount']
        n['metric_normalization']={'version':'source-metric-1','canonical_metric':'finished_goods_inventory','evidence':{'axis':'row','label':'库存商品'}}
        n['dimension_roles']={'financial_item':'descriptive'}
        n['dimensions']={'financial_item':'finished_goods_inventory'}
        apply_source_dimensions(table,[f])
        self.assertEqual(f['metric'],'inventory_net_carrying_amount')
        self.assertNotIn('metric_normalization',n)
        self.assertNotIn('dimension_roles',n)
        before=copy.deepcopy(f);apply_source_dimensions(table,[f]);self.assertEqual(f,before)

    def test_canonical_rows_do_not_overwrite_matrix_row_identity(self):
        table={'rows':[['项目','账面余额','跌价准备','账面价值'],['库存商品','12','2','10']]}
        rows=[{'row':2,'attributes':{'metric':'inventory_profile'}}]
        self.assertEqual(canonical_rows(table,rows),rows)


if __name__=='__main__':unittest.main()

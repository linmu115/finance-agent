import copy
import unittest
from types import SimpleNamespace

from service.dimension_semantics import classify_dimensions, dimensions_ok, preferred_version
from service.document_availability import describe_availability
from service.metric_normalization import apply_metric_normalization


def fact(metric, label, value='12', dimensions=None, column=2, row=2, column_label=None):
    return {'company': 'A公司', 'metric': metric, 'period': '2024-FY', 'scope': 'consolidated_CAS',
            'currency': 'CNY', 'raw_unit': '元', 'value': value,
            'source': {'table_id': 'd:t1', 'row': row, 'column': column,
                       'normalization': {'row_label': label, 'column_label': column_label,
                                         'dimensions': dimensions or {}, 'statement': 'notes', 'restatement': 'original', 'unit_kind': 'money'}}}


class SourceIdentityTests(unittest.TestCase):
    def test_disclosed_deducted_profit_keeps_original_id_and_read_role(self):
        label = '归属于上市公司股东的扣除非经常性损益的净利润'
        table = {'rows': [['主要会计数据', '2024年'], [label, '12']]}
        f = fact('net_profit_parent_ex_nonrecurring', label, dimensions={'financial_item': 'net_profit_excluding_nonrecurring'})
        apply_metric_normalization(table, [f]); classify_dimensions(table, [f])
        self.assertEqual(f['metric'], 'net_profit_parent_ex_nonrecurring')
        self.assertNotIn('metric_aliases', f['source']['normalization'])
        self.assertTrue(dimensions_ok(f))  # existing concept aliases work without rewriting IDs
        before = copy.deepcopy(f)
        apply_metric_normalization(table, [f]); classify_dimensions(table, [f])
        self.assertEqual(f, before)

    def test_segment_product_region_are_not_descriptive(self):
        table = {'rows': [['项目', '2024'], ['营业收入', '12']]}
        for key in ('segment', 'product', 'region', 'related_party', 'component'):
            f = fact('revenue', '营业收入', dimensions={'financial_item': 'revenue', key: 'A'})
            classify_dimensions(table, [f])
            self.assertFalse(dimensions_ok(f), key)

    def test_single_unknown_dimension_and_wrong_metric_remain_excluded(self):
        table = {'rows': [['项目', '2024'], ['营业收入', '12']]}
        for metric, item in [('revenue', 'unknown_category'), ('net_profit_parent', 'revenue')]:
            f = fact(metric, '营业收入', dimensions={'financial_item': item})
            classify_dimensions(table, [f]); self.assertFalse(dimensions_ok(f))

    def test_multiple_distinct_values_cannot_be_excused_as_description(self):
        table = {'rows': [['项目', '2024'], ['营业收入', '12'], ['营业收入', '8']]}
        fs = [fact('revenue', '营业收入', value, {'financial_item': 'revenue'}, row=row) for row, value in [(2,'12'),(3,'8')]]
        classify_dimensions(table, fs)
        self.assertFalse(any(dimensions_ok(f) for f in fs))

    def test_ratio_change_and_purchase_columns_keep_their_meaning(self):
        for header, metric in [('本期变动', 'asset_change'), ('本期购买金额', 'purchases'), ('本期出售/赎回金额', 'disposals')]:
            table = {'rows': [['项目', header], ['交易性金融资产', '12']]}
            f = fact(metric, '交易性金融资产', column_label=header)
            before = copy.deepcopy(f); review = apply_metric_normalization(table, [f])
            self.assertEqual(f, before); self.assertEqual(len(review), 1)
        table = {'rows': [['项目', '同比增长'], ['营业收入', '12']]}
        f = fact('revenue_growth', '营业收入'); f['currency']='percent'; f['raw_unit']='%'
        f['source']['normalization']['unit_kind']='ratio_percent'
        apply_metric_normalization(table, [f]); self.assertEqual(f['metric'], 'revenue_growth')

    def test_parallel_table_does_not_inherit_other_row_label(self):
        table = {'rows': [['项目','本年','项目','本年'], ['营业收入','12','投资收益','8']]}
        f = fact('custom_investment', '投资收益', value='8', column=4)
        apply_metric_normalization(table, [f]); self.assertEqual(f['metric'], 'custom_investment')
        f = fact('unknown_detail', '未识别明细', value='8', column=4)
        apply_metric_normalization(table, [f]); self.assertEqual(f['metric'], 'unknown_detail')

    def test_period_balance_column_next_to_change_column_can_normalize(self):
        table={'rows':[['项目','本期期末数','变动比例(%)'],['合同负债','12','3']]}
        f=fact('balance_sheet_item','合同负债',column_label='本期期末余额')
        apply_metric_normalization(table,[f]); self.assertEqual(f['metric'],'balance_sheet_item')

    def test_explicit_metric_column_is_supported(self):
        table = {'rows': [['公司', '净利润'], ['子公司甲', '12']]}
        f = fact('subsidiary_net_profit', '子公司甲', dimensions={'subsidiary':'甲'}, column_label='净利润')
        apply_metric_normalization(table, [f]); classify_dimensions(table, [f])
        self.assertEqual(f['metric'], 'subsidiary_net_profit'); self.assertFalse(dimensions_ok(f))

    def test_version_is_not_a_business_slice_and_restated_is_selected(self):
        table = {'rows': [['项目','调整前','调整后'], ['营业收入','12','15']]}
        a = fact('revenue','营业收入',dimensions={'version':'original'})
        b = fact('revenue','营业收入',value='15',dimensions={'version':'restated'},column=3)
        b['source']['normalization']['restatement']='restated'
        classify_dimensions(table, [a,b])
        self.assertTrue(all(dimensions_ok(f) for f in [a,b]))
        self.assertEqual(preferred_version([a,b]), [b])


class AvailabilityTests(unittest.TestCase):
    def test_failed_run_has_partial_usable_document_and_disjoint_counts(self):
        doc = {'document_id':'d', 'sha256':'sha', 'state':'failed', 'fact_count':12}
        part = {'document_id':'d', 'tables':[1,2,3,4], 'core_tables':[1,2], 'profile_revision':'p', 'completed_tables':[], 'deferred_tables':{'3':{'reason':'mapping_error'}}}
        states = [{'mode':'script_cleaning','processing_id':'checkpoint','documents':[part]}]
        receipts = [{'script_table':i,'status':'completed','document_sha256':'sha','profile_revision':'p'} for i in [1,2]]
        result = describe_availability(doc,states,receipts)
        self.assertEqual(result['state'],'partial')
        self.assertEqual(result['processing_state'],'failed')
        self.assertEqual(result['status_label'],'核心表已完成 / 1 张待处理 / 1 张搁置')
        self.assertTrue(result['ingestion']['analysis_available'])
        self.assertEqual(result['ingestion']['tables_completed'],2)
        self.assertEqual(doc['state'],'failed')

    def test_conflict_return_and_superseded_receipt_are_not_complete(self):
        doc = {'document_id':'d','sha256':'sha','state':'failed','fact_count':12}
        states = [{'mode':'script_cleaning','processing_id':'c','documents':[{'document_id':'d','tables':[1,2],'core_tables':[1,2]}]}]
        receipts = [{'script_table':1,'status':'failed','document_sha256':'sha'}, {'script_table':2,'status':'completed','document_sha256':'sha','superseded_by':'new'}]
        r=describe_availability(doc,states,receipts)
        self.assertEqual(r['ingestion']['tables_completed'],0)
        self.assertEqual(r['ingestion']['tables_pending'],2)
        self.assertFalse(r['ingestion']['core_complete'])

    def test_parse_failure_without_submitted_work_remains_failure(self):
        doc={'document_id':'d','sha256':'sha','state':'failed','fact_count':0}
        self.assertEqual(describe_availability(doc,[],[]),doc)

    def test_completed_old_attempt_does_not_mask_current_reprocessing(self):
        doc={'document_id':'d','sha256':'sha','state':'failed','fact_count':2}
        old={'document_id':'d','tables':[1],'completed_tables':[1],'profile_revision':'old'}
        current={'document_id':'d','tables':[1,2],'completed_tables':[],'profile_revision':'current'}
        states=[{'mode':'script_cleaning','processing_id':'old','state':'completed','documents':[old]},
                {'mode':'script_cleaning','processing_id':'current','state':'failed','documents':[current]}]
        receipts=[{'script_table':1,'status':'completed','document_sha256':'sha','profile_revision':'current'}]
        result=describe_availability(doc,states,receipts)
        self.assertEqual(result['ingestion']['processing_id'],'current')
        self.assertEqual(result['ingestion']['tables_completed'],1)
        self.assertEqual(result['ingestion']['tables_pending'],1)

    def test_research_pages_and_committed_review_are_not_reported_as_clean_completion(self):
        doc={'document_id':'d','sha256':'sha','state':'failed','fact_count':2}
        part={'document_id':'d','tables':[1],'core_tables':[1],
              'text_coverage':{'pages_total':3,'pages_reviewed':2}}
        states=[{'mode':'script_cleaning','processing_id':'c','documents':[part]}]
        receipts=[{'script_table':1,'status':'needs_review','document_sha256':'sha'}]
        result=describe_availability(doc,states,receipts)
        self.assertEqual(result['state'],'partial')
        self.assertIn('正文 2/3 页',result['status_label'])
        part['text_coverage']['pages_reviewed']=3
        result=describe_availability(doc,states,receipts)
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(result['ingestion']['availability'],'complete')


class QuarterCandidateTests(unittest.TestCase):
    def test_shifted_heading_does_not_append_empty_candidate_or_hide_real_conflict(self):
        from service.workpaper_periods import period_inputs
        from service.period_algebra import derive_period_series
        t={'table_id':'d:t1','page':1,'rows':[['','','第一季度','','第二季度','','第三季度','','第四季度'],
                                          ['营业收入','12','','13','','14','','15','']]}
        fs=[]
        for q,value,column in [(1,'12',2),(2,'13',4),(3,'14',6),(4,'15',8)]:
            f=fact('revenue','营业收入',value,column=column)
            f['period']=f'2024-Q{q}';f['document_id']='d';f['source_ref']=f.pop('source')
            f['source_ref']['normalization'].update(period_start=f'2024-{(q-1)*3+1:02}-01',period_end=f'2024-{q*3:02}-{30 if q in (2,3) else 31}')
            fs.append(f)
        st=SimpleNamespace(facts=fs,company='A公司',currency='CNY')
        d=SimpleNamespace(tabs=[t],year='2024',doc='d',document={},unknown=[],applies=lambda table:True,
                          quantity=lambda *args:self.fail('must reuse mapped cell, not read shifted blank'))
        items,unknown=period_inputs(st,d)
        self.assertEqual(len(items),4);self.assertEqual(unknown,[])
        conflict=copy.deepcopy(fs[0]);conflict['value']='18';st.facts=[*fs,conflict]
        items,_=period_inputs(st,d);series=derive_period_series(items,'d')
        q1=next(x for x in series['quarters'] if x['period']=='2024-Q1')
        self.assertIsNone(q1['quantity']['value'])
        self.assertIn('不同数值',q1['quantity']['source']['missing_reason'])


if __name__ == '__main__':
    unittest.main()

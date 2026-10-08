import copy
import unittest

from service.cleaning_sdk import Cleaner


def cleaner(tables):
    result=Cleaner.__new__(Cleaner)
    result.source={'company':'Example'}
    result.tables={t['index']:copy.deepcopy(t) for t in tables}
    result.results={}
    return result


def map_rows(c,index,metrics,**kwargs):
    c.map_table(index,[{'column':2,'period':'2024-FY'}],metrics=metrics,
                company='Example',statement='notes',scope='consolidated_CAS',
                currency='CNY',unit='元',**kwargs)
    return c.results[int(str(index).lower().removeprefix('t'))]


class SdkLabelTests(unittest.TestCase):
    def test_only_whitespace_changes_match_and_source_is_preserved(self):
        label='公允价值\n变动\t损失（收益以“－”号填\r\n列）'
        c=cleaner([{'index':254,'rows':[[label,'28,153,114.85']]}])
        result=map_rows(c,'t254',{'公允价值变动\u3000损失（收益以“－”号填列）':'fair_value_loss'})
        self.assertEqual(result['rows'][0]['attributes']['metric'],'fair_value_loss')
        self.assertEqual(result['rows'][0]['attributes']['label'],label)
        self.assertEqual(result['rows'][0]['row'],1)
        self.assertEqual(c.tables[254]['rows'],[[label,'28,153,114.85']])

    def test_exact_mappings_keep_priority_when_whitespace_keys_differ(self):
        c=cleaner([{'index':1,'rows':[['应 收款','1']]}])
        result=map_rows(c,1,{'应收款':'other','应 收款':'exact'})
        self.assertEqual(result['rows'][0]['attributes']['metric'],'exact')

    def test_non_whitespace_changes_are_not_fuzzy_matches(self):
        for source,key in [('损失（收益）','损失(收益)'),('资产','负债'),('净利润','利润')]:
            with self.subTest(source=source,key=key):
                c=cleaner([{'index':1,'rows':[[source,'1']]}])
                self.assertIn('needs an explicit metric',map_rows(c,1,{key:'wrong'})['mapping_error'])

    def test_conflicting_whitespace_aliases_are_not_arbitrarily_selected(self):
        c=cleaner([{'index':1,'rows':[['应\n收款','1']]}])
        result=map_rows(c,1,{'应收款':'one','应 收款':'two'})
        self.assertIn('Ambiguous whitespace-only',result['mapping_error'])
        self.assertEqual(result['rows'],[])

    def test_equivalent_whitespace_aliases_work(self):
        c=cleaner([{'index':1,'rows':[['应\n收款','1']]}])
        self.assertEqual(map_rows(c,1,{'应收款':'same','应 收款':'same'})['rows'][0]['attributes']['metric'],'same')

    def test_row_overrides_keep_working_without_metrics(self):
        c=cleaner([{'index':1,'rows':[['应\n收款','1']]}])
        self.assertEqual(map_rows(c,1,{},row_overrides={1:{'metric':'receivable'}})['rows'][0]['attributes']['metric'],'receivable')

    def test_neighbor_hint_handles_both_offset_directions_without_retargeting(self):
        for target,neighbor in [(254,255),(256,255)]:
            with self.subTest(target=target):
                c=cleaner([{'index':target,'rows':[['不相关项目','1']]},
                           {'index':neighbor,'rows':[['取得子公司\n现金','2']]}])
                before=copy.deepcopy(c.tables)
                result=map_rows(c,f'T{target}',{'取得子公司现金':'acquisition_cash'})
                self.assertIn(f'候选应为 t{neighbor}',result['mapping_error'])
                self.assertIn('第 1 行',result['mapping_error'])
                self.assertEqual(set(c.results),{target})
                self.assertEqual(result['rows'],[])
                self.assertEqual(c.tables,before)

    def test_neighbor_hint_lists_both_candidates_instead_of_choosing(self):
        c=cleaner([{'index':i,'rows':[[label,'1']]} for i,label in [(1,'应收款'),(2,'其他项目'),(3,'应收款')]])
        result=map_rows(c,2,{'应收款':'receivable'})
        self.assertIn('t1（',result['mapping_error']);self.assertIn('t3（',result['mapping_error'])
        self.assertEqual(set(c.results),{2})

    def test_shared_label_does_not_suggest_a_neighbor_with_no_better_match(self):
        c=cleaner([{'index':1,'rows':[['其他','1']]},
                   {'index':2,'rows':[['其他','1'],['缺失项目','2']]}])
        self.assertNotIn('偏移',map_rows(c,2,{'其他':'other'})['mapping_error'])

    def test_no_hint_for_nonadjacent_or_unmatched_tables(self):
        c=cleaner([{'index':2,'rows':[['缺失项目','1']]},
                   {'index':3,'rows':[['不同项目','2']]},
                   {'index':4,'rows':[['应收款','3']]}])
        self.assertNotIn('偏移',map_rows(c,2,{'应收款':'receivable'})['mapping_error'])

    def test_neighbor_hint_respects_label_column(self):
        c=cleaner([{'index':2,'rows':[['分部','缺失项目','1']]},
                   {'index':3,'rows':[['分部','应收款','2']]}])
        self.assertIn('候选应为 t3',map_rows(c,2,{'应收款':'receivable'},label_column=2)['mapping_error'])

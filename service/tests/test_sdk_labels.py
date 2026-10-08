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

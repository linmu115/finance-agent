import copy
import unittest
from service.cleaning_rules import context, source_columns
from service.source_semantics import apply_source_semantics
from service.source_table_blocks import nonrecurring_blocks
from service.tests.test_source_semantics import fact


def fixture(heading='非经常性损益项目及金额', minority=True, report='2024年年度报告'):
    a={'index':0,'page':1,'rows':[['非经常性损益项目','2024年金额','2023年金额'],['政府补助','100','90']]}
    b={'index':1,'page':2,'rows':[[('减：少数股东权益影响额（税后）' if minority else '减：所得税影响额'),'2','1'],['合计','98','89']]}
    c={'index':2,'page':2,'rows':[['其他表项目','80','70']]}
    return {'report_year':2024,'pages':[{'page':1,'text':report+'\n'+heading},{'page':2,'text':report}], 'tables':[a,b,c]}


class NonrecurringBlockTests(unittest.TestCase):
    def apply(self,p,t,f):apply_source_semantics(p,t,[f],context(p,t))

    def test_consolidated_scope_can_be_grounded_in_continuation(self):
        p=fixture();f=fact(2,scope='unspecified_CAS')
        self.apply(p,p['tables'][0],f)
        self.assertEqual(f['scope'],'consolidated_CAS')
        self.assertIn('少数股东',f['source']['normalization']['source_semantics']['scope']['quote'])

    def test_explicit_parent_chapter_has_precedence(self):
        p=fixture('母公司非经常性损益项目及金额');f=fact(2,scope='unspecified_CAS')
        self.apply(p,p['tables'][0],f);self.assertEqual(f['scope'],'parent_CAS')

    def test_insufficient_scope_evidence_does_not_guess(self):
        p=fixture(minority=False);f=fact(2,scope='unspecified_CAS');old=copy.deepcopy(f)
        self.apply(p,p['tables'][0],f);self.assertEqual(f,old)

    def test_next_block_does_not_inherit_previous_parent_heading(self):
        p=fixture();p['pages'][0]['text']='母公司非经常性损益项目及金额\n旧表已结束\n合并非经常性损益项目及金额'
        f=fact(2,scope='unspecified_CAS');self.apply(p,p['tables'][0],f)
        self.assertEqual(f['scope'],'consolidated_CAS')

    def test_headerless_continuation_inherits_period_scope_and_stops_at_total(self):
        p=fixture();f=fact(1,3,period='2024-FY',scope='unspecified_CAS')
        self.apply(p,p['tables'][1],f)
        self.assertEqual((f['scope'],f['period']),('consolidated_CAS','2023-FY'))
        self.assertEqual(f['source']['normalization']['period_start'],'2023-01-01')
        original=copy.deepcopy(f);self.apply(p,p['tables'][1],f);self.assertEqual(f,original)
        next_fact=fact(1,scope='unspecified_CAS');old=copy.deepcopy(next_fact)
        self.apply(p,p['tables'][2],next_fact);self.assertEqual(next_fact,old)
        self.assertEqual([t['index'] for t in nonrecurring_blocks(p)[0]['tables']],[0,1])
        columns=source_columns(p['tables'][1],p,context(p,p['tables'][1]))
        self.assertEqual([c['period'] for c in columns],['2024-FY','2023-FY'])

    def test_interim_continuation_keeps_report_duration(self):
        p=fixture(report='2024年半年度报告');f=fact(1,3,period='unknown',scope='unspecified_CAS')
        self.apply(p,p['tables'][1],f);self.assertEqual(f['period'],'2023-H1')

    def test_new_header_or_section_closes_unfinished_block(self):
        for change in ('header','section'):
            p=fixture();p['tables'][1]['rows']=p['tables'][1]['rows'][:1]
            if change=='header':p['tables'][2]['rows'][0]=['项目','2024年金额','2023年金额']
            else:
                p['tables'][2]['page']=3
                p['pages'].append({'page':3,'text':'二、其他事项'})
            self.assertEqual([t['index'] for t in nonrecurring_blocks(p)[0]['tables']],[0,1])


if __name__=='__main__':unittest.main()

import copy
import json
import unittest
from service.tests import test_script_cleaning as fixtures
from service.accounting_basis import identify, resolve, apply_basis
from service.cleaning_rules import draft, context, shape, lookup
from service.standard_metrics import standard_metric


class CleaningReuseTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def prepare(self, rows, text, year=2025):
        _,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed)
        parsed.update(company='Test',report_year=year)
        parsed['pages'][0]['text']=text
        parsed['tables'][0]['rows']=rows
        self.s._persist_prepared('p',self.did,parsed)
        return parsed

    def test_basis_requires_current_source_and_grounded_override(self):
        parsed={'pages':[{'page':1,'text':'本财务报表按照企业会计准则编制。'}]}
        self.assertEqual(identify(parsed)['basis'],'CAS')
        with self.assertRaisesRegex(ValueError,'accounting_basis_not_supported'):
            resolve(parsed,{'basis':'IFRS','evidence':{'page':1,'quote':'本财务报表按照企业会计准则编制。'}})
        self.assertEqual(identify({'pages':[{'page':1,'text':'A股 2025 年年度报告'}]})['basis'],'unknown')
        item={'schema':{'scope':'parent_IFRS'},'rows':[{'row':1,'attributes':{'columns_json':[{'scope':'consolidated_IFRS'}]}}]}
        corrected=apply_basis(item,identify(parsed))
        self.assertEqual(corrected['schema']['scope'],'parent_CAS')
        self.assertEqual(json.loads(corrected['rows'][0]['attributes']['columns_json'])[0]['scope'],'consolidated_CAS')
        self.assertEqual(item['schema']['scope'],'parent_IFRS')

    def test_exact_standard_labels_keep_financial_distinctions(self):
        expected={'货币资金':'cash','营业收入':'revenue','一、营业总收入':'total_operating_revenue',
                  '减：所得税费用':'income_tax_expense','其中：应收利息':'interest_receivable',
                  '经营活动产生的现金流量净额':'operating_cash_flow','Property and equipment':'property_plant_equipment',
                  '归属于母公司所有者权益（或股东权益）合计':'equity_parent'}
        for label,metric in expected.items():self.assertEqual(standard_metric(label),metric,label)
        self.assertIsNone(standard_metric('客户甲的自定义业务'))

    def test_standard_auto_commit_uses_same_source_validator_and_records_rule_version(self):
        parsed=self.prepare([['项目','期末余额','期初余额'],['库存现金','120.50','90'],['银行存款','800','700'],['合计','920.50','790']],
                            '按照企业会计准则编制。\n七、合并财务报表项目注释\n1、货币资金\n单位：元 币种：人民币\n120.50')
        result=self.s.begin_script_cleaning('p',[self.did],'auto','fixture')['data']
        self.assertEqual(result['coverage']['tables_completed'],1)
        self.assertEqual(result['fact_count'],6)
        self.assertEqual(result['document_progress'][0]['rule_reuse']['standard_tables'],[0])
        with self.s.store.connect() as db:
            fact=dict(db.execute('select * from facts limit 1').fetchone())
            rules=[dict(r) for r in db.execute('select * from cleaning_rules')]
        self.assertEqual(fact['scope'],'consolidated_CAS')
        self.assertTrue(json.loads(fact['source_json'])['normalization']['cleaning_rule']['version'])
        encoded=json.dumps(rules,ensure_ascii=False)
        for secret in ['120.50','920.50','库存现金','Test',self.did]:self.assertNotIn(secret,encoded)
        # A signature match does not excuse a newly introduced source amount.
        parsed['tables'][0]['rows'].append(['新项目','66','77'])
        self.s._persist_prepared('p',self.did,parsed)
        resumed=self.s.begin_script_cleaning('p',[self.did],'changed','fixture')['data']
        self.assertEqual(resumed['pending_tables'][self.did],[0])

    def test_learned_rule_rebinds_company_year_and_values_without_cross_project_data(self):
        parsed=self.prepare([['项目','2025','2024'],['Custom recurring fee','123','90']],
                            '合并利润表\n单位：元\n123')
        self.pid=self.s.begin_script_cleaning('p',[self.did],'learn','fixture')['data']['processing_id']
        payload={'tables':[{'index':0,'schema':{'company':'Test','statement':'income','scope':'consolidated_unknown','currency':'CNY','unit':'元',
                  'columns_json':json.dumps([{'column':2,'period':'2025-FY'},{'column':3,'period':'2024-FY'}]),
                  'skipped_rows_json':json.dumps([{'row':1,'reason':'header'}])},
                  'rows':[{'row':2,'attributes':{'metric':'recurring_service_fee','label':'Custom recurring fee'}}]}]}
        self.s.commit_cleaning_result('p',self.pid,self.job(payload))
        p=self.root/'uploads/second.csv';p.write_text('other source')
        did=self.s.register_document('q',str(p),'second.csv')['data']['document_id']
        parsed=copy.deepcopy(parsed);parsed['company']='Second';parsed['report_year']=2026
        parsed['tables'][0]['rows']=[['项目','2026','2025'],['Custom recurring fee','456','200']]
        parsed['pages'][0]['text']='合并利润表\n单位：万元\n456'
        self.s._persist_prepared('q',did,parsed)
        result=self.s.begin_script_cleaning('q',[did],'reuse','fixture')['data']
        self.assertEqual(result['coverage']['tables_completed'],1)
        self.assertEqual(result['document_progress'][0]['rule_reuse']['completed_tables'],[0])
        records=self.s.query_financial_data('q')['data']['items']
        self.assertEqual({r['value'] for r in records},{'4560000','2000000'})
        self.assertEqual({r['period'] for r in records},{'2026-FY','2025-FY'})
        self.assertEqual({r['company'] for r in records},{'Second'})

    def test_core_order_and_local_failure_progress(self):
        parsed=self.prepare([['项目','2025','2024'],['未知','123','90']],'1、其他事项\n单位：元\n123')
        parsed['pages'].append({'page':2,'text':'合并利润表\n单位：元\n456','width':100,'height':100})
        parsed['tables'].append({'index':1,'page':2,'rows':[['项目','2025','2024'],['未知核心','456','91']],'cells':{}})
        self.s._persist_prepared('p',self.did,parsed)
        result=self.s.begin_script_cleaning('p',[self.did],'core','fixture')['data']
        self.assertEqual(result['next_batch']['tables'][0]['index'],1)
        progress=self.s.get_cleaning_progress('p',result['processing_id'])['data']
        self.assertEqual(progress['unattempted_tables'][self.did],[0,1])
        self.assertEqual(result['document_progress'][0]['coverage']['core_tables_total'],1)

    def test_complex_matrix_total_is_not_assumed_to_be_note_asset(self):
        parsed=self.prepare([['类别','期初余额','本期变动金额','期末余额'],['坏账准备','12','3','15'],['合计','12','3','15']],
                            '5、应收账款\n单位：元\n12')
        mapping=draft(parsed,parsed['tables'][0],'Test',identify(parsed))
        self.assertIn(3,mapping['unmapped_rows'])


if __name__=='__main__':unittest.main()

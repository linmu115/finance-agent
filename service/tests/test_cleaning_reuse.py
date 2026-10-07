import copy
import json
import unittest
from service.tests import test_script_cleaning as fixtures
from service.accounting_basis import identify, resolve, apply_basis
from service.cleaning_rules import draft, context, shape, lookup, compile_rule
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

    def test_continued_statement_preserves_first_data_row_and_parent_scope(self):
        parsed=self.prepare([['项目','附注','2025 年12 月31 日','2024 年12 月31 日'],['货币资金','1','800','700']],
                            '2025 年年度报告\n合并资产负债表\n单位：元\n800')
        parsed['report_year']=None
        parsed['pages'].append({'page':2,'text':'银行存款 12 900 600','width':100,'height':100})
        table={'index':1,'page':2,'rows':[['银行存款','12','900','600']],'cells':{}}
        parsed['tables'].append(table)
        mapped=draft(parsed,table,'Test',identify(parsed))
        self.assertEqual(mapped['rows'][0]['row'],1)
        self.assertEqual(json.loads(mapped['schema']['columns_json'])[0]['period'],'2025-12-31')
        self.assertEqual(json.loads(mapped['schema']['skipped_rows_json']),[])
        # The same balance occurs above a new parent-company heading.
        parsed['pages'][1].update(text='900\n母公司资产负债表\n单位：元\n900',words=[
            {'text':'900','bbox':[0,0,20,10]}, {'text':'母公司资产负债表','bbox':[0,20,80,30]},
            {'text':'单位：元','bbox':[0,40,60,50]}, {'text':'900','bbox':[0,60,20,70]}])
        table['bbox']=[0,55,100,100]
        self.assertEqual(context(parsed,table)['scope'],'parent')

    def test_equity_movements_have_separate_metrics_periods_and_source_components(self):
        parsed=self.prepare([['项目','2025 年度','',''],['','股本','未分配利润','所有者权益合计'],
                            ['一、上年年末余额','100','200','300'],['三、本期增减变动金额（减少以“－”号填列）','0','40','40'],
                            ['四、本期期末余额','100','240','340']],
                            '母公司所有者权益变动表\n单位：元\n100')
        mapped=draft(parsed,parsed['tables'][0],'Test',identify(parsed))
        self.assertEqual(mapped['unmapped_rows'],[])
        self.assertEqual([r['attributes']['metric'] for r in mapped['rows']],['equity_prior_year_closing','equity_movement','equity_closing'])
        cols=json.loads(mapped['rows'][0]['attributes']['columns_json'])
        self.assertEqual([c['metric'] for c in cols],['share_capital','retained_earnings','equity'])
        self.assertEqual(cols[0]['period'],'2024-12-31')

    def test_packed_ifrs_cashflow_uses_standard_labels_and_keeps_missing_slots(self):
        parsed=self.prepare([['','Six months ended 30 June',''],['','2025','2024'],['','RMB’000','RMB’000'],
                             ['Cash flows from operating activities\nCash used in operations\nIncome tax paid\nNet cash used in operating activities','','(80)\n–\n(80)'],
                             ['','(100)',''],['','(2)',''],['','(102)','']],
                            'Consolidated Statement of Cash Flows\nFor the six months ended 30 June 2025\nIFRS')
        mapped=draft(parsed,parsed['tables'][0],'Test',identify(parsed))
        self.assertEqual(mapped['unmapped_rows'],[])
        definitions=[c for r in mapped['rows'] for c in json.loads(r['attributes']['columns_json'])]
        self.assertEqual(len(definitions),5)
        self.assertEqual({c['period'] for c in definitions},{'2025-H1','2024-H1'})
        self.assertEqual({c['metric'] for c in definitions},{'cash_used_in_operations','taxes_paid','operating_cash_flow'})

    def test_income_statement_distinguishes_finance_interest_from_operating_interest(self):
        parsed=self.prepare([['项目','2025','2024'],['利息收入','100','90'],['财务费用','8','7'],['其中：利息费用','10','9'],['利息收入','2','2']],
                            '合并利润表\n单位：元\n100')
        mapped=draft(parsed,parsed['tables'][0],'Test',identify(parsed))
        interest=[r for r in mapped['rows'] if r['attributes']['metric']=='interest_income']
        self.assertNotIn('dimensions_json',interest[0]['attributes'])
        self.assertEqual(json.loads(interest[1]['attributes']['dimensions_json']),{'statement_section':'finance_expenses'})
        self.assertIsNone(compile_rule(parsed,parsed['tables'][0],{'schema':mapped['schema'],'mapping':mapped['rows'],'issues':[],'exclusion_reason':None}))

    def test_rule_keeps_period_logic_and_rebinds_dimension_text_without_source_quotes(self):
        parsed=self.prepare([['项目','2025','2024'],['某客户','100','90']], '合并利润表\n单位：元\n100')
        item={'schema':{'columns_json':json.dumps([{'column':2,'period':'2025-FY','start':'2025-01-01','end':'2025-12-31','label':'不应保存的原文','unit':'元','currency':'CNY'}, {'column':3,'period':'2024-FY'}]),'unit':'元','currency':'CNY'},
              'mapping':[{'row':2,'attributes':{'metric':'service_revenue','dimensions_json':{'customer':'某客户'}}}],
              'issues':[],'exclusion_reason':None}
        rule=compile_rule(parsed,parsed['tables'][0],item)
        encoded=json.dumps(rule,ensure_ascii=False)
        self.assertNotIn('某客户',encoded);self.assertNotIn('不应保存的原文',encoded)
        parsed['report_year']=2026
        parsed['tables'][0]['rows'][0]=['项目','2026','2025']
        parsed['pages'][0]['text']='合并利润表\n单位：万元\n100'
        mapped=draft(parsed,parsed['tables'][0],'Next company',identify(parsed),rule)
        columns=json.loads(mapped['schema']['columns_json'])
        self.assertEqual(columns[0]['start'],'2026-01-01')
        self.assertNotIn('unit',columns[0]);self.assertEqual(mapped['schema']['unit'],'万元')
        self.assertEqual(json.loads(mapped['rows'][0]['attributes']['dimensions_json']),{'customer':'某客户'})

    def test_standard_inventory_label_corrects_model_translation_and_upgrades_only_affected_table(self):
        from unittest.mock import patch
        parsed=self.prepare([['项目','2025','2024'],['委托加工物资','100','90']], '单位：元\n100')
        self.pid=self.s.begin_script_cleaning('p',[self.did],'before','fixture')['data']['processing_id']
        # Reproduce the observed old mapping before this deterministic rule.
        payload={'tables':[{'index':0,'schema':self.schema,'rows':[{'row':2,'attributes':{'metric':'materials_on_consignment_inventory'}}]}]}
        with patch('service.script_cleaning.canonical_rows',side_effect=lambda table,rows,label_column=1,statement=None:rows):
            self.s.commit_cleaning_result('p',self.pid,self.job(payload))
        result=self.s.begin_script_cleaning('p',[self.did],'after','fixture')['data']
        self.assertEqual(result['pending_tables'][self.did],[])
        with self.s.store.connect() as db:
            current=[r[0] for r in db.execute('SELECT metric FROM facts WHERE document_id=?',(self.did,))]
            archived=db.execute('SELECT count(*) FROM fact_history WHERE document_id=?',(self.did,)).fetchone()[0]
        self.assertEqual(set(current),{'materials_sent_for_processing_inventory'})
        self.assertGreater(archived,0)

    def test_equity_continuation_inherits_section_but_top_level_other_resets_it(self):
        parsed=self.prepare([['项目','2025 年度',''],['','股本','所有者权益合计'],['（二）所有者投入和减少资本','20','20']],
                            '母公司所有者权益变动表\n单位：元\n20')
        parsed['pages'].append({'page':2,'text':'4．其他 10\n（六）其他 30','width':100,'height':100})
        table={'index':1,'page':2,'rows':[['4．其他','10','10'],['（六）其他','30','30']],'cells':{}}
        parsed['tables'].append(table)
        mapped=draft(parsed,table,'Test',identify(parsed))
        self.assertEqual([r['attributes']['metric'] for r in mapped['rows']],['owners_contributions_and_withdrawals_other','equity_other'])

    def test_interim_heading_inside_table_and_explicit_prior_june_date_are_preserved(self):
        parsed=self.prepare([['','Six months ended 30 June',''],['','2025','2024'],['Revenue','100','90']], '单位：元')
        mapped=draft(parsed,parsed['tables'][0],'Test',identify(parsed))
        self.assertEqual([c['period'] for c in json.loads(mapped['schema']['columns_json'])],['2025-H1','2024-H1'])
        parsed['tables'][0]['rows']=[['项目','30 June 2025','30 June 2024'],['货币资金','100','90']]
        mapped=draft(parsed,parsed['tables'][0],'Test',identify(parsed))
        self.assertEqual([c['period'] for c in json.loads(mapped['schema']['columns_json'])],['2025-06-30','2024-06-30'])

    def test_packed_row_error_before_map_table_does_not_abort_other_tables(self):
        from service.cleaning_sdk import Cleaner
        c=Cleaner.__new__(Cleaner);c.source={'company':'Test'};c.results={}
        c.tables={0:{'index':0,'rows':[['Revenue\nCost','100\n40']]},1:{'index':1,'rows':[['Revenue','80']]}}
        bad=c.packed_row(0,1,[{'column':2,'period':'2025-FY'}],[{'metric':'revenue'}])
        c.map_table(0,[],statement='income',scope='unspecified',currency='CNY',unit='元',row_overrides={1:bad})
        c.map_table(1,[{'column':2,'period':'2025-FY'}],statement='income',scope='unspecified',currency='CNY',unit='元')
        self.assertIn('2 source numbers',c.results[0]['mapping_error'])
        self.assertNotIn('mapping_error',c.results[1])


if __name__=='__main__':unittest.main()

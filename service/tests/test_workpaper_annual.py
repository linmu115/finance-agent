import copy
import json
from pathlib import Path
from decimal import Decimal as D
import tempfile
import unittest
from unittest.mock import patch

from service.core import FinanceService
from service.financial_workpapers import statement_analysis,financial_workpaper
from service.analysis_report import compile_report

FIXTURE=Path(__file__).parent/'fixtures/workpapers/annual.json'


class AnnualWorkpapersTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=FinanceService(self.tmp.name);self.s.create_project('p','generic annual')
        self.data=json.loads(FIXTURE.read_text('utf8'));self.facts=self.data['facts']
        self.doc=self.facts[0]['document_id']
        for r in self.facts:r.update(project_id='p',company='测试主体')
        with self.s.store.connect(write=True) as db:
            db.execute("INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,state,parser_version,created_at,report_year) VALUES(?,?,?,?,?,?,?,?,?,?)",(self.doc,'p','年度报告.pdf','hash','unused.pdf','application/pdf','ready','test','now',2024))
        self.save_tables()

    def save_tables(self):
        with self.s.store.connect(write=True) as db:
            db.execute('DELETE FROM source_tables')
            for t in self.data['tables']:
                db.execute('INSERT INTO source_tables VALUES(?,?,?,?,?,?,?)',(t['table_id'],self.doc,t['page'],None,'[]',json.dumps(t['rows'],ensure_ascii=False),'[]'))
                db.execute('INSERT OR REPLACE INTO pages(document_id,page,text) VALUES(?,?,?)',(self.doc,t['page'],'单位：元 币种：人民币'))

    def report(self,kind='statement_analysis'):
        with patch('service.financial_workpapers.load_facts',return_value=self.facts):
            if kind=='statement_analysis':r,records=statement_analysis(self.s,'p',self.doc);return compile_report(r,records)
            return financial_workpaper(self.s,'p',kind,document_id=self.doc)['report']

    def test_annual_window_deducted_disclosure_and_roe_basis(self):
        t=self.report()['tables'];r=t['deducted_profit']['rows'][0]
        self.assertEqual(r['key'],'2024-FY');self.assertEqual(r['disclosed'],'6011.27494592')
        self.assertEqual(D(r['residual']),0);self.assertAlmostEqual(D(r['share']),D('28.8847212568'),places=10)
        roe=t['roe']['rows'][0];self.assertEqual(roe['weighted'],'15.81');self.assertAlmostEqual(D(roe['computed']),D('15.8413007625'),places=10)
        self.assertNotEqual(roe['computed'],roe['weighted'])
        self.assertEqual(t['nonrecurring_items']['rows'][3]['2024-FY'],None)
        self.assertEqual(len(t['nonrecurring_items']['rows']),25)

    def test_complete_continuation_bridge_and_quarters(self):
        t=self.report()['tables'];rows=t['indirect_bridge']['rows']
        self.assertEqual(len(rows),40)
        self.assertEqual([D(r['amount']) for r in rows if r['direction']=='残差'],[0,0])
        investments=[r for r in rows if '投资损失' in r['item']]
        self.assertEqual([r['direction'] for r in investments],['减','加'])
        self.assertEqual([D(r['residual']) for r in t['quarterly_reconciliation']['rows']],[0]*4)
        self.assertTrue(any('Q4' in r['finding'] and '为负' in r['finding'] for r in t['observations']['rows']))

    def test_unknown_row_is_preserved_and_still_reconciled_without_guessing(self):
        t=next(t for t in self.data['tables'] if '公允价值变动损失' in t['rows'][0][0])
        t['rows'][1][0]='尚无分类规则的新调整项目'
        self.save_tables();tables=self.report()['tables']
        self.assertEqual(len(tables['unrecognized_rows']['rows']),2)
        unknown=[r for r in tables['indirect_contributions']['rows'] if r['category']=='未识别']
        self.assertEqual(len(unknown),2)
        self.assertEqual([D(r['amount']) for r in tables['indirect_bridge']['rows'] if r['direction']=='残差'],[0,0])

    def test_blank_adjustment_keeps_unknown_residual_but_other_period_works(self):
        t=next(t for t in self.data['tables'] if '公允价值变动损失' in t['rows'][0][0]);t['rows'][1][1]=''
        self.save_tables();r=self.report()['tables']['indirect_bridge']['rows']
        self.assertEqual([x['amount'] for x in r if x['direction']=='残差'],[None,'0.00'])

    def test_mutated_value_exposes_real_residual_and_variant_header_is_found(self):
        t=next(t for t in self.data['tables'] if '将净利润' in str(t['rows']))
        t['rows'][1][0]='净利润调整为经营活动产生的现金流量：';t['rows'][0][1:] = ['本年金额','上年金额']
        t['rows'][3][1]='4,675,845,574.44'
        self.save_tables();r=self.report()['tables']['indirect_bridge']['rows']
        self.assertEqual([D(x['amount']) for x in r if x['direction']=='残差'],[D('-.000001'),0])

    def test_negative_quarter_cfo_observation_no_causal_claim(self):
        t=next(t for t in self.data['tables'] if '第一季度' in str(t['rows'][0]));t['rows'][4][2]='-1.00'
        t['rows'][0][1:]=['Q1','Q2','Q3','Q4']
        self.save_tables();r=self.report()['tables']
        self.assertTrue(any('Q2' in x['finding'] and '现金流量净额为负' in x['finding'] for x in r['observations']['rows']))
        self.assertNotEqual(D(r['quarterly_reconciliation']['rows'][3]['residual']),0)

    def test_same_report_comparison_exposed_and_sources_use_comparative_columns(self):
        r=self.report('comparison')['tables']
        revenue=next(x for x in r['amounts']['rows'] if x['key']=='revenue')
        self.assertEqual(revenue['2024-FY'],'115393310976.69');self.assertEqual(revenue['2023-FY'],'125758168916.51')
        provenance=next(x for x in r['report_columns']['rows'] if x['key']=='2023-FY_revenue')
        self.assertEqual(provenance['document_id'],self.doc);self.assertEqual(provenance['column_label'],'2023年')
        self.assertEqual(len({x['document_id'] for x in r['report_columns']['rows']}),1)


if __name__=='__main__':unittest.main()

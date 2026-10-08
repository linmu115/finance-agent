import copy
from decimal import Decimal as D
import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from service.analysis_report import compile_report
from service.financial_workpapers import WorkpaperInputError
from service.report_package import presentation_table, section_for, workbook
from service.tests.test_workpaper_expectations import forecast, actual
from service.workpaper_expectations import expectations_report
from service.workpaper_expectations_data import candidate_issue, context_tables, reference_tables, load_inputs, eps_basis


def record(rid,value,metric='eps',**kw):
    r=forecast(rid,value,metric=metric,unit='元/股' if metric=='eps' else '元',**kw)
    r.update(scope='unspecified',label={'eps':'EPS','net_profit':'净利润','revenue':'营业收入','net_profit_parent':'归属母公司净利润'}[metric],source_ref={'page':1,'row':2,'column':2,'text':''})
    return r


class ExpectationsDataTests(unittest.TestCase):
    def test_legal_name_history_keeps_dimensions_and_unknown_profit_separate(self):
        a=record('a','2.05',publisher='甲证券',published='2024-05-12',dimensions={'security_name':'甲','financial_item':'earnings_forecast_matrix'})
        b=record('b','1.89',publisher='甲证券股份有限公司',published='2024-11-04',basis='forecast_total_shares')
        c=record('c','13063',metric='net_profit',publisher='甲证券',published='2024-05-12')
        c['exclusion_reason']=candidate_issue(c,[])
        d=record('d','12019',metric='net_profit_parent',publisher='甲证券股份有限公司',published='2024-11-04')
        original=copy.deepcopy(a['dimensions'])
        tabs,latest=context_tables([a,b,c,d],[], '2024-12-31')
        self.assertEqual({r['record_id'] for r in latest},{'b','d'})
        out=compile_report({'tables':tabs})['tables']
        self.assertEqual(out['version_links_CNY_per_share']['rows'][0]['change'],'-0.16')
        self.assertIsNone(out['version_links_CNY_money']['rows'][0]['change'])
        self.assertEqual(a['dimensions'],original)
        strict=compile_report(expectations_report([a,b,c,d],[], '2024-12-31'))
        self.assertEqual(len(strict['tables']['actual_vs_expected_CNY_per_share']['rows']),1)
        self.assertEqual(strict['tables']['excluded_CNY_money']['rows'][0]['record'],'c')

    def test_latest_reference_values_are_not_ranked_as_same_basis_errors(self):
        r=record('r','1.92',basis='latest_shares');a=actual('1.33','eps','元/股');a['basis']='basic'
        tab=reference_tables([r],[a])['reference_gaps_CNY_per_share']
        row=compile_report({'tables':{'gap':tab}})['tables']['gap']['rows'][0]
        self.assertEqual(D(row['difference']),D('-.59'))
        self.assertIn('分母口径不同',row['status']);self.assertNotIn('rank',row)
        strict=compile_report(expectations_report([r],[a]))['tables']['actual_vs_expected_CNY_per_share']['rows'][0]
        self.assertIsNone(strict['difference']);self.assertIsNone(strict['rank'])

    def test_conflicting_latest_reference_never_gets_definite_gap(self):
        a,b=record('a','1.92'),record('b','2.01');f=actual('1.33','eps','元/股');f['basis']='basic'
        _,latest=context_tables([a,b],[f],None)
        rows=reference_tables(latest,[f])['reference_gaps_CNY_per_share']['rows']
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['difference']['value'] is None and '冲突' in r['status'] for r in rows))

    def test_mean_shifted_label_and_dimensions_never_enter_company_total(self):
        r=record('r',100,metric='net_profit')
        self.assertIn('行名与指标不符',candidate_issue(r,[['header'],['经营活动现金','100']]))
        r['dimensions']={'summary_type':'mean'}
        self.assertIn('汇总行',candidate_issue(r,[]))
        r=record('r',100,metric='net_profit_parent',dimensions={'financial_item':'other_current_liabilities'})
        self.assertIn('维度未对齐',candidate_issue(r,[]))

    def test_dates_scenarios_and_currencies_never_form_cross_series_history(self):
        a=record('a',1,published='2024-01-01');b=record('b',2,published='2025-01-01')
        _,latest=context_tables([a,b],[],'2024-12-31');self.assertEqual([r['record_id'] for r in latest],['a'])
        b['published_at']='2024-10-01';b['currency']='USD'
        tabs,latest=context_tables([a,b],[],'2024-12-31');self.assertEqual(tabs,{})
        self.assertEqual(len(latest),2)
        self.assertEqual(eps_basis({**a,'label':'EPS（人民币，最新摊薄）'}),'latest_shares')
        self.assertEqual(eps_basis({**a,'label':'基本每股收益'}),'basic')
        self.assertEqual(eps_basis(a,'2024 年总股本数为 60 亿股'),'forecast_total_shares')

    def test_restated_actual_never_silently_ranks_with_original_forecast(self):
        r=forecast('r',100,restatement='original');a=actual(90);a['restatement']='restated'
        out=compile_report(expectations_report([r],[a]))
        self.assertIsNone(out['tables']['actual_vs_expected_CNY_money']['rows'][0]['difference'])

    def test_project_alias_join_and_mislabeled_interim_actual_excluded(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript('CREATE TABLE research_entities(project_id,kind,entity_id,name,aliases_json,identifiers_json); CREATE TABLE document_profiles(project_id,document_id,profile_json); CREATE TABLE research_records(project_id,entity_id,is_current,record_json,source_json,document_id);')
        db.executemany('INSERT INTO research_entities VALUES(?,?,?,?,?,?)',[
            ('p','company','long','甲公司','["甲"]','{"ticker":"000001"}'),('p','company','short','甲','[]','{}'),
            ('other','company','wrong','甲','[]','{"ticker":"999999"}')])
        db.executemany('INSERT INTO document_profiles VALUES(?,?,?)',[
            ('p','annual','{"title":"甲公司2024年年度报告"}'),('p','quarter','{"title":"甲公司2024年第三季度报告"}')])
        class Store:
            def project(self,p):pass
            def connect(self):return db
        svc=SimpleNamespace(store=Store())
        f={'company':'甲公司','metric':'revenue','period':'2024-FY','scope':'consolidated_CAS','fact_id':'a','document_id':'annual',
           'currency':'CNY','value':'100','source_ref':{'page':1,'normalization':{'statement':'income','dimensions':{}}}}
        with patch('service.workpaper_expectations_data.load_facts',return_value=[f,{**f,'fact_id':'b','document_id':'quarter','value':'80'}]):
            rs,actuals,selection=load_inputs(svc,'p','甲',None,'2024',None,'consolidated')
        self.assertEqual(selection['entity_ids'],['long','short']);self.assertEqual(len(actuals),1)
        self.assertEqual(selection['actual_exclusions'][0]['key'],'b')
        with patch('service.workpaper_expectations_data.load_facts',return_value=[f,{**f,'fact_id':'future','document_id':'quarter','period':'2025-FY','value':'80'}]):
            _,_,default=load_inputs(svc,'p','甲',None,None,None,'consolidated')
        self.assertEqual(default['periods'],['2024-FY','2023-FY'])
        db.execute('INSERT INTO research_entities VALUES(?,?,?,?,?,?)',('p','company','conflict','甲','[]','{"ticker":"999999"}'))
        with self.assertRaisesRegex(WorkpaperInputError,'证券身份'):load_inputs(svc,'p','甲',None,'2024',None,'consolidated')
        db.close()

    def test_package_presentation_does_not_remove_workbook_or_A1_provenance(self):
        from openpyxl import load_workbook
        r=record('r',1.92);a=actual(1.33,'eps','元/股');a['basis']='basic'
        tables=reference_tables([r],[a]);t=next(iter(tables.values()))
        t.update(report_section='key_data',report_columns=['metric','difference','status'])
        compiled=compile_report({'tables':tables})['tables']
        t=next(iter(compiled.values()));self.assertEqual(set(presentation_table(t)['columns']),{'metric','difference','status'})
        self.assertEqual(section_for('gap',t),1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'workpapers.xlsx'
            workbook({'title':'K4','turns':[{'tables':compiled,'sources':[]}]},path)
            sheet=load_workbook(path)['指标'];row=next(row for row in sheet if row[0].value=='r')
            self.assertEqual(D(str(row[7].value)),D('-.59'))
            self.assertIn('record_id',row[7].comment.text)


if __name__=='__main__':unittest.main()

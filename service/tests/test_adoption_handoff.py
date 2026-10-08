import copy
import hashlib
import itertools
import json
from pathlib import Path
import re
import tempfile
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from service.core import FinanceService
from service.financial_workpapers import financial_workpaper, load_facts, cell, col, table
from service.analysis_report import bind_text, compile_report
from service.workpaper_period_selection import canonical_period, normalize_periods, normalize_period_records, WorkpaperInputError
from service.workpaper_handoff import answer_handoff


class PeriodSelectionTests(unittest.TestCase):
    def test_declared_company_alias_resolves_within_project_and_document(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;self.addCleanup(db.close)
        db.executescript('CREATE TABLE current_financial_facts(project_id,document_id,company); CREATE TABLE research_entities(project_id,kind,name,aliases_json);')
        db.executemany('INSERT INTO current_financial_facts VALUES(?,?,?)',[('p','annual','甲实业股份有限公司'),('p','otherdoc','乙有限公司'),('other','foreign','外部主体')])
        db.executemany('INSERT INTO research_entities VALUES(?,?,?,?)',[('p','company','甲实业股份有限公司','["甲股份"]'),('other','company','外部主体','["甲股份"]')])
        store=SimpleNamespace(project=lambda p:None,document=lambda p,d:None,connect=lambda:db)
        service=SimpleNamespace(store=store,_expanded_fact=lambda r:r)
        self.assertEqual([r['company'] for r in load_facts(service,'p','annual','甲股份')],['甲实业股份有限公司'])
        self.assertEqual(load_facts(service,'p','otherdoc','甲股份'),[])
        self.assertEqual(load_facts(service,'p','annual','未登记别名'),[])
        self.assertEqual(len(load_facts(service,'p',company='甲')),1)

    def test_spellings(self):
        cases={'2024-FY':['2024','2024FY','FY2024','2024-12-31','2024年','2024年度','2024年全年','2024年报','2024年度报告','2024年年度报告'],
               '2025-H1':['2025H1','H1 2025','2025年上半年','2025半年度','2025-06-30','2025-6M','2025年半年度报告','2025中期','2025中期报告'],
               '2024-Q3':['2024Q3','Q3 2024','2024年第三季度'],
               '2024-9M':['2024-9M','2024年前三季度','2024-09-30'],
               '2024-Q1':['2024年一季度','2024-03-31'], '2024-H2':['2024年下半年']}
        for expected,values in cases.items():
            for value in values:
                with self.subTest(value=value):self.assertEqual(canonical_period(value),expected)

    def test_order_duplicates_and_comparable_window(self):
        available=['2024-FY','2023-FY','2024-Q4']
        for requested in itertools.permutations(available):
            self.assertEqual(normalize_periods(requested,available),['2024-FY','2023-FY','2024-Q4'])
        self.assertEqual(normalize_periods(['FY2023','2024年','2024FY'],available),['2024-FY','2023-FY'])
        self.assertEqual(normalize_periods(['2024Q3','2024Q4'],['2024-Q3','2024-Q4']),['2024-Q4','2024-Q3'])

    def test_single_default_date_and_missing_comparator(self):
        available=['2024-H1','2025-H1','2025-Q2','2024-FY']
        for value in (None,[],['H1 2025'],'2025年上半年','2025-06-30'):
            self.assertEqual(normalize_periods(value,available),['2025-H1','2024-H1'])
        self.assertEqual(normalize_periods('2024',['2024-FY']),['2024-FY','2023-FY'])

    def test_unavailable_or_malformed_names_available_periods(self):
        for value in ('2026','2024-05-01','unknown'):
            with self.subTest(value=value),self.assertRaisesRegex(WorkpaperInputError,'可用期间：2024-FY, 2023-FY'):
                normalize_periods(value,['2023-FY','2024-FY'])

    def test_source_windows_distinguish_ytd_and_quarter_without_mutating_records(self):
        raw=[{'period':'2024Q3','source_ref':{'normalization':{'statement':'income','period_start':'2024-01-01','period_end':'2024-09-30'}}},
             {'period':'2024Q3','source_ref':{'normalization':{'statement':'income','period_start':'2024-07-01','period_end':'2024-09-30'}}},
             {'period':'2024-01-01','source_ref':{'normalization':{'statement':'cashflow','period_start':'','period_end':'2024-01-01'}}}]
        original=copy.deepcopy(raw);rows=normalize_period_records(raw)
        self.assertEqual([r['period'] for r in rows],['2024-9M','2024-Q3','2024-01-01']);self.assertEqual(raw,original)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=FinanceService(self.tmp.name);self.s.create_project('p','test');self.s.create_project('other','other')
        self.facts=json.loads((Path(__file__).parent/'fixtures/workpapers/carote.json').read_text(encoding='utf8'))

    def report(self,kind='statement_analysis',periods=None):
        with patch('service.financial_workpapers.load_facts',return_value=self.facts),patch('service.workpaper_basis.load_facts',return_value=self.facts):
            return financial_workpaper(self.s,'p',kind,periods=periods)

    def test_financial_direction_is_identical_after_reversing_parameters(self):
        for kind in ('statement_analysis','variance_attribution','anomaly_signals','basis_changes','comparison'):
            with self.subTest(kind=kind):
                first=self.report(kind,['2024H1','H1 2025']);second=self.report(kind,['2025-06-30','2024-06-30'])
                self.assertEqual(first['numeric_tables'],second['numeric_tables'])
                self.assertEqual(first['period_roles'],{'current':'2025-H1','comparison':'2024-H1'})
        bridge=self.report('variance_attribution','2025H1')['numeric_tables']['profit_bridge']
        parent=next(r for r in bridge['rows'] if r['key']=='parent_profit_change')
        self.assertEqual(parent['contribution'],'-61.311')

    def test_key_values_bind_exactly_with_units_and_missing_not_zero(self):
        report=compile_report({'periods':['2024-FY','2023-FY'],'tables':{'test':table({'key':col('行键'),'item':col('指标'),'value':col('金额','百万元','CNY')},[
            {'key':'income','item':'收入','value':cell('1234500','元','CNY')},
            {'key':'unknown','item':'未披露','value':cell(None,'元','CNY',reason='原文缺少该值')}])}})
        handoff=answer_handoff(report)
        self.assertIn('1.2345 CNY 百万元',handoff['key_values'][0]);self.assertIn('原文缺少该值',handoff['key_values'][1])
        self.assertIn('—',handoff['key_values'][1]);self.assertEqual(handoff['table_bindings']['test'],'{{table:test}}')
        for line in handoff['key_values']:
            for token in re.findall(r'\{\{[^{}]+\}\}',line):self.assertIn(bind_text(token,report['tables']),line)

    def test_delivery_and_run_ids_read_same_content_status_and_reject_cross_project(self):
        data=self.report();delivery=data['delivery']['id'];name='income.csv'
        got=self.s.get_artifact('p',delivery,name)['data']
        folder=self.s.store.root/'analysis'/'run-test';(folder/'output').mkdir(parents=True)
        blob=(self.s.store.root/got['relative_path']).read_bytes();(folder/'output'/name).write_bytes(blob)
        state={'run_id':'run-test','project_id':'p','status':'succeeded','artifacts':[{'name':name,'size':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}]}
        (folder/'state.json').write_text(json.dumps(state),encoding='utf8');self.s._save_analysis_state('p','run-test',state)
        self.assertEqual(self.s.get_artifact('p','run-test',name)['data']['content'],got['content'])
        for identifier in (delivery,'run-test'):
            self.assertEqual(self.s.get_analysis_status('p',identifier)['data']['status'],'succeeded')
            with self.assertRaises(Exception):self.s.get_artifact('other',identifier,name)
            with self.assertRaises(Exception):self.s.get_artifact('p',identifier,'../'+name)
        self.assertEqual(self.s.get_analysis_status('p',delivery)['data']['numeric_tables']['income']['rows'],data['numeric_tables']['income']['rows'])
        self.assertEqual(self.s.get_artifact('p',delivery,'numeric_tables.json')['data']['content'],data['numeric_tables'])
        with self.assertRaisesRegex(ValueError,'可用文件'):self.s.get_artifact('p',delivery,'missing.json')
        (self.s.store.root/got['relative_path']).write_text('changed',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'清单不一致'):self.s.get_artifact('p',delivery,name)


if __name__=='__main__':unittest.main()

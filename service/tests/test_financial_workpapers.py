import copy
import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from service.core import FinanceService
from service.financial_workpapers import statement_analysis, financial_workpaper, WorkpaperInputError
from service.analysis_report import compile_report, bind_text

FIXTURES = Path(__file__).parent/'fixtures'/'workpapers'


class StatementWorkpapersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = FinanceService(self.tmp.name)
        self.service.create_project('p','test')

    def report(self, name='carote', facts=None, **kwargs):
        facts = facts if facts is not None else json.loads((FIXTURES/(name+'.json')).read_text(encoding='utf-8'))
        with patch('service.financial_workpapers.load_facts',return_value=facts):
            report, records = statement_analysis(self.service,'p',**kwargs)
        return compile_report(report,records)

    def row(self, report, tab, key):
        return next(r for r in report['tables'][tab]['rows'] if r['key']==key)

    def test_carote_income_and_profit_attribution_against_reviewed_source(self):
        r = self.report()
        expected = {'revenue':('836.925','955.192'), 'gross_profit':('281.594','395.243'),
                    'operating_profit':('96','193.422'),'finance_net':('25.533','3.425'),
                    'profit_before_tax':('121.533','196.847'),'tax':('-18.742','-32.763')}
        for key,pair in expected.items():
            for p,v in zip(('2025-H1','2024-H1'),pair):
                self.assertEqual(Decimal(self.row(r,'income',key)[p]),Decimal(v))
        for p,net,parent in [('2025-H1','102.791','102.785'),('2024-H1','164.084','164.096')]:
            row=self.row(r,'profit_attribution',p)
            self.assertEqual(Decimal(row['consolidated']),Decimal(net))
            self.assertEqual(Decimal(row['parent']),Decimal(parent))
            self.assertEqual(Decimal(row['parent'])+Decimal(row['minority']),Decimal(net))
        self.assertLess([x['key'] for x in r['tables']['income']['rows']].index('operating_profit'),[x['key'] for x in r['tables']['income']['rows']].index('finance_net'))

    def test_margin_uses_unrounded_amounts_and_pp(self):
        r=self.report();row=self.row(r,'ratios','gross_profit_margin')
        expected=Decimal(281594)/836925*100-Decimal(395243)/955192*100
        self.assertAlmostEqual(Decimal(row['change_pp']),expected,places=24)
        self.assertEqual(round(Decimal(row['change_pp']),4),Decimal('-7.7321'))
        self.assertEqual(r['tables']['ratios']['columns']['change_pp']['unit'],'个百分点')

    def test_mainline_answer_binding_reads_workpaper_cells_and_tables(self):
        report=self.report()
        text=bind_text('{{income.revenue.2025-H1}}\n{{table:ratios}}',report['tables'])
        self.assertIn('836.9250 CNY 百万元',text)
        self.assertIn('个百分点',text)
        self.assertNotIn('{{',text)

    def test_carote_cash_receipts_add_and_both_bridges_reconcile(self):
        r=self.report();rows=r['tables']['bridge']['rows']
        interests=[x for x in rows if 'Interest received' in x['item']]
        self.assertEqual([x['direction'] for x in interests],['加','加'])
        self.assertEqual([x['amount'] for x in interests],['5.723','1.216'])
        self.assertEqual([x['amount'] for x in rows if x['direction']=='残差'],['0']*4)
        self.assertEqual(self.row(r,'cash','2025-H1_cfo')['amount'],'-18.676')
        self.assertEqual(self.row(r,'bridge','2025-H1_cash_end')['amount'],'384.364')

    def test_ruihe_uses_total_revenue_and_investing_interest_is_not_cfo(self):
        r=self.report('ruihe')
        self.assertEqual(self.row(r,'income','revenue')['2025-H1'],'120.392')
        self.assertEqual(self.row(r,'income','fair_value_gains')['2025-H1'],'63.015')
        self.assertEqual(self.row(r,'profit_attribution','2025-H1')['consolidated'],'41.098')
        self.assertEqual(self.row(r,'profit_attribution','2025-H1')['parent'],'43.186')
        self.assertEqual(self.row(r,'cash','2025-H1_cfo')['amount'],'-30.65')
        self.assertEqual(self.row(r,'bridge','2025-H1_cash_end')['amount'],'25.723')
        self.assertFalse(any('interest' in x['item'].lower() for x in r['tables']['bridge']['rows'] if x['bridge']=='经营小计至CFO'))
        # Prior-year PDF comparatives share one physical cell; offsets preserve logical row order.
        self.assertEqual([x['amount'] for x in r['tables']['bridge']['rows'] if x['direction']=='残差'],['0']*4)

    def test_missing_begin_balance_does_not_borrow_other_year(self):
        r=self.report();row=self.row(r,'cash_quality','2024-H1')
        self.assertIsNone(row['dso']);self.assertIsNone(row['dio']);self.assertIsNone(row['dpo'])
        self.assertIsNone(self.row(self.report('ruihe'),'cash_quality','2025-H1')['dio'])
        row=self.row(r,'cash_quality','2025-H1')
        expected=(Decimal('85.774')+Decimal('103.440'))/2/Decimal('836.925')*181
        self.assertAlmostEqual(Decimal(row['dso']),expected,places=24)
        evidence=r['tables']['cash_quality']['evidence'][0]['dso']['source']['inputs']
        self.assertTrue(any(ref.get('page')==25 for ref in evidence))

    def test_missing_cash_item_is_unknown_not_zero(self):
        facts=json.loads((FIXTURES/'carote.json').read_text(encoding='utf-8'))
        facts=[r for r in facts if r['metric']!='effects_of_exchange_rate_changes_on_cash_and_cash_equivalents']
        r=self.report(facts=facts)
        self.assertIsNone(self.row(r,'bridge','2025-H1_cash_residual')['amount'])
        self.assertEqual(self.row(r,'income','revenue')['2025-H1'],'836.925')

    def test_zero_denominator_is_local_missing(self):
        facts=json.loads((FIXTURES/'carote.json').read_text(encoding='utf-8'))
        for r in facts:
            if r['metric']=='revenue' and r['period']=='2025-H1':r['value']='0'
        r=self.report(facts=facts)
        self.assertIsNone(self.row(r,'ratios','gross_profit_margin')['2025-H1'])
        self.assertEqual(self.row(r,'cash','2025-H1_cfo')['amount'],'-18.676')

    def test_conflicting_profit_does_not_pick_an_arbitrary_value(self):
        facts=json.loads((FIXTURES/'carote.json').read_text(encoding='utf-8'))
        for r in facts:
            if r['metric']=='net_profit':r['quality']='conflict'
        report=self.report(facts=facts)
        self.assertIsNone(self.row(report,'profit_attribution','2025-H1')['consolidated'])
        self.assertEqual(self.row(report,'profit_attribution','2025-H1')['parent'],'102.785')

    def test_parent_scope_never_uses_consolidated_inputs(self):
        with self.assertRaises(WorkpaperInputError):self.report(scope='parent')

    def test_new_values_change_calculations_no_company_answer_constants(self):
        facts=json.loads((FIXTURES/'carote.json').read_text(encoding='utf-8'))
        for r in facts:
            if r['metric']=='gross_profit' and r['period']=='2025-H1':r['value']='123456789'
        r=self.report(facts=facts)
        self.assertAlmostEqual(Decimal(self.row(r,'ratios','gross_profit_margin')['2025-H1']),Decimal(123456789)/836925000*100,places=24)

    def test_host_delivery_csv_report_and_json_use_same_values(self):
        facts=json.loads((FIXTURES/'carote.json').read_text(encoding='utf-8'))
        with patch('service.financial_workpapers.load_facts',return_value=facts):
            result=self.service.financial_workpaper('p')
        self.assertEqual(result['status'],'ok');data=result['data']
        folder=Path(self.tmp.name)/'research'/'p'/'deliveries'/data['delivery']['id']
        with (folder/'ratios.csv').open(encoding='utf-8-sig') as handle: rows=list(csv.DictReader(handle))
        self.assertIn('-7.7321',(folder/'report.md').read_text(encoding='utf-8'))
        self.assertEqual(rows[0]['本期减可比期（个百分点）'],data['report']['tables']['ratios']['rows'][0]['change_pp'])
        self.assertEqual(json.loads((folder/'chart_data.json').read_text(encoding='utf-8')),data['report'])
        self.assertTrue(result['source_refs'])
        self.assertTrue(all(c['row_key']=='key' for c in data['summary'].values()))

    def test_project_isolation_before_query_or_delivery(self):
        with self.assertRaises(ValueError):financial_workpaper(self.service,'other')


if __name__=='__main__':unittest.main()

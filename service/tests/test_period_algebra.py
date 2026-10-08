from decimal import Decimal as D
import unittest
from unittest.mock import patch

from service.period_algebra import (change, derive_period_series, identify_period,
    observation, quarter_window, select_observation, single_quarter, sum_periods)
from service.financial_workpapers import cell, financial_workpaper
from service.workpaper_periods import load_period_series
from service.tests import test_workpaper_annual


def amount(value,start,end,version='original',doc='current',**extra):
    q={'value':None if value is None else str(value),'unit':'元','currency':'CNY',
       'source':{'document_id':doc,'page':1,'table_id':doc+':t1','row':2,'column':2}}
    return observation('revenue',q,entity='issuer',scope='consolidated_CAS',start=start,end=end,
        document_id=doc,restatement=version,**extra)


class PeriodAlgebraTests(unittest.TestCase):
    def test_dates_override_ambiguous_q3_label(self):
        self.assertEqual(identify_period('2024-Q3')['kind'],'unknown')
        self.assertEqual(identify_period('2024-Q3',label='年初至报告期末')['kind'],'ytd')
        self.assertEqual(identify_period('2024-Q3',label='单季')['start'],'2024-07-01')
        self.assertEqual(identify_period('2024-Q3','2024-01-01','2024-09-30')['kind'],'ytd')
        self.assertEqual(identify_period('2024-H1')['end'],'2024-06-30')

    def test_q2_and_q4_differences_have_entire_source_chain(self):
        q1=amount(10,'2024-01-01','2024-03-31');h1=amount(25,'2024-01-01','2024-06-30')
        q2=single_quarter(h1,q1);self.assertEqual(D(q2['quantity']['value']),15)
        self.assertEqual(q2['start'],'2024-04-01')
        ytd=amount(80,'2024-01-01','2024-09-30');fy=amount(100,'2024-01-01','2024-12-31')
        q4=single_quarter(fy,ytd);self.assertEqual(D(q4['quantity']['value']),20)
        self.assertEqual(len(q4['quantity']['source']['inputs']),2)
        self.assertEqual(q4['quantity']['source']['inputs'][1]['quantity']['source']['column'],2)

    def test_no_mixed_versions_or_noncontiguous_quarters(self):
        h1=amount(30,'2024-01-01','2024-06-30','restated');q1=amount(10,'2024-01-01','2024-03-31')
        out=single_quarter(h1,q1);self.assertIsNone(out['quantity']['value'])
        self.assertIn('重述',out['quantity']['source']['missing_reason'])
        gap=sum_periods([q1,amount(20,'2024-07-01','2024-09-30')]);self.assertIsNone(gap['quantity']['value'])
        self.assertIsNone(single_quarter(amount(50,'2024-01-01','2024-09-30'),q1)['quantity']['value'])

    def test_missing_is_not_zero_and_balances_not_subtracted(self):
        a=amount(20,'2024-01-01','2024-06-30');b=amount(None,'2024-01-01','2024-03-31')
        self.assertIsNone(single_quarter(a,b)['quantity']['value'])
        self.assertIsNone(single_quarter(a)['quantity']['value'])
        b=amount(10,'2024-01-01','2024-03-31',additive=False)
        self.assertIsNone(single_quarter(a,b)['quantity']['value'])

    def test_current_report_adjusted_comparative_has_priority(self):
        old=amount(100,'2023-01-01','2023-12-31',doc='old')
        before=amount(100,'2023-01-01','2023-12-31')
        after=amount(120,'2023-01-01','2023-12-31','restated',basis_id='current-basis')
        chosen=select_observation([old,before,after],'current')
        self.assertEqual(chosen['quantity']['value'],'120')
        current=amount(150,'2024-01-01','2024-12-31',basis_id='current-basis')
        self.assertEqual(D(change(current,chosen,'ytd_yoy')['growth']['value']),25)

    def test_conflicting_current_cells_remain_candidates(self):
        a=amount(100,'2023-01-01','2023-12-31');b=amount(120,'2023-01-01','2023-12-31')
        chosen=select_observation([a,b],'current');self.assertIsNone(chosen['quantity']['value'])
        self.assertEqual(len(chosen['quantity']['source']['inputs']),2)

    def test_growth_modes_and_zero_negative_base(self):
        a=amount(150,'2024-04-01','2024-06-30');b=amount(100,'2024-01-01','2024-03-31')
        self.assertEqual(D(change(a,b,'qoq')['growth']['value']),50)
        prior=amount(120,'2023-04-01','2023-06-30')
        self.assertEqual(D(change(a,prior)['growth']['value']),25)
        self.assertIsNone(change(a,prior,'ytd_yoy')['growth']['value'])
        for base in (0,-10):
            b['quantity']['value']=str(base);r=change(a,b,'qoq')
            self.assertIsNone(r['growth']['value']);self.assertEqual(D(r['delta']['value']),150-base)

    def test_scope_currency_and_entity_cannot_mix(self):
        for field,value in [('scope','parent_CAS'),('currency','USD'),('entity','other')]:
            a=amount(30,'2024-01-01','2024-06-30');b=amount(10,'2024-01-01','2024-03-31');b[field]=value
            self.assertIsNone(single_quarter(a,b)['quantity']['value'])

    def test_qoq_previous_year_q4_and_leap_year(self):
        a=amount(30,'2024-01-01','2024-03-31');b=amount(20,'2023-10-01','2023-12-31')
        self.assertEqual(D(change(a,b,'qoq')['growth']['value']),50)
        self.assertEqual(quarter_window(2024,1),('2024-01-01','2024-03-31'))

    def test_series_keeps_disclosed_and_derivation_residual(self):
        inputs=[amount(v,*quarter_window(2024,i)) for i,v in enumerate((10,20,30,41),1)]
        inputs.append(amount(100,'2024-01-01','2024-12-31'))
        r=derive_period_series(inputs,'current')
        q4=next(x for x in r['reconciliations'] if x['period']=='2024-Q4')
        self.assertEqual(D(q4['derived']['quantity']['value']),40)
        self.assertEqual(D(q4['residual']['value']),1)


class PeriodWorkpaperTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_workpaper_annual.AnnualWorkpapersTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def test_yili_four_metrics_q4_zero_and_qoq_manual(self):
        f=self.fixture
        with patch('service.workpaper_periods.load_facts',return_value=f.facts):
            r=load_period_series(f.s,'p',f.doc)
        checks=[x for x in r['reconciliations'] if x['period']=='2024-Q4']
        self.assertEqual(len(checks),4)
        self.assertTrue(all(D(x['residual']['value'])==0 for x in checks))
        rows={x['period']:x for x in r['quarters'] if x['metric']=='revenue'}
        q2,q1=rows['2024-Q2'],rows['2024-Q1']
        manual=(D(q2['quantity']['value'])/D(q1['quantity']['value'])-1)*100
        self.assertAlmostEqual(D(change(q2,q1,'qoq')['growth']['value']),manual,places=24)
        self.assertTrue(all(x['derived']['quantity']['source']['inputs'] for x in checks))

    def test_tool_exposed_with_typed_sources(self):
        f=self.fixture
        with patch('service.workpaper_periods.load_facts',return_value=f.facts):
            result=financial_workpaper(f.s,'p','period_analysis',document_id=f.doc)
        self.assertIn('reconciliation',result['numeric_tables'])
        self.assertTrue(result['delivery']['files'])


if __name__=='__main__':unittest.main()

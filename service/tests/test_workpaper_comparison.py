import copy
import unittest
from decimal import Decimal as D

from service.analysis_report import compile_report
from service.workpaper_comparison import comparison_report


def subject(key='a24', year=2024, entity='a', currency='CNY'):
    amounts = dict(revenue=1200,cogs=-720,gross_profit=480,selling=-120,administrative=-60,
                   research=-30,operating_profit=240,net_profit=180,parent_profit=150,cfo=216,
                   assets_begin=900,assets_end=1100,equity_begin=400,equity_end=500,
                   cash_end=100,receivables_begin=100,receivables_end=140,
                   inventory_begin=150,inventory_end=210,payables_begin=80,payables_end=120,liabilities_end=600)
    return dict(key=key,entity_id=entity,company=entity,period=str(year),period_start=f'{year}-01-01',period_end=f'{year}-12-31',
                scope='consolidated',currency=currency,period_source={'document_id':key,'page':1},
                metadata={k:{'value':v,'source':{'document_id':key,'page':1}} for k,v in
                          dict(fiscal_year_end='12-31',scope='consolidated',currency=currency,accounting_standard='CAS',restated=False).items()},
                metrics={k:dict(value=str(v),unit='百万元',currency=currency,source={'fact_id':key+'_'+k,'page':2}) for k,v in amounts.items()})


def row(report, tab, key):
    return next(r for r in report['tables'][tab]['rows'] if r['key']==key)


class ComparisonCoreTests(unittest.TestCase):
    def test_independent_numeric_examples_over_thirty_values(self):
        current=subject();old=subject('a23',2023)
        for metric in ('revenue','gross_profit','net_profit','parent_profit','cfo'):
            old['metrics'][metric]['value']=str(D(current['metrics'][metric]['value'])/D('1.2'))
        report=compile_report(comparison_report([old,current]))
        checks=0
        for metric,expected in dict(revenue=100,cogs=-60,gross_profit=40,selling=-10,administrative=-5,research=D('-2.5'),operating_profit=20,net_profit=15,parent_profit=D('12.5')).items():
            self.assertEqual(D(row(report,'common_income',metric)['a24']),D(expected));checks+=1
        for metric,expected in dict(assets_end=1100,cash_end=100,receivables_end=140,inventory_end=210,liabilities_end=600,payables_end=120,equity_end=500).items():
            self.assertAlmostEqual(D(row(report,'common_balance',metric)['a24']),D(expected)/11,places=24);checks+=1
        dupont=row(report,'dupont','a24')
        for metric,expected in dict(net_margin=15,asset_turnover=D('1.2'),equity_multiplier=D(1000)/450,roe=40,product=40,residual=0).items():
            self.assertAlmostEqual(D(dupont[metric]),D(expected),places=24);checks+=1
        for key,expected in dict(cash_conversion=120,cfo_margin=18).items():
            self.assertEqual(D(row(report,'cash_conversion','a24')[key]),D(expected));checks+=1
        for key,expected in dict(days=366,dso=D('36.6'),dio=D('91.5'),dpo=D(100)/720*366,cycle=D('36.6')+D('91.5')-D(100)/720*366).items():
            self.assertAlmostEqual(D(row(report,'operating_days','a24')[key]),D(expected),places=24);checks+=1
        for metric in ('revenue','gross_profit','net_profit','parent_profit','cfo'):
            self.assertEqual(D(row(report,'growth','a24_'+metric)['growth']),D(20));checks+=1
        self.assertEqual(checks,34)
        self.assertEqual(row(report,'amounts','parent_profit')['a24'],'150000000')
        self.assertEqual(row(report,'amounts','net_profit')['a24'],'180000000')

    def test_average_balances_not_closing_and_scale_invariance(self):
        a=subject();b=copy.deepcopy(a);b['key']='b24'
        for q in b['metrics'].values():q.update(value=str(D(q['value'])*100),unit='万元')
        report=compile_report(comparison_report([a,b]))
        self.assertEqual(row(report,'dupont','a24')['roe'],row(report,'dupont','b24')['roe'])
        self.assertEqual(row(report,'dupont','a24')['roe'],'40')
        self.assertNotEqual(D(row(report,'dupont','a24')['roe']),D(180)/500*100)
        self.assertEqual(row(report,'growth','a24_cfo')['growth'],None)

    def test_missing_opening_is_local_no_other_year_substitution(self):
        a=subject();del a['metrics']['assets_begin'];del a['metrics']['receivables_begin']
        report=compile_report(comparison_report([subject('a23',2023),a]))
        self.assertIsNone(row(report,'dupont','a24')['asset_turnover'])
        self.assertIsNone(row(report,'dupont','a24')['residual'])
        self.assertIsNone(row(report,'operating_days','a24')['dso'])
        self.assertEqual(row(report,'cash_conversion','a24')['cash_conversion'],'120')
        evidence=report['tables']['operating_days']['evidence'][1]['dso']['source']
        self.assertIn('receivables_begin',evidence['missing_reason'])

    def test_different_currencies_not_mixed_or_converted(self):
        a=subject();b=subject('b24',entity='b',currency='HKD')
        a['metrics']['cfo']['currency']='USD'
        r=compile_report(comparison_report([a,b]))
        self.assertIsNone(row(r,'cash_conversion','a24')['cash_conversion'])
        self.assertEqual(D(row(r,'common_income','gross_profit')['b24']),D(40))
        self.assertEqual(r['tables']['amounts']['columns']['b24']['currency'],'HKD')
        self.assertEqual(row(r,'comparability','a24_currency')['difference'],'存在已披露差异')
        self.assertEqual(D(row(r,'observations','a24_b24_gross_profit')['gap_pp']),D(0))

    def test_scope_and_fiscal_period_prevent_false_growth(self):
        old=subject('a23',2023);now=subject();old['scope']='parent'
        r=compile_report(comparison_report([old,now]))
        self.assertIsNone(row(r,'growth','a24_revenue')['growth'])
        old['scope']='consolidated';old['period_end']='2023-06-30'
        r=compile_report(comparison_report([old,now]))
        self.assertIsNone(row(r,'growth','a24_revenue')['growth'])

    def test_zero_loss_and_missing_metadata_are_not_success_or_zero(self):
        a=subject();a['metrics']['net_profit']['value']='-10';a['metrics']['equity_begin']['value']='-500';a['metadata']={}
        r=compile_report(comparison_report([a]))
        self.assertIsNone(row(r,'cash_conversion','a24')['cash_conversion'])
        self.assertIsNone(row(r,'dupont','a24')['roe'])
        self.assertIsNone(row(r,'comparability','a24_restated')['value'])
        self.assertIsNone(row(r,'growth','a24_net_profit')['growth'])
        a['metrics']['revenue']['value']='0'
        r=compile_report(comparison_report([a]))
        self.assertIsNone(row(r,'dupont','a24')['net_margin'])
        self.assertEqual(row(r,'amounts','cfo')['a24'],'216000000')

    def test_input_unchanged_evidence_kept_and_no_annualization(self):
        a=subject();a['period_end']='2024-06-30';original=copy.deepcopy(a)
        r=compile_report(comparison_report([a]))
        self.assertEqual(a,original)
        self.assertEqual(row(r,'dupont','a24')['roe'],'40')
        self.assertEqual(row(r,'operating_days','a24')['days'],'182')
        self.assertEqual(r['tables']['dupont']['evidence'][0]['roe']['source']['inputs'][0]['fact_id'],'a24_net_profit')


if __name__=='__main__':unittest.main()

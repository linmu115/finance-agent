import copy
from decimal import Decimal as D
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from service.analysis_report import compile_report, bind_text
from service.financial_workpapers import cell, financial_workpaper
from service.workpaper_signals import anomaly_signals, audit_signals, note_ratios
from service.tests import test_workpaper_annual as annual_tests


class SyntheticData:
    def __init__(self):
        self.ps=['2024-FY','2023-FY'];self.currency='CNY';self.records=[]
        self.st=SimpleNamespace(company='合成主体')
        self.d=SimpleNamespace(pages={},tabs=[],year='2024',doc='synthetic',document={'original_name':'合成报告'},applies=lambda t:True)
        self.income={'net_profit':100,'parent_profit':90,'revenue':1000,'cogs':600,'asset_impairment':-10,'credit_impairment':-5,'cfo':120}
        self.balances={'assets':1000,'equity':500,'receivables':100,'inventory':80,'other_receivables':10,'prepayments':10,'other_noncurrent':10,
                       'cash_balance':100,'short_term_borrowings':100,'goodwill':10}
        self.changes={};self.base={'tables':{}}
    def q(self,v):return cell(v,'元','CNY',sources=[{'document_id':'synthetic','page':1,'table_id':'t','row':1,'column':2}])
    def pick(self,k,p,stmt):return self.q(self.changes.get((k,p),self.income.get(k)))
    def balance(self,k,p,begin=False,year_ago=False):return self.q(self.changes.get((k,begin,year_ago),self.balances.get(k)))
    def window(self,p):return p[:4]+'-01-01',p[:4]+'-12-31'
    def annual_row(self,t,p):
        if t=='cash_quality':return {'dso':cell(30,'天'),'dio':cell(30,'天')}
        if t=='deducted_profit':return {'share':cell(10,'%')}
        return {}
    def quarters(self,k):return [self.q(20),self.q(20),self.q(20),self.q(20)]
    def first_three_quarters(self,k):return self.q(60)
    def source_text(self,p,q,**kw):return {'document_id':'synthetic','page':int(p),'quote':q,**kw}


class SignalTests(unittest.TestCase):
    def report(self,a):
        with patch('service.workpaper_signals.AnalystData',return_value=a):raw,rs=anomaly_signals(None,'p')
        report=compile_report(raw,rs)
        return report,{r['key']:r for r in report['tables']['signals']['rows']}

    def test_synthetic_trigger_nontrigger_and_exact_threshold(self):
        a=SyntheticData();report,rows=self.report(a)
        self.assertEqual(rows['2024-FY_cash_conversion']['triggered'],'否')
        self.assertFalse(report['tables']['observations']['rows'])
        a.changes.update({('cfo','2024-FY'):-10,('cfo','2023-FY'):50,('receivables',False,False):200,
                          ('inventory',False,False):160,('other_noncurrent',False,False):200,('cash_balance',False,False):300,
                          ('short_term_borrowings',False,False):300,('goodwill',False,False):200,('asset_impairment','2024-FY'):-30})
        report,rows=self.report(a)
        for k in ['2024-FY_cash_conversion','2024-FY_accrual','2024-FY_profit_cash_sign','cash_divergence_run',
                  'receivables_growth_gap','inventory_growth_gap','other_noncurrent_asset_share','other_noncurrent_growth',
                  'cash_debt_high','goodwill_equity_share','asset_impairment_change']:
            self.assertEqual(rows[k]['triggered'],'是',k)
        self.assertEqual(set(r['key'] for r in report['tables']['observations']['rows']),{k for k,r in rows.items() if r['triggered']=='是'})
        a.changes[('goodwill',False,False)]=150
        _,rows=self.report(a);self.assertEqual(rows['goodwill_equity_share']['triggered'],'否')
        text=bind_text('{{signals.2024-FY_cash_conversion.value}}',report['tables'])
        self.assertIn('-0.10 ratio',text)

    def test_missing_year_ago_not_replaced_with_opening_and_negative_profit(self):
        a=SyntheticData();a.changes[('receivables',False,True)]=None;a.changes[('net_profit','2024-FY')]=-1
        _,rows=self.report(a)
        self.assertEqual(rows['receivables_growth_gap']['triggered'],'未知')
        self.assertEqual(rows['2024-FY_cash_conversion']['triggered'],'未知')
        self.assertIsNone(rows['cash_divergence_run']['value'])
        for r in rows.values():
            if r['value'] is None:self.assertTrue(r['missing'],r['key'])
            else:self.assertIn(r['triggered'],('是','否'))

    def test_audit_negation_generic_duties_and_emphasis_are_separate(self):
        a=SyntheticData();a.d.pages={1:'本公司未经审计。是否改聘会计师事务所 □是 √否\n如果披露不充分，我们应当发表非无保留意见。'}
        result=audit_signals(a)
        self.assertIsNone(result['opinion'][1]);self.assertFalse(result['auditor_change'][1]);self.assertNotIn('emphasis',result)
        a.d.pages[2]='一、审计意见\n出具了标准无保留意见的审计报告。\n三、强调事项\n我们提请注意附注。'
        result=audit_signals(a)
        self.assertFalse(result['opinion'][1]);self.assertTrue(result['emphasis'][1])

    def test_note_aging_uses_gross_total_and_ignores_duplicate_one_year_subtotal(self):
        a=SyntheticData();a.d.pages={1:'5、应收账款\n（1）按账龄披露'}
        t={'table_id':'t','page':1,'rows':[['账龄','期末账面余额','期初账面余额'],['1年以内','70','90'],['1年以内小计','70','90'],['1至2年','20','5'],['2年以上','10','5'],['合计','100','100']]}
        a.d.tabs=[t];a.d.quantity=lambda t,i,c,h:a.q(t['rows'][i][c])
        aging,_=note_ratios(a)
        self.assertEqual(D(aging[0]['value'])-D(aging[1]['value']),20)
        t['rows'][3][1]=None
        aging,_=note_ratios(a);self.assertIsNone(aging[0]['value'])


class SignalContractTests(unittest.TestCase):
    setUp=annual_tests.AnnualWorkpapersTests.setUp
    save_tables=annual_tests.AnnualWorkpapersTests.save_tables

    def test_publish_attaches_a1_typed_evidence_and_only_triggered_observations(self):
        with patch('service.financial_workpapers.load_facts',return_value=self.facts):
            result=financial_workpaper(self.s,'p','anomaly_signals',document_id=self.doc)
        report=result['report'];rows=report['tables']['signals']['rows']
        self.assertEqual(result['numeric_tables'],report['tables'])
        self.assertEqual(len({r['family'] for r in rows}),9)
        self.assertTrue(any(f['name']=='signals.csv' for f in result['delivery']['files']))
        self.assertTrue(report['tables']['signals']['evidence'])
        self.assertEqual({r['key'] for r in result['observations']},{r['key'] for r in rows if r['triggered']=='是'})
        self.assertTrue(all('经验阈值' in r['threshold_source'] or '经验阈值' in r['baseline'] or r['family'] in ('审计与治理','季度集中','利润与现金流') for r in rows))


if __name__=='__main__':unittest.main()

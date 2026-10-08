"""Integration at the N4 adapter, beyond N2's isolated arithmetic tests."""
import copy
from decimal import Decimal as D
import unittest
from unittest.mock import patch

from service.tests import test_workpaper_annual as annual
from service.workpaper_analyst import AnalystData,locators


class SignalPeriodIntegrationTests(unittest.TestCase):
    setUp=annual.AnnualWorkpapersTests.setUp
    save_tables=annual.AnnualWorkpapersTests.save_tables

    def context(self):
        return AnalystData(self.s,'p',self.doc)

    def test_annual_disclosure_and_cumulative_derivation_reconcile(self):
        with patch('service.financial_workpapers.load_facts',return_value=self.facts):
            a=self.context();quarters=a.quarters('revenue');series=a.period_series()
        self.assertEqual(D(quarters[3]['value']),D('26660376531.26'))
        checks=[r for r in series['reconciliations'] if r['period']=='2024-Q4']
        self.assertEqual(len(checks),4)
        self.assertTrue(all(D(r['residual']['value'])==0 for r in checks))
        self.assertTrue(all(locators(r['derived']['quantity']) for r in checks))
        self.assertIs(series,a.period_series())

    def without_quarter_disclosures(self):
        # Source table and normalized rows both removed. Q4 must actually use
        # the second report's cumulative source, not the K1 quarterly table.
        tableids={t['table_id'] for t in self.data['tables'] if '第一季度' in str(t['rows'][0])}
        self.data['tables']=[t for t in self.data['tables'] if t['table_id'] not in tableids]
        self.facts=[r for r in self.facts if r['source_ref'].get('table_id') not in tableids]
        self.save_tables()
        prior=copy.deepcopy(next(r for r in self.facts if r['period']=='2024-FY' and r['metric']=='revenue'))
        prior.update(document_id='q3-doc',fact_id='q3-revenue',period='2024-Q3',value='88732934445.43')
        prior['source_ref'].update(document_id='q3-doc',table_id='q3-table',page=3,row=2,column=2)
        prior['source_ref']['normalization'].update(period_start='2024-01-01',period_end='2024-09-30',period_label='年初至报告期末')
        return prior

    def test_q4_uses_same_project_source_chain_when_annual_table_is_absent(self):
        prior=self.without_quarter_disclosures();calls=[]
        def load(service,project,document_id=None,company=None):
            calls.append((project,document_id,company))
            return self.facts if document_id else [*self.facts,prior]
        with patch('service.financial_workpapers.load_facts',side_effect=load):
            a=AnalystData(self.s,'p',self.doc);q4=a.quarters('revenue')[3];ytd=a.first_three_quarters('revenue')
        self.assertEqual(D(q4['value']),D('26660376531.26'))
        self.assertEqual(D(ytd['value']),D('88732934445.43'))
        self.assertIsNone(a.quarters('revenue')[0]['value'])
        self.assertEqual({x['document_id'] for x in locators(q4)},{self.doc,'q3-doc'})
        self.assertEqual(calls,[('p',self.doc,None),('p',None,'测试主体')])
        self.assertTrue(any(r['document_id']=='q3-doc' for r in a.records))

    def test_mixed_restatement_basis_stays_unknown(self):
        prior=self.without_quarter_disclosures()
        prior['source_ref']['normalization']['restatement']='restated'
        with patch('service.financial_workpapers.load_facts',side_effect=lambda s,p,document_id=None,company=None:self.facts if document_id else [*self.facts,prior]):
            a=AnalystData(self.s,'p',self.doc);q4=a.quarters('revenue')[3]
        self.assertIsNone(q4['value'])
        self.assertIn('重述',q4['source']['missing_reason'])


if __name__=='__main__':unittest.main()

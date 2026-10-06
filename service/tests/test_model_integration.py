"""Record-to-model, model reuse and cash-flow regressions from the pilot."""
import copy
import unittest
from decimal import Decimal

from service.model_inputs import resolve_inputs
from service.model_comparison import compare_models
from service.research_models import financial_quality, value_dcf
from service.tests.test_research_models import dcf_spec


class RecordBindingsTests(unittest.TestCase):
    def test_fact_coordinates_units_and_project_scope_survive_binding(self):
        from service.tests.test_script_cleaning import ScriptCleaningTests
        fixture=ScriptCleaningTests();fixture.setUp()
        try:
            run=fixture.job();fixture.s.commit_cleaning_result('p',fixture.pid,run)
            facts=fixture.s.query_financial_data('p')['data']['items']
            fact=next(row for row in facts if row['metric']=='revenue' and row['value']=='100000')
            spec=dcf_spec();bindings={'base.revenue':{'fact_id':fact['fact_id'],'scale':'1000000'}}
            result=resolve_inputs(fixture.s,'p',spec,bindings)
            self.assertEqual(result['spec']['base']['revenue'],'0.1')
            self.assertEqual(spec['base']['revenue'],'1000')
            self.assertEqual(result['bindings'][0]['source_value'],'100000')
            self.assertEqual(result['bindings'][0]['period'],'2025-H1')
            self.assertEqual(result['spec']['source_refs']['base.revenue'][0]['id'],fixture.did)
            self.assertEqual(result['spec']['source_refs']['base.revenue'][0]['cell'],fact['source_ref']['cell'])
            auto=copy.deepcopy(spec);auto['amount_scale']='1000000'
            del auto['base']['revenue']
            bound=resolve_inputs(fixture.s,'p',auto,{'base.revenue':{'fact_id':fact['fact_id']}})
            self.assertEqual(bound['spec']['base']['revenue'],'0.1')
            self.assertEqual(result['spec']['input_basis']['base.revenue']['source_kind'],'disclosed_actual')
            with self.assertRaisesRegex(ValueError,'model_record_not_in_project'):
                resolve_inputs(fixture.s,'q',spec,bindings)
            with self.assertRaisesRegex(ValueError,'model_input_path_not_found'):
                resolve_inputs(fixture.s,'p',spec,{'missing.revenue':bindings['base.revenue']})
        finally:fixture.tearDown()

    def test_analyst_forecast_keeps_its_identity_and_raw_value(self):
        from service.tests.test_research_ingestion import ResearchIngestionTests
        fixture=ResearchIngestionTests();fixture.setUp()
        try:
            fixture.commit()
            records=fixture.s.query_research_records('p')['data']['items']
            row=next(r for r in records if r['data_kind']=='analyst_forecast' and r['metric']=='revenue')
            result=resolve_inputs(fixture.s,'p',dcf_spec(),{'base.revenue':{'record_id':row['record_id'],'scale':'1000000'}})
            self.assertEqual(result['spec']['base']['revenue'],'120')
            self.assertEqual(result['bindings'][0]['data_kind'],'analyst_forecast')
            self.assertEqual(result['spec']['input_basis']['base.revenue']['source_kind'],'analyst_forecast')
            computed=fixture.s.calculate_financial_metrics('p','sum',{'values':[{'record_id':row['record_id']},{'record_id':row['record_id']}]})
            self.assertEqual(Decimal(computed['data']['value']), Decimal(row['value'])*2)
            self.assertEqual(computed['data']['resolved_inputs']['values.0']['data_kind'],'analyst_forecast')
        finally:fixture.tearDown()


class ModelDifferencesTests(unittest.TestCase):
    def test_both_capex_and_depreciation_changes_are_visible_and_decompose(self):
        base=dcf_spec();new=copy.deepcopy(base)
        new['forecast'][0].update(capex_ratio='0.08',da_ratio='0.06')
        order=['forecast.0.capex_ratio','forecast.0.da_ratio']
        result=compare_models('dcf',base,new,order)
        self.assertEqual({v['path'] for v in result['changed_inputs']},set(order))
        total=Decimal(result['result_changes']['value_per_share']['change'])
        # One year: capex costs 30, depreciation adds 10; discounted at 10%, /100 shares.
        self.assertLess(abs(total-Decimal('-0.1818181818181818181818181818')),Decimal('1e-26'))
        steps=result['decomposition']['steps']
        self.assertLess(abs(sum(Decimal(v['contribution']) for v in steps)-total),Decimal('1e-26'))
        self.assertLess(Decimal(steps[0]['contribution']),0)
        self.assertGreater(Decimal(steps[1]['contribution']),0)
        self.assertEqual(base['forecast'][0]['capex_ratio'],'0.05')
        row=result['forecast_changes'][0]
        self.assertEqual(Decimal(row['da_change']),10)
        self.assertEqual(Decimal(row['capex_change']),30)
        self.assertEqual(Decimal(row['fcff_change']),-20)
        self.assertEqual(Decimal(row['fcff_bridge_residual']),0)

    def test_reference_outside_sensitivity_is_not_described_as_inside(self):
        spec=dcf_spec();spec['sensitivity']={'wacc':['0.08','0.09'],'growth':['0']}
        spec['reference_value_per_share']='13'
        result=value_dcf(spec)['results']
        self.assertFalse(result['reference_comparison']['sensitivity_contains_reference'])
        self.assertEqual(result['reference_comparison']['range_position'],'below')
        self.assertGreater(Decimal(result['sensitivity_range']['minimum']),13)
        self.assertEqual(Decimal(result['value_per_share']),13)

    def test_different_value_dates_are_not_reported_as_economic_change(self):
        base=dcf_spec();new=copy.deepcopy(base)
        new['base_year']=2025;new['forecast'][0]['year']=2026
        result=compare_models('dcf',base,new)
        self.assertEqual(result['result_changes'],{})
        self.assertIn('base_year',result['comparison_unavailable'])


class CashflowBridgeTests(unittest.TestCase):
    def test_director_loan_is_not_working_capital_and_unexplained_amount_is_visible(self):
        spec={'currency':'HKD','amount_scale':'1000','period_basis':'annual',
              'receivables_sales_basis':'revenue_proxy','payables_cost_basis':'cogs_proxy',
              'periods':[{'year':2025,'days':'365','net_income':'100','cfo':'91',
                  'cashflow_bridge':{'profit_basis':'consolidated_net_income','starting_profit':'100',
                    'adjustments':[
                        {'label':'折旧','amount':'20','category':'non_cash'},
                        {'label':'税项','amount':'-29','category':'tax'},
                        {'label':'存货与应收增加','amount':'-5','category':'operating_working_capital'},
                        {'label':'董事贷款','amount':'7461','category':'financing'},
                        {'label':'待明确的调节项','amount':'5','category':'unclassified'}]}}]}
        result=financial_quality(spec)
        bridge=result['results']['cashflow_reconciliations'][0]
        self.assertEqual(bridge['explained_cfo'],'86')
        self.assertEqual(bridge['unexplained_residual'],'5')
        self.assertEqual(bridge['excluded_non_operating'],['董事贷款'])
        self.assertEqual(bridge['unclassified'],['待明确的调节项'])
        del spec['periods'][0]['cfo']
        self.assertIsNone(financial_quality(spec)['results']['cashflow_reconciliations'][0]['unexplained_residual'])


if __name__=='__main__':unittest.main()

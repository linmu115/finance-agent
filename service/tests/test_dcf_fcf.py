import unittest
from copy import deepcopy
from decimal import Decimal
from service.research_models import evaluate_model,ValidationError
from service.model_inputs import apply_overrides
from service.model_comparison import compare_models
from service.analysis_report import bind_text,model_quantity

BASE={'currency':'CNY','amount_scale':'1000000','valuation_date':'2023-12-31','discount':{'cashflow_timing':'year_end'},
      'fcf':['288','512','591','594','626'],'wacc':'.122','g':'.02','net_cash':'320','shares':{'count':'555','scale':'1000000'},'price_currency':'HKD','fx':'1.07',
      'sensitivity':{'wacc':['.112','.122','.132'],'growth':['.01','.02','.03']}}


class GivenFcfTests(unittest.TestCase):
    def test_frozen_value_grid_and_update(self):
        r=evaluate_model('dcf_fcf',BASE)
        self.assertAlmostEqual(float(r['results']['enterprise_value']),5329.224677510071,places=9)
        self.assertAlmostEqual(float(r['results']['value_per_share']),10.891298026911309,places=12)
        self.assertEqual(len(r['tables']['sensitivity']),9)
        updated=apply_overrides(BASE,{'wacc':{'+':'.005'},'fcf':{'*':'.9'}})['spec']
        changes=compare_models('dcf_fcf',BASE,updated,['wacc','fcf'])
        self.assertAlmostEqual(float(evaluate_model('dcf_fcf',updated)['results']['value_per_share']),9.40763954155814,places=12)
        steps=changes['decomposition']['steps']
        self.assertAlmostEqual(float(steps[0]['contribution']),-.506913751506370,places=12)
        self.assertAlmostEqual(float(steps[1]['contribution']),-.976744733846800,places=12)
        self.assertIn('dcf_update_contributions',changes['report']['tables'])
        reversed_order=compare_models('dcf_fcf',BASE,updated,['fcf','wacc'])
        self.assertNotEqual(steps[0]['contribution'],reversed_order['decomposition']['steps'][1]['contribution'])
        self.assertEqual(changes['decomposition']['total_change'],reversed_order['decomposition']['total_change'])

    def test_defaults_missing_values_and_invalid_grid_cells(self):
        s=deepcopy(BASE);s.pop('sensitivity');s.pop('shares');s.pop('net_cash');r=evaluate_model('dcf_fcf',s)
        self.assertEqual(len(r['tables']['sensitivity']),25)
        self.assertIsNone(r['results']['equity_value']);self.assertIsNone(r['results']['value_per_share'])
        self.assertIsNone(r['results']['non_controlling_interest'])
        s.update(wacc='.025',g='.02');r=evaluate_model('dcf_fcf',s)
        self.assertTrue(any(row.get('reason') and row['enterprise_value'] is None for row in r['tables']['sensitivity']))
        self.assertTrue(any(row['enterprise_value'] is not None for row in r['tables']['sensitivity']))

    def test_discount_time_and_exit_multiples(self):
        s=deepcopy(BASE);s['discount']['cashflow_timing']='mid_year';r=evaluate_model('dcf_fcf',s)
        annual=evaluate_model('dcf_fcf',BASE)
        self.assertEqual(r['results']['terminal_pv'],annual['results']['terminal_pv'])
        self.assertGreater(Decimal(r['results']['explicit_forecast_pv']),Decimal(annual['results']['explicit_forecast_pv']))
        s.update(terminal_ebitda='1000',terminal_net_income='500');r=evaluate_model('dcf_fcf',s)
        self.assertEqual(Decimal(r['results']['ev_ebitda']),Decimal('6.26'));self.assertIsNone(r['results']['pe'])
        s['terminal_net_cash']='100';r=evaluate_model('dcf_fcf',s);self.assertEqual(Decimal(r['results']['pe']),Decimal('12.72'))

    def test_price_bridge_requires_identifying_assumptions(self):
        s={**deepcopy(BASE),'target_price':'10.95'};r=evaluate_model('dcf_fcf',s)
        self.assertFalse(r['tables']['target_bridge']);self.assertTrue(any('不可识别' in n for n in r['warnings']))
        s['target_assumptions']={'wacc':'.127','fcf':['259.2','460.8','531.9','534.6','563.4'],'g':'.025','fx':'1.1','shares':{'count':'550','scale':'1000000'}}
        s['target_order']=['wacc','g','fcf','fx','shares'];r=evaluate_model('dcf_fcf',s)
        self.assertEqual(len(r['tables']['target_bridge']),6)
        total=sum(Decimal(x['contribution']) for x in r['tables']['target_bridge'])
        self.assertAlmostEqual(float(total),10.95-float(r['results']['value_per_share']),places=12)

    def test_binding_units_and_record_provenance(self):
        s={**deepcopy(BASE),'eps':'0.63','source_refs':{'eps':[{'kind':'document','id':'d','record_id':'r2024','locator':'page:2'}]}}
        r=evaluate_model('dcf_fcf',s);table=r['report']['tables']['dcf_summary'];i=table['row_keys'].index('eps')
        self.assertEqual(table['rows'][i]['value'],'0.63');self.assertIn('r2024',str(table['evidence'][i]))
        self.assertEqual(bind_text('{{dcf_summary.eps.value}}',r['report']['tables']),'0.63 CNY 元/股')
        self.assertEqual(bind_text('{{dcf_summary.value_per_share.value}}',r['report']['tables']),'10.89 HKD 元/股')
        q=model_quantity({'id':'a','revision_id':'b','kind':'dcf_fcf','spec':s,'result':r},'results.value_per_share')
        self.assertEqual(q['currency'],'HKD')

    def test_unknown_inputs_have_precise_errors(self):
        with self.assertRaisesRegex(ValueError,'model_input_path_not_found'):apply_overrides(BASE,{'unknown':{'+':1}})
        with self.assertRaisesRegex(ValueError,'cover_changed_inputs'):compare_models('dcf_fcf',BASE,apply_overrides(BASE,{'wacc':{'+':'.005'}})['spec'],['fcf'])
        with self.assertRaisesRegex(ValidationError,'net_cash OR net_debt'):evaluate_model('dcf_fcf',{**BASE,'net_debt':'10'})
        with self.assertRaisesRegex(ValidationError,'YYYY-MM-DD'):evaluate_model('dcf_fcf',{**BASE,'valuation_date':'today'})

if __name__=='__main__':unittest.main()

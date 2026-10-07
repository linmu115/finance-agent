import json
from pathlib import Path
import tempfile
import unittest
from service.analysis_report import bind_text
from service.analysis_comparison import deliver_parameter_comparison
from service.scenario_tables import scenario_tables,PREFERRED
from service.analysis_tables import json_tables

def tables(value):
    return {'valuation':{'columns':{'price':{'unit':'元/股','currency':'HKD','decimals':2}},'row_keys':['base'],'rows':[{'price':value}]}}

class ScenarioTablesTests(unittest.TestCase):
    def test_numeric_only_json_rows_keep_identity_when_the_first_value_changes(self):
        old=json_tables({'2024':288,'2025':512},'fcf_RMB_mn')
        new=json_tables({'2024':259.2,'2025':460.8},'fcf_RMB_mn')
        self.assertEqual(old['fcf_RMB_mn']['row_keys'],['0'])
        self.assertEqual(new['fcf_RMB_mn']['row_keys'],['0'])
        result,_=scenario_tables(old,new,'old','new')
        self.assertEqual(len(result[PREFERRED]['rows']),2)
        self.assertEqual(result[PREFERRED]['rows'][0]['delta'],'-28.8')

    def test_baseline_stays_referenceable_and_comparison_embeds(self):
        result,context=scenario_tables(tables('10.89'),tables('9.41'),'old','new')
        body=bind_text('{{基准_old__valuation.base.price}} / {{情景_new__valuation.base.price}}\n'+context['preferred_embedding'],result)
        self.assertIn('10.89 HKD 元/股 / 9.41 HKD 元/股',body)
        self.assertIn('差额（情景减基准）',body);self.assertIn('-1.48 HKD 元/股',body)
        self.assertEqual(context['baseline']['tables']['valuation'],'基准_old__valuation')
        self.assertEqual(result[PREFERRED]['evidence'][0]['old']['version_id'],'old')

    def test_parameter_wrapper_publishes_version_context_and_exact_comparison(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);source=folder/'input';output=folder/'output';source.mkdir();output.mkdir()
            (source/'parameter_comparison.json').write_text(json.dumps({'baseline':tables('10.89'),'baseline_id':'run1','scenario_id':'run2','parameters':{'wacc':{'old':'.122','new':'.127'}},'order':None}),encoding='utf8')
            (output/'numeric_tables.json').write_text(json.dumps({'tables':tables('9.41')}),encoding='utf8')
            deliver_parameter_comparison(source,output)
            context=json.loads((output/'scenario_bindings.json').read_text(encoding='utf8'))
            values=json.loads((output/'numeric_tables.json').read_text(encoding='utf8'))['tables']
            self.assertEqual(values[context['baseline']['tables']['valuation']]['rows'][0]['price'],'10.89')
            self.assertEqual(values[context['scenario']['tables']['valuation']]['rows'][0]['price'],'9.41')
            self.assertIn('差额（情景减基准）',bind_text(context['preferred_embedding'],values))

if __name__=='__main__':unittest.main()

import copy,csv,json,tempfile,unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from service.analysis_report import compile_report,display_table,render_table,bind_text,write_csv,save_table,ROUNDING_NOTE
from service.analysis_comparison import deliver_parameter_comparison
from service.analysis_tables import table_view
from service.core import FinanceService
from service.financial_workpapers import statement_analysis
from service.model_comparison import compare_models

def fixture():
    return {'columns':{'value':{'unit':'元/股','currency':'HKD','decimals':2}},'row_keys':['a','b','total'],
            'rows':[{'value':'-0.50691375150637'},{'value':'-0.97674473384680'},{'value':'-1.48365848535317'}],
            'sum_relations':[{'parts':[{'row':'a','column':'value'},{'row':'b','column':'value'}],'total':{'row':'total','column':'value'}}]}

class DisplaySumTests(unittest.TestCase):
    def test_signed_largest_remainders_share_one_view_without_changing_exact_rows_or_csv(self):
        table=fixture();before=copy.deepcopy(table);view=display_table(table)
        self.assertEqual([r['value'] for r in view['rows']],['-0.51','-0.97','-1.48'])
        self.assertIn(ROUNDING_NOTE,render_table(table));self.assertEqual(table,before)
        self.assertEqual(table_view(table)['rows'],before['rows'])
        self.assertIn('-0.97',table_view(table)['display_rows'][1]['value'])
        self.assertIn('-0.97 HKD 元/股',bind_text('{{t.b.value}}',{'t':table}))
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'table.csv';write_csv(path,table)
            with path.open(encoding='utf-8-sig') as handle:rows=list(csv.DictReader(handle))
            self.assertEqual(list(rows[1].values()),['-0.97674473384680'])

    def test_positive_horizontal_composition_and_no_inference_from_total_label(self):
        table={'columns':{k:{'unit':'%','decimals':0} for k in ('a','b','c','total')},'rows':[{'a':'33.33','b':'33.33','c':'33.34','total':'100'}],'row_keys':['mix']}
        self.assertEqual(display_table(table)['rows'],table['rows'])
        table['sum_relations']=[{'parts':[{'row':'mix','column':k} for k in ('a','b','c')],'total':{'row':'mix','column':'total'}}]
        self.assertEqual(display_table(table)['rows'][0],{'a':'33','b':'33','c':'34','total':'100'})

    def test_missing_and_actual_discrepancies_are_not_hidden(self):
        table=fixture();table['rows'][0]['value']=None
        self.assertEqual(display_table(table)['rows'],table['rows']);self.assertIn('缺失',display_table(table)['notes'][0])
        table=fixture();table['rows'][2]['value']='100'
        self.assertEqual(display_table(table)['rows'],table['rows']);self.assertNotIn(ROUNDING_NOTE,display_table(table)['notes'])

    def test_carote_cash_bridge_relationships_at_two_and_four_decimals(self):
        facts=json.loads((Path(__file__).parent/'fixtures/workpapers/carote.json').read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory() as root:
            service=FinanceService(root);service.create_project('p','test')
            with patch('service.financial_workpapers.load_facts',return_value=facts):raw,records=statement_analysis(service,'p')
            table=compile_report(raw,records)['tables']['bridge'];original=copy.deepcopy(table['rows'])
            for decimals in (2,4):
                table['columns']['amount']['decimals']=decimals;display=display_table(table);values={key:Decimal(row['amount']) for key,row in zip(table['row_keys'],display['rows'])}
                self.assertEqual(len(table['sum_relations']),4)
                for relation in table['sum_relations']:
                    self.assertEqual(sum(values[part['row']] for part in relation['parts']),values[relation['total']['row']])
                self.assertIn(ROUNDING_NOTE,display['notes']);self.assertEqual(table['rows'],original)

    def test_save_table_and_parameter_contributions_declare_relations(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);source=folder/'input';output=folder/'output';source.mkdir();output.mkdir()
            raw=fixture();raw['columns']={'key':{},**raw['columns']}
            for key,row in zip(raw['row_keys'],raw['rows']):row['key']=key
            table=save_table('direct',raw['columns'],raw['rows'],input_dir=source,output_dir=output,sum_relations=raw['sum_relations'])
            self.assertIn('-0.97',render_table(table))
            def tables(value):return {'t':{'columns':{'value':{'unit':'元/股','currency':'HKD','decimals':2}},'row_keys':['price'],'rows':[{'value':value}]}}
            (source/'parameter_comparison.json').write_text(json.dumps({'baseline':tables('10'), 'steps':[tables('9.49308624849363')], 'baseline_id':'old','scenario_id':'new','parameters':{},'order':['wacc','fcf']}),encoding='utf8')
            (output/'numeric_tables.json').write_text(json.dumps({'tables':tables('8.51634151464683')}),encoding='utf8')
            deliver_parameter_comparison(source,output)
            contributions=json.loads((output/'numeric_tables.json').read_text(encoding='utf8'))['tables']['parameter_contributions']
            self.assertEqual(len(contributions['sum_relations']),1)
            self.assertEqual([r['delta'] for r in display_table(contributions)['rows']],['-0.51','-0.97','-1.48'])
            self.assertEqual(contributions['rows'][1]['delta'],'-0.97674473384680')

if __name__=='__main__':unittest.main()

import copy
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from service.model_delivery import deliver_saved, prepare_delivery, select_models
from service.research_models import evaluate_model
from service.tests.test_research_models import dcf_spec


class DeliveryTests(unittest.TestCase):
    def test_supported_model_amounts_rates_and_days_are_labelled_in_delivered_csv(self):
        from service.research_schema import get_model_example
        with tempfile.TemporaryDirectory() as folder:
            for kind in ('three_statement', 'financial_quality', 'manufacturing_scenario', 'comparables'):
                spec = get_model_example(kind); spec['amount_scale'] = '1000000'
                model = {'kind': kind, 'spec': spec, 'result': evaluate_model(kind, spec)}
                output = Path(folder) / kind; output.mkdir()
                prepare_delivery(output, {'saved': model}, {})
                with (output / 'saved_inputs.csv').open(encoding='utf-8-sig') as file:
                    inputs = {row['path']: row for row in csv.DictReader(file)}
                with (output / 'saved_units.csv').open(encoding='utf-8-sig') as file:
                    units = {(row['table'], row['column']): row['unit'] for row in csv.DictReader(file)}
                if kind == 'three_statement':
                    for field in ('interest_rate', 'opex_ratio', 'revenue_growth', 'gross_margin', 'tax_rate'):
                        self.assertEqual(inputs['forecast.0.' + field]['unit'], 'ratio')
                    for field in ('dso', 'dio', 'dpo', 'days_in_year'):
                        self.assertEqual(inputs['forecast.0.' + field]['unit'], '天')
                    for field in ('base_revenue', 'opening.ppe', 'forecast.0.debt_repayment'):
                        self.assertEqual(inputs[field]['unit'], 'CNY 百万元')
                    for table, rows in model['result']['tables'].items():
                        # Every three-statement output except its calendar year is an amount.
                        for field in rows[0]:
                            if field != 'year':
                                self.assertEqual(units[table, field], 'CNY 百万元', (table, field))
                    self.assertEqual(inputs['forecast.0.interest_rate']['value'], '0.05')
                elif kind == 'financial_quality':
                    self.assertEqual(inputs['periods.1.finance_expense']['unit'], 'CNY 百万元')
                    self.assertEqual(units['quality', 'cash_conversion'], 'ratio')
                    self.assertEqual(units['quality', 'dso'], '天')
                    self.assertEqual(units['attribution', 'revenue_effect'], 'CNY 百万元')
                elif kind == 'manufacturing_scenario':
                    self.assertEqual(inputs['scenario.pass_through_rate']['unit'], 'ratio')
                    self.assertEqual(inputs['baseline.0.unit_price']['unit'], 'CNY 百万元/units')
                    self.assertEqual(units['scenario', 'scenario_volume'], 'units')
                    self.assertEqual(units['scenario', 'scenario_ebit'], 'CNY 百万元')
                else:
                    self.assertEqual(inputs['subject.earnings']['unit'], 'CNY 百万元')
                    self.assertEqual(inputs['subject.shares.count']['unit'], '股')
                    self.assertEqual(inputs['peers.0.eps']['unit'], '')

    def test_selected_revision_csv_and_calculator_reproduce_exact_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);saved=root/'research'/'p'/'artifacts';saved.mkdir(parents=True)
            spec=dcf_spec();model={'id':'m','revision_id':'old','kind':'dcf','spec':spec,'result':evaluate_model('dcf',spec)}
            (saved/'old.json').write_text(json.dumps(model),encoding='utf-8')
            newer=copy.deepcopy(model);newer['revision_id']='new';newer['spec']['discount']['wacc']='0.12'
            (saved/'new.json').write_text(json.dumps(newer),encoding='utf-8')
            selected=select_models(root,'p',{'base':{'artifact_id':'m','revision_id':'old'}})
            self.assertEqual(selected['base'],model)
            with self.assertRaises(FileNotFoundError):select_models(root,'other',{'base':{'artifact_id':'m','revision_id':'old'}})
            files=prepare_delivery(root,selected,{})
            with zipfile.ZipFile(files['model_bundle.zip']) as z:
                self.assertEqual(json.loads(z.read('models.json'))['base'],model)
                self.assertIn('base_forecast.csv',z.namelist())
                self.assertIn('recompute_models.py',z.namelist())
            # Trusted library replay only: no agent-written script is run on host.
            with zipfile.ZipFile(files['finance_model_code.zip']) as z:
                self.assertEqual(z.read('finance_model/research_models.py'),Path('service/research_models.py').read_bytes())
            self.assertEqual(evaluate_model(model['kind'],json.loads(files['models.json'].read_text(encoding='utf-8'))['base']['spec']),model['result'])

    def test_exported_inputs_and_result_columns_state_their_units(self):
        import csv, io
        with tempfile.TemporaryDirectory() as folder:
            spec=dcf_spec();spec['amount_scale']='1000000'
            model={'id':'m','revision_id':'v','kind':'dcf','spec':spec,'result':evaluate_model('dcf',spec)}
            files=prepare_delivery(Path(folder),{'base':model},{})
            read=lambda name:list(csv.DictReader(io.StringIO(files[name].read_text(encoding='utf-8-sig'))))
            inputs={row['path']:row for row in read('base_inputs.csv')}
            self.assertEqual(list(next(iter(inputs.values()))),['path','value','unit','source','basis'])
            # Rates are fractions and say so; amounts carry currency and the model's scale; labels have no unit.
            self.assertEqual((inputs['discount.wacc']['value'],inputs['discount.wacc']['unit']),(spec['discount']['wacc'],'ratio'))
            for path in ('terminal.growth','terminal.roic','forecast.0.tax_rate','forecast.0.ebit_margin'):self.assertEqual(inputs[path]['unit'],'ratio',path)
            for path in ('base.revenue','base.net_working_capital','bridge.net_debt','bridge.non_controlling_interest'):self.assertEqual(inputs[path]['unit'],spec['currency']+' 百万元',path)
            for path in ('currency','cash_tax_policy','base_year','discount.cashflow_timing'):self.assertEqual(inputs[path]['unit'],'',path)
            units={(row['table'],row['column']):row['unit'] for row in read('base_units.csv')}
            self.assertEqual(units[('forecast','revenue')],spec['currency']+' 百万元')
            self.assertEqual(units[('forecast','ebit_margin')],'ratio')
            self.assertEqual(units[('forecast','year')],'')
            self.assertEqual(units[('results','value_per_share')],spec['currency']+'/股')
            self.assertEqual(units[('results','enterprise_value')],spec['currency']+' 百万元')
            self.assertEqual(units[('results','terminal_value_share')],'ratio')
            # Every column of every exported result table is listed, in the table's own order.
            for table,rows in model['result']['tables'].items():
                self.assertEqual([c for t,c in units if t==table],list(dict.fromkeys(key for row in rows for key in row)))
            # The result tables themselves are unchanged, so the bundled calculator still reproduces them.
            self.assertEqual(read('base_forecast.csv')[0]['revenue'],str(model['result']['tables']['forecast'][0]['revenue']))
            with zipfile.ZipFile(files['model_bundle.zip']) as z:
                self.assertIn('base_units.csv',z.namelist())
                self.assertIn('ratio',z.read('README.txt').decode())
            other=copy.deepcopy(model);other['spec']['amount_scale']='1';(Path(folder)/'unscaled').mkdir()
            unscaled=prepare_delivery(Path(folder)/'unscaled',{'b':other},{})['b_inputs.csv'].read_text(encoding='utf-8-sig')
            self.assertEqual({row['path']:row['unit'] for row in csv.DictReader(io.StringIO(unscaled))}['base.revenue'],spec['currency']+' 元')
            # An item of a list has the unit of the list.
            from service.model_units import unit_label
            self.assertEqual([unit_label(model,path) for path in ('sensitivity.wacc.0','sensitivity.growth.2','spec.sensitivity.wacc.1','forecast.0','tables.forecast.0.revenue')],['ratio','ratio','ratio','',spec['currency']+' 百万元'])
            # A comparable peer's own figures are in that peer's currency: only the implied values of the subject are labelled.
            from service.research_schema import get_model_example
            peers=get_model_example('comparables');peers={'id':'c','revision_id':'v','kind':'comparables','spec':peers,'result':evaluate_model('comparables',peers)}
            (Path(folder)/'peers').mkdir();compared=prepare_delivery(Path(folder)/'peers',{'c':peers},{})
            rows=lambda name:list(csv.DictReader(io.StringIO(compared[name].read_text(encoding='utf-8-sig'))))
            self.assertEqual({row['path']:row['unit'] for row in rows('c_inputs.csv') if row['path'].startswith('peers.0.')},{'peers.0.id':'','peers.0.metric_basis':'','peers.0.price':'','peers.0.eps':''})
            listed={(row['table'],row['column']):row['unit'] for row in rows('c_units.csv')}
            self.assertEqual((listed[('peers','multiple')],listed[('peers','value_per_share')],listed[('results','selected_multiple')]),('倍',peers['spec']['currency']+'/股','倍'))
            from service.analysis_report import model_quantity
            with self.assertRaisesRegex(ValueError,'尚无单位元数据'):model_quantity(peers,'spec.peers.0.eps')
            self.assertEqual(model_quantity(peers,'tables.peers.0.value_per_share')['currency'],peers['spec']['currency'])

    def test_saved_versions_are_delivered_once_with_tables_differences_and_calculator(self):
        import csv, hashlib, io, os
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);saved=root/'research'/'p'/'artifacts';saved.mkdir(parents=True)
            spec=dcf_spec();old={'id':'m','revision_id':'old','kind':'dcf','spec':spec,'result':evaluate_model('dcf',spec)}
            changed=copy.deepcopy(spec);changed['discount']['wacc']='0.12';changed['terminal']['growth']='0.01'
            new={'id':'m','revision_id':'new','kind':'dcf','spec':changed,'result':evaluate_model('dcf',changed)}
            for model in (old,new):(saved/(model['revision_id']+'.json')).write_text(json.dumps(model),encoding='utf-8')
            refs={'saved':{'artifact_id':'m','revision_id':'new'},'previous':{'artifact_id':'m','revision_id':'old'}}
            request={'update':{'baseline':'previous','scenario':'saved','order':['discount.wacc','terminal.growth']}}
            delivery=deliver_saved(root,'p',refs,request)
            location=root/delivery['folder']
            self.assertEqual(location.parent,root/'research'/'p'/'deliveries')
            names={f['name'] for f in delivery['files']}
            self.assertEqual(delivery['attachments'],sorted(['saved_forecast.csv','saved_inputs.csv','saved_sensitivity.csv','saved_units.csv','saved_model_bundle.zip',
                                                             'update_decomposition.csv','update_forecast_changes.csv','update_inputs_changed.csv','update_results_changed.csv']))
            self.assertLessEqual(set(delivery['attachments']),names)
            self.assertIn('previous_inputs.csv',names)
            self.assertNotIn('model_bundle.zip',names)
            for item in delivery['files']:
                data=(location/item['name']).read_bytes()
                self.assertEqual((len(data),hashlib.sha256(data).hexdigest()),(item['size'],item['sha256']),item['name'])
            # The differences are the calculator's own: both changed inputs, the value change and its ordered contributions.
            update=delivery['results']['update']
            self.assertEqual([c['path'] for c in update['changed_inputs']],['discount.wacc','terminal.growth'])
            change=update['result_changes']['value_per_share']
            self.assertEqual(change['before'],str(old['result']['results']['value_per_share']))
            self.assertEqual(change['after'],str(new['result']['results']['value_per_share']))
            steps=update['decomposition']['steps']
            self.assertEqual([step['path'] for step in steps],['discount.wacc','terminal.growth'])
            from decimal import Decimal, localcontext
            with localcontext() as exact:
                exact.prec=60
                self.assertEqual(sum(Decimal(step['contribution']) for step in steps),Decimal(change['change']))
            rows=list(csv.DictReader(io.StringIO((location/'update_inputs_changed.csv').read_text(encoding='utf-8-sig'))))
            self.assertEqual([(r['path'],r['before'],r['after']) for r in rows],[('discount.wacc',spec['discount']['wacc'],'0.12'),('terminal.growth',spec['terminal']['growth'],'0.01')])
            with zipfile.ZipFile(location/'saved_model_bundle.zip') as z:
                self.assertEqual(json.loads(z.read('models.json'))['saved'],new)
                self.assertLessEqual({'recompute_models.py','finance_model_code.zip','saved_inputs.csv','previous_inputs.csv','update_decomposition.csv','comparisons.json'},set(z.namelist()))
            # Asking again for the same versions returns the same published files without rewriting them.
            stamp=os.stat(location/'saved_inputs.csv').st_mtime_ns
            again=deliver_saved(root,'p',refs,request)
            self.assertEqual(again,delivery)
            self.assertEqual(os.stat(location/'saved_inputs.csv').st_mtime_ns,stamp)
            self.assertEqual([p.name for p in (root/'research'/'p'/'deliveries').iterdir()],[delivery['delivery_id']])
            self.assertEqual(sorted(p.name for p in location.iterdir()),sorted([*names,'delivery.json']))
            # A delivery interrupted before its manifest is finished on the next request, with a manifest that matches the files.
            (location/'delivery.json').unlink();(location/'saved_inputs.csv').write_text('cut short',encoding='utf-8')
            resumed=deliver_saved(root,'p',refs,request)
            self.assertEqual((resumed['delivery_id'],resumed['attachments'],resumed['results']),(delivery['delivery_id'],delivery['attachments'],delivery['results']))
            for item in resumed['files']:
                data=(location/item['name']).read_bytes()
                self.assertEqual((len(data),hashlib.sha256(data).hexdigest()),(item['size'],item['sha256']),item['name'])
            with zipfile.ZipFile(location/'saved_model_bundle.zip') as z:
                self.assertEqual((location/'saved_inputs.csv').read_bytes(),z.read('saved_inputs.csv'))
            # A single saved model is delivered without a comparison; another project cannot reach these versions.
            single=deliver_saved(root,'p',{'saved':{'artifact_id':'m','revision_id':'old'}},{})
            self.assertNotEqual(single['delivery_id'],delivery['delivery_id'])
            self.assertEqual(single['attachments'],['saved_forecast.csv','saved_inputs.csv','saved_model_bundle.zip','saved_sensitivity.csv','saved_units.csv'])
            self.assertEqual(single['results'],{})
            with self.assertRaises(FileNotFoundError):deliver_saved(root,'other',refs,request)
            with self.assertRaisesRegex(ValueError,'model_revision_not_found_in_project'):deliver_saved(root,'p',{'saved':{'artifact_id':'someone-else','revision_id':'old'}},{})
            self.assertEqual(len(list((root/'research'/'p'/'deliveries').iterdir())),2)

    def test_differences_export_the_same_ordered_contributions(self):
        with tempfile.TemporaryDirectory() as folder:
            spec=dcf_spec();new=copy.deepcopy(spec);new['discount']['wacc']='0.12'
            models={k:{'kind':'dcf','spec':v,'result':evaluate_model('dcf',v)} for k,v in [('base',spec),('new',new)]}
            files=prepare_delivery(Path(folder),models,{'change':{'baseline':'base','scenario':'new','order':['discount.wacc']}})
            change=json.loads(files['comparisons.json'].read_text(encoding='utf-8'))['change']
            self.assertEqual(change['decomposition']['steps'][0]['contribution'],change['result_changes']['value_per_share']['change'])
            self.assertIn('change_decomposition.csv',files)

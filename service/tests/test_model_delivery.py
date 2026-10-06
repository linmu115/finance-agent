import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from service.model_delivery import prepare_delivery, select_models
from service.research_models import evaluate_model
from service.tests.test_research_models import dcf_spec


class DeliveryTests(unittest.TestCase):
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

    def test_differences_export_the_same_ordered_contributions(self):
        with tempfile.TemporaryDirectory() as folder:
            spec=dcf_spec();new=copy.deepcopy(spec);new['discount']['wacc']='0.12'
            models={k:{'kind':'dcf','spec':v,'result':evaluate_model('dcf',v)} for k,v in [('base',spec),('new',new)]}
            files=prepare_delivery(Path(folder),models,{'change':{'baseline':'base','scenario':'new','order':['discount.wacc']}})
            change=json.loads(files['comparisons.json'].read_text(encoding='utf-8'))['change']
            self.assertEqual(change['decomposition']['steps'][0]['contribution'],change['result_changes']['value_per_share']['change'])
            self.assertIn('change_decomposition.csv',files)

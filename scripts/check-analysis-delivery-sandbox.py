"""Deterministic chart/model delivery smoke in the actual isolated runtime."""
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sandbox import create_runner
from service.model_delivery import prepare_delivery
from service.research_models import evaluate_model
from service.tests.test_research_models import dcf_spec
from service.plot_runtime import LAUNCH

trial=ROOT/'data/evaluation/pi-analysis-20261006';export=trial/'delivery-smoke-input';export.mkdir(exist_ok=True)
spec=dcf_spec();spec['sensitivity']={'wacc':['0.08','0.10','0.12'],'growth':['0','0.02']}
model={'id':'fixture','revision_id':'fixture-1','kind':'dcf','spec':spec,'result':evaluate_model('dcf',spec)}
inputs=prepare_delivery(export,{'base':model},{})
code='''import json, runpy, zipfile
from pathlib import Path
import finance_charts as fc
fc.configure('report')
r={'fact_id':'f','value':'137000','currency':'CNY','raw_unit':'千元','period':'2025H1','source_ref':{'page':1,'cell':'B2'}}
values,unit,data=fc.record_values([r],'百万元')
assert values==[0.137] and unit=='CNY 百万元' and data[0]['value']=='137000'
import matplotlib.pyplot as plt
fig,ax=plt.subplots()
bars=fc.plot_amounts(ax,['2025'],['119338'],amount_scale='1000000',display_unit='亿元',kind='bar')
assert bars[0].get_height()==1193.38 and ax.get_ylabel()=='CNY 亿元'
fig.savefig('/output/unit_bound_amounts.png')
fig,ax=fc.waterfall(5,{'减少':-9,'回升':2},end=-1,unit=unit,title='正负跨零与未解释差额')
assert [(p.get_y(),p.get_height()) for p in ax.patches]==[(0,5),(-4,9),(-4,2),(-2,1),(-1,1)]
fig.savefig('/output/waterfall.png')
models=json.load(open('/input/models.json'))
fig,axes=fc.comparison_heatmaps({'基准':models['base']['result'],'相同模型':models['base']['result']})
assert axes[0].images[0].norm is axes[1].images[0].norm
fig.savefig('/output/sensitivity.png')
dest=Path('/output/recomputed');dest.mkdir()
with zipfile.ZipFile('/input/model_bundle.zip') as z:z.extractall(dest)
runpy.run_path(str(dest/'recompute_models.py'),run_name='__main__')
actual=json.loads((dest/'base_recomputed.json').read_text())
assert actual==models['base']['result']
Path('/output/checks.json').write_text(json.dumps({'units':True,'plot_value_and_axis_bound':True,'negative_waterfall':True,'shared_color_axis':True,'bundled_calculator_exact':True}))
'''
(export/'analysis.py').write_text(code,encoding='utf-8');inputs['analysis.py']=export/'analysis.py'
for name in ('finance_charts.py','plot_runtime.py'):inputs[name]=ROOT/'service'/name
if os.environ.get('FINANCE_CHART_HELPER'):inputs['finance_charts.py']=Path(os.environ['FINANCE_CHART_HELPER'])
runner=create_runner(trial/'delivery-smoke')
launch=LAUNCH.replace('setup()\n','setup()\nfrom plot_runtime import deliver_models\ndeliver_models()\n')
result=runner.run(launch,inputs,project_id='analysis-delivery-smoke')
(trial/('delivery-smoke-candidate.json' if os.environ.get('FINANCE_CHART_HELPER') else 'delivery-smoke.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:result.get(k) for k in ('status','run_id','error','stdout','stderr','container_removed')},ensure_ascii=False))
sys.exit(0 if result['status']=='succeeded' else 1)

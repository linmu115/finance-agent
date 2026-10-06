"""Exercise the new delivery path in the real container, without model calls."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from sandbox import create_runner
from service.plot_runtime import LAUNCH

trial = ROOT/'data/evaluation/pi-finance-generalization-20261006'
folder = trial/'presentation-input'; folder.mkdir(parents=True, exist_ok=True)
records = [{'record_id':'r1','value':'78560234000','currency':'HKD','raw_unit':'千元','period':'2029','data_kind':'analyst_forecast','source_ref':{'page':8}},
           {'record_id':'r2','value':'-4302500000','currency':'HKD','period':'2030','data_kind':'analyst_forecast','source_ref':{'page':8}}]
report = {'title':'金额与单位一致性：独立样本', 'theme':'report', 'body':'首年收入 {{forecast.0.revenue}}，次年 {{forecast.1.revenue}}。',
 'tables':{'forecast':{'columns':{'year':{'label':'年度'},'revenue':{'label':'收入','unit':'亿元'}},
                     'rows':[{'year':'2029E','revenue':{'record_id':'r1'}},{'year':'2030E','revenue':{'record_id':'r2'}}]}},
 'charts':[{'table':'forecast','x':'year','y':['revenue'],'kind':'bar','title':'独立数值的金额换算与负值'}]}
code = '''import csv,json,zipfile,runpy,os
from pathlib import Path
from analysis_report import compile_report,render_chart,deliver
records=json.loads(Path('/input/research_records.json').read_text())
report=json.loads(Path('/input/analysis_report.json').read_text())
c=compile_report(report,records)
fig,ax=render_chart(c['tables']['forecast'],report['charts'][0])
assert [bar.get_height() for bar in ax.patches]==[785.60234,-43.025]
assert ax.get_ylabel()=='HKD 亿元'
assert all(bar.get_facecolor()[-1]==0 for bar in ax.patches)
fig.savefig('/output/geometry.png',dpi=180,bbox_inches='tight')
deliver(report)
with open('/output/forecast.csv',encoding='utf-8-sig') as f: rows=list(csv.reader(f))
assert rows[1][1]=='785.60234' and rows[2][1]=='-43.025'
assert '785.60 HKD 亿元' in Path('/output/report.md').read_text()
target=Path('/output/reproduced');target.mkdir()
with zipfile.ZipFile('/output/presentation_bundle.zip') as z:z.extractall(target)
os.chdir(target);runpy.run_path(str(target/'render.py'),run_name='__main__')
assert (target/'output/forecast.csv').read_bytes()==Path('/output/forecast.csv').read_bytes()
assert (target/'output/chart_data.json').read_bytes()==Path('/output/chart_data.json').read_bytes()
Path('/output/checks.json').write_text(json.dumps({'chart_geometry':True,'chart_currency_and_units':True,'forecast_style':True,'csv_exact':True,'body_same_values':True,'bundle_reproduces':True}))
'''
files = {'analysis.py':code,'facts.json':'[]','research_records.json':json.dumps(records),
         'analysis_report.json':json.dumps(report)}
inputs={}
for name, content in files.items():
    (folder/name).write_text(content,encoding='utf-8');inputs[name]=folder/name
for name in ('analysis_report.py','model_units.py','plot_runtime.py'):
    inputs[name]=ROOT/'service'/name
runner=create_runner(trial/'presentation-smoke')
result=runner.run(LAUNCH,inputs,project_id='presentation-smoke')
(trial/'presentation-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:result.get(k) for k in ('status','run_id','error','stdout','stderr','container_removed')},ensure_ascii=False))
sys.exit(0 if result['status']=='succeeded' else 1)

"""Real sandbox smoke with the same plot launcher as the app; no model calls."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox import create_runner
from service.plot_runtime import LAUNCH

trial = ROOT / 'data/evaluation' / os.environ.get('FINANCE_COMPARISON_DIR','pi-analysis-20261005-r2')
script = trial / 'chart-smoke.py'
script.write_text("""from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager
fig, ax = plt.subplots(figsize=(7, 3.8))
ax.bar(['经营利润', '合并净利润', '经营现金流'], [-18.17, 41.098, -30.65])
ax.set(title='中文与负数显示测试', ylabel='人民币百万元')
ax.axhline(0, color='#777777', linewidth=.6)
fig.savefig('/output/chart.png', dpi=150)
Path('/output/data.csv').write_text('指标,数值\\n经营利润,-18.17\\n合并净利润,41.098\\n经营现金流,-30.65\\n', encoding='utf-8-sig')
Path('/output/report.md').write_text('# 中文图表验收\\n合并口径，人民币百万元。', encoding='utf-8')
print([f.name for f in font_manager.fontManager.ttflist if 'CJK' in f.name])
""", encoding='utf-8')
runner = create_runner(trial / 'sandbox-smoke')
availability = runner.availability()
if not availability['available']:
    print(json.dumps(availability));sys.exit(2)
runs=[]
for financial in (False, True):
    inputs={'analysis.py':script,'plot_runtime.py':ROOT/'service/plot_runtime.py'}
    launch=LAUNCH
    if financial:
        inputs['finance_charts.py']=ROOT/'service/finance_charts.py'
        launch=launch.replace('setup()\n',"setup()\nimport finance_charts\nfinance_charts.configure('report')\n")
    runs.append(runner.run(launch,inputs,project_id='analysis-comparison-smoke'))
(trial/'sandbox-smoke.json').write_text(json.dumps({'availability':availability,'runs':runs},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'status':r['status'],'id':r['run_id'],'removed':r.get('container_removed'),'artifacts':r.get('artifacts'),'error':r.get('error')} for r in runs],ensure_ascii=False))
sys.exit(0 if all(r['status']=='succeeded' and r.get('container_removed') for r in runs) else 2)

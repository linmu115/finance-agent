"""Exercise the actual shared Docker launch, without an LLM or project materials."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
folder=ROOT/'docs/evidence/a3-a5-b4-20261007';folder.mkdir(parents=True,exist_ok=True)
service=FinanceService(ROOT/'data/evaluation/a3-a5-b4-20261007');project='a3-shared';service.create_project(project,'A3 shared launch')
code='''import json
from pathlib import Path
import matplotlib.pyplot as plt
fig,ax=plt.subplots()
image=ax.imshow([[0,1],[2,3]],cmap='viridis')
label=ax.text(0,0,'0',color='black',ha='center',va='center')
fig.colorbar(image,ax=ax)
fig.tight_layout()
fig.savefig('/output/shared_plot.png',dpi=100)
Path('/output/render_state.json').write_text(json.dumps({'layout':type(fig.get_layout_engine()).__name__,'label_color':label.get_color(),'data':image.get_array().tolist()}))
'''
results=[]
try:
    for profile in ('prepared','financial'):
        run=service.run_analysis(project,code=code,financial_tools=profile=='financial')['data']['run_id']
        state=service.analysis_futures[run].result();item={'profile':profile,'run_id':run,'state':state};results.append(item)
        (folder/'a3-shared.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
        assert state['status']=='succeeded',state
        status=service.get_analysis_status(project,run)['data'];diag=status['plot_diagnostics']
        artifact=service.get_artifact(project,run,'render_state.json')['data']
        rendered=json.loads((service.store.root/'analysis'/run/'output/render_state.json').read_text(encoding='utf8'))
        assert rendered=={'layout':'ConstrainedLayoutEngine','label_color':'white','data':[[0,1],[2,3]]},rendered
        assert diag['files'][0]['contrast_changes']
        assert not any('plot_diagnostics' in name for name in status['numeric_tables'])
        item.update(rendered=rendered,plot_diagnostics=diag,excluded_from_numeric_tables=True)
        (folder/'a3-shared.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
        print(profile,run,'PASS',flush=True)
finally:service.analysis_pool.shutdown()

"""Execute captured sandbox startup and render synthetic plots in a fresh process."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import matplotlib as mpl
mpl.use('Agg')
mpl.rcdefaults()
from matplotlib import font_manager
from matplotlib.figure import Figure

export=Path(sys.argv[1])
sys.path.insert(0,str(export))
original_savefig,original_tight_layout=Figure.savefig,Figure.tight_layout
before_rc=dict(mpl.rcParams)
launch=(export/'launch.py').read_text(encoding='utf8')
# Execute the unmodified startup prefix of the actual captured launcher. The
# financial profile's model download copying is unrelated to plotting and uses
# container-only absolute paths; it alone is mocked.
with patch('plot_runtime.deliver_models'):
    exec(launch.split('try:\n',1)[0])

import matplotlib.pyplot as plt
fig,ax=plt.subplots(figsize=(7,4))
ax.imshow([[0,1],[2,3]],cmap='viridis')
label=ax.text(0,0,'0',color='black',ha='center',va='center')
ax.set_title('中文图表')
fig.savefig(export/'heat.png',dpi=120)
constrained=fig.get_constrained_layout()
heat_color=label.get_color()
plt.close(fig)

fig,ax=plt.subplots(figsize=(7,4))
ax.bar([0,1],[-18.7,955.2],color=['navy','orange'])
ax.set_ylim(-70,1050);ax.axhline(0,color='gray')
label=ax.annotate('-18.7',(0,-18.7),xytext=(0,-14),textcoords='offset points',ha='center',va='top')
before={'position':list(label.get_position()),'va':label.get_va(),'xy':list(label.xy)}
fig.savefig(export/'negative.png',dpi=120)
after={'position':list(label.get_position()),'va':label.get_va(),'xy':list(label.xy)}
plt.close(fig)

diagnostics=export/'plot_diagnostics.json'
data={
    'savefig_patched':Figure.savefig is not original_savefig,
    'tight_layout_patched':Figure.tight_layout is not original_tight_layout,
    'constrained_layout':constrained,'heat_label_color':heat_color,
    'negative_label_moved':before!=after,'negative_label_before':before,'negative_label_after':after,
    'diagnostics_written':diagnostics.is_file(),
    'installed_cjk_fonts':sorted({font.name for font in font_manager.fontManager.ttflist}&
        {'Noto Sans CJK SC','Noto Sans CJK JP','Microsoft YaHei','SimHei'}),
    'changed_rc_keys':sorted(k for k,v in mpl.rcParams.items() if v!=before_rc[k]),
    'rc':{k:mpl.rcParams[k] for k in ('font.family','font.sans-serif','axes.unicode_minus',
        'savefig.bbox','savefig.pad_inches','figure.autolayout','figure.constrained_layout.use')},
}
if diagnostics.is_file():
    data['diagnostics']=json.loads(diagnostics.read_text(encoding='utf8'))
    for entry in data['diagnostics']['files']:entry['file']=Path(entry['file']).name
(export/'probe.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

"""Shared plot defaults for every sandbox profile, including the generic baseline."""
def setup():
    import matplotlib as mpl
    from matplotlib import font_manager
    installed={font.name for font in font_manager.fontManager.ttflist}
    fonts=[name for name in ('Noto Sans CJK SC','Noto Sans CJK JP','Microsoft YaHei','SimHei') if name in installed]
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':fonts+['DejaVu Sans'],
        'axes.unicode_minus':False,'savefig.bbox':'tight','savefig.pad_inches':0.2})
    if not fonts:
        import warnings
        warnings.warn('没有可用的中文字体；中文图表可能缺字。',RuntimeWarning)


def deliver_models():
    import json, shutil, zipfile
    from pathlib import Path
    root=Path('/input')
    if not json.loads((root/'models.json').read_text(encoding='utf-8')):return
    shutil.copyfile(root/'model_bundle.zip','/output/model_bundle.zip')
    # Make already-calculated tables available as direct downloads as well.
    with zipfile.ZipFile(root/'model_bundle.zip') as z:
        for name in z.namelist():
            if name.endswith(('.csv','.json')):
                (Path('/output')/name).write_bytes(z.read(name))


LAUNCH = '''import runpy, shutil, sys
from pathlib import Path
sys.path.insert(0, '/input')
from plot_runtime import setup
setup()
try:
    runpy.run_path('/input/analysis.py', run_name='__main__')
    if Path('/input/analysis_report.json').exists() or Path('/output/analysis_report.json').exists():
        from analysis_report import deliver
        deliver()
finally:
    shutil.copyfile('/input/analysis.py', '/output/executed_script.py')
'''

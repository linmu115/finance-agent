import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FIXTURES=Path(__file__).resolve().parents[2]/'tests/fixtures/f21'


@unittest.skipUnless(importlib.util.find_spec('matplotlib'),'Run in the plot environment')
class F21WaterfallTests(unittest.TestCase):
    def setUp(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from service import plot_runtime
        self.plt=plt;self.runtime=plot_runtime;plot_runtime.setup();plot_runtime._DIAGNOSTICS.clear()
        self.addCleanup(plt.close,'all')

    def test_full_f203_scripts_mark_actual_broken_bars_and_never_modify_geometry(self):
        for name in ('F2_X3','G2_X3'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                code=(FIXTURES/(name+'.py')).read_text('utf8').replace("'/output'",repr(Path(tmp).as_posix()))
                self.runtime._DIAGNOSTICS.clear();geometries=[]
                check=self.runtime.waterfall_issues
                def inspect(fig):
                    before=[(p.get_y(),p.get_height()) for ax in fig.axes for c in ax.containers for p in c.patches]
                    issues=check(fig)
                    self.assertEqual(before,[(p.get_y(),p.get_height()) for ax in fig.axes for c in ax.containers for p in c.patches])
                    geometries.append(before);return issues
                with patch.object(self.runtime,'waterfall_issues',inspect):exec(compile(code,name+'.py','exec'),{'__name__':'__main__'})
                diagnostics=json.loads((Path(tmp)/'plot_diagnostics.json').read_text('utf8'))
                if target:=os.environ.get('F21_EVIDENCE_DIR'):
                    out=Path(target);out.mkdir(parents=True,exist_ok=True)
                    (out/(name+'-waterfall.json')).write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf8')
                issues=[i for f in diagnostics['files'] for i in f['waterfall_issues']]
                self.assertTrue(geometries);self.assertTrue(issues);self.assertTrue(all(i['bar_number']>=1 for i in issues))
                self.assertEqual(issues[0]['bar_number'],1)
                self.assertTrue(all('hint' not in i for i in issues))

    def test_house_waterfall_and_signed_or_absolute_heights(self):
        from service.finance_charts import waterfall
        for start in (0,10,-10):
            fig,_=waterfall(start,{'A':5,'B':-3,'C':-18,'D':9})
            self.assertEqual(self.runtime.waterfall_issues(fig),[])
        for absolute in (False,True):
            fig,ax=self.plt.subplots();current=0
            for i,v in enumerate((10,-3,5,-20,8)):
                ax.bar(i,abs(v) if absolute else v,bottom=min(current,current+v) if absolute else current)
                current+=v
            ax.bar(5,abs(current) if absolute else current,bottom=min(0,current) if absolute else 0)
            self.assertEqual(self.runtime.waterfall_issues(fig),[])

    def test_ordinary_grouped_and_stacked_bars_not_waterfalls(self):
        fig,ax=self.plt.subplots();ax.bar([0,1,2],[10,-3,4]);self.assertEqual(self.runtime.waterfall_issues(fig),[])
        fig,ax=self.plt.subplots();ax.bar([0,1,2],[1,-2,3],bottom=5,width=.3);ax.bar([.3,1.3,2.3],[-1,2,-3],bottom=8,width=.3)
        self.assertEqual(self.runtime.waterfall_issues(fig),[])
        fig,ax=self.plt.subplots();ax.bar([0,1,2],[3,4,5]);ax.bar([0,1,2],[2,-1,3],bottom=[3,4,5])
        self.assertEqual(self.runtime.waterfall_issues(fig),[])

    def test_financial_hint_and_precise_middle_failure(self):
        self.runtime.setup(financial=True);fig,ax=self.plt.subplots()
        ax.bar([0,1,2],[10,-3,4],bottom=[0,7,7]);ax.set_xticks([0,1,2],['start','bad','last'])
        issues=self.runtime.waterfall_issues(fig)
        self.assertEqual(len(issues),1);self.assertEqual(issues[0]['bar_number'],2);self.assertEqual(issues[0]['label'],'bad')
        self.assertEqual(issues[0]['expected_endpoint'],10);self.assertEqual(issues[0]['endpoints'],[7,4])
        self.assertIn('finance_charts.waterfall',issues[0]['hint'])


if __name__=='__main__':unittest.main()

"""Shared report API through Docker in prepared/financial mode, without a model."""
import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.analysis_report import ROUNDING_NOTE
from service.tests.test_display_sums import fixture
root=ROOT/'data/evaluation/display-sums-20261007'
service=FinanceService(root);project='display-sums';service.create_project(project,'Display sum deterministic replay')
folder=ROOT/'docs/evidence/display-sums-20261007';results=[]
try:
    for profile in ('prepared','financial'):
        table=fixture();report={'title':'显示精度贡献表','tables':{'contributions':table},'body':'{{table:contributions}}'}
        run=service.run_analysis(project,report=report,financial_tools=profile=='financial')['data']['run_id']
        state=service.analysis_futures[run].result();item={'profile':profile,'run_id':run,'state':state};results.append(item)
        (folder/'sandbox.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
        assert state['status']=='succeeded',state
        status=service.get_analysis_status(project,run)['data'];got=status['numeric_tables']['contributions']
        assert got['rows']==table['rows'];assert [r['value'] for r in got['display_rows']]==['-0.51 HKD 元/股','-0.97 HKD 元/股','-1.48 HKD 元/股']
        answer=service.render_answer(project,'{{table:contributions}}',status['numeric_tables'])['data']['body']
        output=root/'analysis'/run/'output';markdown=(output/'report.md').read_text(encoding='utf8')
        with (output/'contributions.csv').open(encoding='utf-8-sig') as handle:rows=list(csv.DictReader(handle))
        assert [list(r.values())[0] for r in rows]==[r['value'] for r in table['rows']]
        assert ROUNDING_NOTE in markdown and ROUNDING_NOTE in answer
        assert '-0.97' in markdown and '-0.97' in answer
        item.update(exact_table_unchanged=True,csv_unchanged=True,display_rows=got['display_rows'],report_and_answer_same_rounding=True,note_present=True)
        (folder/'sandbox.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
        print(profile,run,'passed',flush=True)
finally:service.analysis_pool.shutdown()

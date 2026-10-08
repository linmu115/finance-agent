"""Replay only the explicitly named development snapshots; no live DB writes."""
import argparse
from contextlib import contextmanager
from decimal import Decimal,localcontext
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.store import Store
from service.analysis_report import compile_report,render_report
from service.workpaper_periods import load_period_series,period_analysis
from service.period_algebra import change


class Snapshot(Store):
    def __init__(self,path):self.path=Path(path).resolve();self.root=self.path.parent
    @contextmanager
    def connect(self,write=False):
        if write:raise ValueError('snapshot is read only')
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='current_financial_facts'").fetchone():
            db.execute('CREATE TEMP VIEW current_financial_facts AS SELECT rowid,* FROM facts')
        try:yield db
        finally:db.close()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--old-copy',required=True);ap.add_argument('--current-copy',required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    result={'llm_calls':0,'database_mode':'read-only snapshots','cases':[]}
    for label,path,pid,did in [('yili',args.old_copy,'b43ae45c-d96b-43b6-ab5b-04306c0eb142','1f94f25a3cb74d528f10ddac0be06a0d'),
        ('ruihe',args.current_copy,'374beac2-a970-4972-b210-e91018bbd6e6','ab25c52089fd4db89fba046c9c811c46'),
        ('carote',args.current_copy,'03b52dde-19da-49c1-949a-ee6d93bf036b','3d9d0befd8374eed9a7488dbd8dd00d2')]:
        service=FinanceService.__new__(FinanceService);service.store=Snapshot(path)
        with localcontext() as ctx:
            ctx.prec=40
            series=load_period_series(service,pid,did);raw,records=period_analysis(service,pid,did);report=compile_report(raw,records)
            manual=[]
            # Independently recompute every available growth value from amounts.
            for group,modes in [('quarters',('qoq','yoy')),('cumulatives',('ytd_yoy',))]:
                lookup={(x['metric'],x['period']):x for x in series[group]}
                for row in raw['tables']['changes']['rows']:
                    if row['mode'] not in modes or row['growth']['value'] is None:continue
                    a=lookup[(row['metric'],row['period'])];b=lookup[(row['metric'],row['comparison'])]
                    expected=(Decimal(a['quantity']['value'])-Decimal(b['quantity']['value']))/Decimal(b['quantity']['value'])*100
                    assert abs(expected-Decimal(row['growth']['value']))<Decimal('1e-30')
                    manual.append({'metric':row['metric'],'period':row['period'],'comparison':row['comparison'],'mode':row['mode'],'computed':row['growth']['value'],'manual':str(expected),'match':True})
        folder=args.output/label;folder.mkdir(parents=True,exist_ok=True);render_report(report,folder)
        (folder/'raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        checks=[{'metric':r['metric'],'period':r['period'],'reported':r['disclosed']['quantity'],'derived':r['derived']['quantity'],'residual':r['residual']} for r in series['reconciliations']]
        if label=='yili':
            q4=[r for r in checks if r['period']=='2024-Q4'];assert len(q4)==4
            assert all(Decimal(r['residual']['value'])==0 for r in q4)
        result['cases'].append({'label':label,'document_id':did,'quarters':len(series['quarters']),'cumulatives':len(series['cumulatives']),
            'reconciliations':checks,'growth_manual':manual,'unknown_rows':series['unknown_rows'],'unrecognized_periods':series['unrecognized_periods']})
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps([{'label':c['label'],'quarters':c['quarters'],'growth_checks':len(c['growth_manual']),'reconciliations':len(c['reconciliations'])} for c in result['cases']],ensure_ascii=False))


if __name__=='__main__':main()

"""Offline K4 acceptance. Reads an already-copied SQLite with mode=ro."""
import argparse
from decimal import Decimal as D, localcontext
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.store import Store
from service.financial_workpapers import financial_workpaper
from service.report_package import prepare
from service.analysis_report import convert


class Snapshot(Store):
    def __init__(self,path,output):self.path=Path(path).resolve();self.root=Path(output).resolve()
    @contextmanager
    def connect(self,write=False):
        if write:raise ValueError('acceptance snapshot is read-only')
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--output',required=True)
    p.add_argument('--project',default='374beac2-a970-4972-b210-e91018bbd6e6');p.add_argument('--company',default='伊利')
    p.add_argument('--period',default='2024');p.add_argument('--as-of',default='2024-12-31')
    p.add_argument('--verify-yili',action='store_true',help='Check the frozen, visually verified 2024 acceptance values')
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    svc=FinanceService.__new__(FinanceService);svc.store=Snapshot(a.db,out/'artifacts')
    result=financial_workpaper(svc,a.project,'expectations',company=a.company,periods=a.period,as_of=a.as_of)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    if a.verify_yili:
        expected=json.loads((Path(__file__).resolve().parents[1]/'service/tests/fixtures/workpapers/expectations_verified.json').read_text('utf8'))
        tabs=result['numeric_tables']
        def original(row,t):
            unit=t['columns']['value']['unit'];return D(convert(row['value'],unit,'元' if unit=='百万元' else unit))
        observed={r['record']:original(r,t) for n,t in tabs.items() if n.startswith(('ledger_','excluded_')) for r in t['rows']}
        actuals={r['key']:original(r,t) for n,t in tabs.items() if n.startswith('actuals_') for r in t['rows']}
        for rid,value in expected['forecast_values'].items():assert observed[rid]==D(value),rid
        for rid,value in expected['annual_values'].items():assert actuals[rid]==D(value),rid
        gaps=[r for n,t in tabs.items() if n.startswith('reference_gaps_') for r in t['rows']]
        assert len(gaps)==6
        for r in gaps:
            assert r['published_at']==expected['latest'][r['institution']]
            scale=D(1) if r['metric']=='eps' else D(1000000)
            assert D(r['difference'])*scale==D(expected['reference_differences'][r['key']])
            with localcontext() as ctx:
                ctx.prec=40
                assert D(r['difference_rate'])==D(r['difference'])/abs(D(r['forecast']))*100
        late=[r for n,t in tabs.items() if n.startswith('excluded') for r in t['rows'] if r['publisher']=='国信证券']
        assert late and all(r['status']=='晚于预测截止日' for r in late)
        assert not any(r['publisher']=='国信证券' for n,t in tabs.items() if n.startswith(('ledger','actual_vs_expected','revisions')) for r in t['rows'])
        assert tabs['version_links_CNY_per_share']['rows'][0]['change']=='-0.16'
        assert tabs['version_links_CNY_money']['rows'][0]['change'] is None
        assert len(tabs['missing']['rows'])==4
        summary={'verified_source_values':12,'money_unit':'CNY 百万元','eps_unit':'CNY 元/股','reference_gaps':gaps,'post_cutoff_excluded':len(late),'unknown_parent_identity_separate':True,'interim_fy_labels_excluded':4,
                 'ranking':'No same-basis ranking: forecast accounting scope unspecified; EPS bases differ.',
                 'table_rows':{n:len(t['rows']) for n,t in tabs.items()}}
        (out/'acceptance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
        (out/'numeric-tables.json').write_text(json.dumps(tabs,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    snapshot={'project_id':a.project,'conversation_id':'offline-expectations-acceptance','title':'伊利 2024 预期差验收（离线工具回放）',
              'turns':[{'id':'k4','created_at':'2026-10-08','body':'【事实/数据】预测冻结截至 2024-12-31。差額中未对齐的口径见数值参照表，未作为同口径误差排名。','sources':[], 'tables':result['numeric_tables']}]}
    package=prepare(svc,a.project,snapshot)
    (out/'package.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'tables':{k:len(v['rows']) for k,v in result['numeric_tables'].items()},'package_id':package['package_id']},ensure_ascii=False))
    for name,t in result['numeric_tables'].items():
        if name.startswith(('reference_gaps','version_links')):print(name,json.dumps(t['rows'],ensure_ascii=False))


if __name__=='__main__':main()

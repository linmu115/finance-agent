"""Source-only basis validation. SQLite inputs are copied snapshots, read only.

Optional candidate PDF preview does not ingest it or produce normalized facts.
It exercises the pure original-table adapter, separate from service acceptance.
"""
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
from service.workpaper_basis import basis_changes,extract_adjustment_pairs,quantify_restatement


class Snapshot(Store):
    def __init__(self,path):self.path=Path(path).resolve();self.root=self.path.parent
    @contextmanager
    def connect(self,write=False):
        if write:raise ValueError('snapshot is read only')
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='current_financial_facts'").fetchone():db.execute('CREATE TEMP VIEW current_financial_facts AS SELECT rowid,* FROM facts')
        try:yield db
        finally:db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--old-copy',required=True);p.add_argument('--current-copy',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--candidate-pdf',type=Path);a=p.parse_args()
    result={'llm_calls':0,'ingestion':0,'cases':[]}
    cases=[('yili',a.old_copy,'b43ae45c-d96b-43b6-ab5b-04306c0eb142','1f94f25a3cb74d528f10ddac0be06a0d'),('ruihe',a.current_copy,'374beac2-a970-4972-b210-e91018bbd6e6','ab25c52089fd4db89fba046c9c811c46')]
    for name,path,pid,did in cases:
        s=FinanceService.__new__(FinanceService);s.store=Snapshot(path)
        with localcontext() as ctx:
            ctx.prec=40;raw,records=basis_changes(s,pid,did);report=compile_report(raw,records)
        folder=a.output/name;folder.mkdir(parents=True,exist_ok=True);render_report(report,folder)
        (folder/'raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        t=raw['tables'];summary=t['summary']['rows'][0]
        assert not summary['restatement_detected'],(name,summary)
        result['cases'].append({'name':name,'summary':summary,'markers':t['markers']['rows'],'repeated_nonrecurring':t['repeated_nonrecurring']['rows'],'unrecognized':t['unrecognized']['rows']})
    if a.candidate_pdf:
        import fitz
        doc=fitz.open(a.candidate_pdf);pages={};tables=[]
        # Full candidate file is inspected; every paired table is retained,
        # including unrecognized labels and notes. No project is created.
        for n,page in enumerate(doc,1):
            pages[n]=page.get_text()
            for i,t in enumerate(page.find_tables().tables,1):tables.append({'table_id':f'candidate:p{n}:t{i}','page':n,'rows':t.extract()})
        pairs,unknown=extract_adjustment_pairs(tables,pages,'candidate-cas-annual',2024,'CNY','consolidated_CAS')
        changes,ratios=quantify_restatement(pairs)
        assert len(pairs)==11,'Haier CAS comparative table should retain six amounts and five per-share/ROE rows'
        matched=[]
        for item in changes:
            for version in ('original','restated'):
                q=item[version];ref=q['source']
                assert q['value'] is not None
                assert q['value'] in pages[ref['page']].replace(',','').replace(' ','').replace('\n','')
                matched.append({'metric':item['metric'],'period':item['period'],'version':version,'value':q['value'],'unit':q['unit'],'source':ref})
            with localcontext() as ctx:
                ctx.prec=40
                assert Decimal(item['delta']['value'])==Decimal(item['restated']['value'])-Decimal(item['original']['value'])
        weighted=next(r for r in ratios if r['ratio']=='weighted_roe')
        assert Decimal(weighted['impact_pp']['value'])==Decimal('0.39')
        # Candidate report table layout is inspected in memory only. No facts
        # or financial-service project is populated before material approval.
        result['candidate_preview']={'file':str(a.candidate_pdf),'pages':len(doc),'method':'pure source-table calculation; not ingested/service end-to-end acceptance',
            'pairs':pairs,'changes':changes,'ratio_impacts':ratios,'unrecognized':unknown,'source_checks':matched}
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'cases':[(x['name'],x['summary'],len(x['repeated_nonrecurring'])) for x in result['cases']],
        'candidate_pairs':len(result.get('candidate_preview',{}).get('pairs',[]))},ensure_ascii=False))


if __name__=='__main__':main()

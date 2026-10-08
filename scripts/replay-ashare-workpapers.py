"""Read ONLY explicit copied SQLite files; old schema view lives in TEMP memory.

No Store initialization/migration, ingestion, LLM call or original database write.
The PDF text checks supplement the recorded visual review, not replace it.
"""
import argparse
from contextlib import contextmanager
from decimal import Decimal,localcontext
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.store import Store
from service.financial_workpapers import statement_analysis
from service.workpaper_comparison import comparison
from service.analysis_report import compile_report,convert,render_report


class ReadOnlyCopy(Store):
    def __init__(self,path):self.path=Path(path).resolve();self.root=self.path.parent
    @contextmanager
    def connect(self,write=False):
        if write:raise ValueError('acceptance snapshot is read only')
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='current_financial_facts'").fetchone():
            db.execute('CREATE TEMP VIEW current_financial_facts AS SELECT rowid,* FROM facts')
        try:yield db
        finally:db.close()


def run(path,project,document,kind,output):
    s=FinanceService.__new__(FinanceService);s.store=ReadOnlyCopy(path)
    with localcontext() as ctx:
        ctx.prec=40
        raw,records=(comparison if kind=='comparison' else statement_analysis)(s,project,document)
        report=compile_report(raw,records)
    output.mkdir(parents=True,exist_ok=True);render_report(report,output)
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    return raw,report


def main():
    p=argparse.ArgumentParser();p.add_argument('--old-copy',type=Path,required=True);p.add_argument('--current-copy',type=Path,required=True)
    p.add_argument('--pdf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    project='b43ae45c-d96b-43b6-ab5b-04306c0eb142';doc='1f94f25a3cb74d528f10ddac0be06a0d'
    raw,yili=run(a.old_copy,project,doc,'statement_analysis',a.output/'yili')
    _,comp=run(a.old_copy,project,doc,'comparison',a.output/'comparison')
    import fitz
    pdf=fitz.open(a.pdf);spot=[]
    def clean(text):return re.sub(r'\s+','',text).replace(',','').replace('−','-').replace('－','-')
    # Every disclosed nonblank cell in these acceptance sections is checked.
    for name,columns in [('nonrecurring_items',('2024-FY','2023-FY')),('indirect_bridge',('amount',)),('quarterly',('Q1','Q2','Q3','Q4')),('roe',('weighted','begin','end')),('deducted_profit',('disclosed',))]:
        for row in raw['tables'][name]['rows']:
            for key in columns:
                q=row[key]
                if q['value'] is None:continue
                ref=q['source'].get('source_ref',q['source'])
                if not ref.get('page'):continue # residuals/other calculations are separately reconciled
                text=clean(pdf[ref['page']-1].get_text());value=clean(str(q['value']))
                assert value in text,(name,row['key'],key,value,ref['page'])
                actual=next(r for r in yili['tables'][name]['rows'] if r['key']==row['key'])[key]
                unit=yili['tables'][name]['columns'][key]['unit']
                assert Decimal(actual)==Decimal(convert(q['value'],q['unit'],unit))
                spot.append({'table':name,'row':row['key'],'column':key,'value':q['value'],'unit':q['unit'],'pdf_page':ref['page'],
                             'source_table':ref.get('table_id'),'source_row':ref.get('row'),'source_column':ref.get('column'),'source_column_label':ref.get('column_label'),'match':True})
    assert len(spot)>=30
    y=yili['tables'];residuals={k:[r['amount'] if k in ('bridge','indirect_bridge') else r['residual'] for r in y[k]['rows'] if k not in ('bridge','indirect_bridge') or r['direction']=='残差'] for k in ('bridge','indirect_bridge','deducted_profit','quarterly_reconciliation')}
    assert all(Decimal(v)==0 for values in residuals.values() for v in values),residuals
    regression=[]
    for name,proj,did in [('ruihe','374beac2-a970-4972-b210-e91018bbd6e6','ab25c52089fd4db89fba046c9c811c46'),('carote','03b52dde-19da-49c1-949a-ee6d93bf036b','3d9d0befd8374eed9a7488dbd8dd00d2')]:
        _,r=run(a.current_copy,proj,did,'statement_analysis',a.output/name);t=r['tables']
        residual=[v['amount'] for v in t['bridge']['rows'] if v['direction']=='残差'];assert all(Decimal(v)==0 for v in residual)
        regression.append({'company':name,'residuals':residual,'income':t['income']['rows'],'profit':t['profit_attribution']['rows'],
                           'unrecognized':t['unrecognized_rows']['rows'],'missing':t['missing']['rows'],'observations':t['observations']['rows']})
    result={'llm_calls':0,'ingestion':0,'database_mode':'ro; legacy view TEMP only','source_pdf':str(a.pdf.resolve()),
            'visually_reviewed_pdf_pages':[7,8,9,217,218],'checked_values':len(spot),'spot_checks':spot,'yili_residuals':residuals,
            'deducted_profit':y['deducted_profit']['rows'],'roe':y['roe']['rows'],'indirect_contributions':y['indirect_contributions']['rows'],
            'quarterly':y['quarterly']['rows'],'observations':y['observations']['rows'],'unrecognized_rows':y['unrecognized_rows']['rows'],
            'remaining_missing':y['missing']['rows'],'comparison_columns':comp['tables']['report_columns']['rows'],'regression':regression}
    (a.output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'checked_values':len(spot),'yili_residuals':residuals,'unrecognized':len(result['unrecognized_rows']),'regression':[(r['company'],r['residuals']) for r in regression]},ensure_ascii=False))


if __name__=='__main__':main()

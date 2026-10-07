"""Run against a COPY of finance.sqlite; writes deliveries only beneath that copied data root."""
import argparse
import json
from decimal import Decimal
from pathlib import Path
from service.core import FinanceService


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-copy',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    service=FinanceService(args.data_copy)
    result={'kind':'statement_analysis','llm_calls':0,'new_ingestion':0,'cases':[]}
    for name,project,document,reference in [
        ('carote','03b52dde-19da-49c1-949a-ee6d93bf036b','3d9d0befd8374eed9a7488dbd8dd00d2',
         {'revenue':'836.925','cfo':'-18.676','consolidated':'102.791','parent':'102.785','cash_end':'384.364','gross_margin_change':'-7.7321'}),
        ('ruihe','374beac2-a970-4972-b210-e91018bbd6e6','ab25c52089fd4db89fba046c9c811c46',
         {'revenue':'120.392','cfo':'-30.65','consolidated':'41.098','parent':'43.186','cash_end':'25.723'})]:
        response=service.financial_workpaper(project,document_id=document)
        assert response['status']=='ok',response
        data=response['data'];tables=data['report']['tables']
        def row(t,k):return next(r for r in tables[t]['rows'] if r['key']==k)
        actual={'revenue':row('income','revenue')['2025-H1'],'cfo':row('cash','2025-H1_cfo')['amount'],
                'consolidated':row('profit_attribution','2025-H1')['consolidated'],'parent':row('profit_attribution','2025-H1')['parent'],
                'cash_end':row('bridge','2025-H1_cash_end')['amount'],
                'gross_margin_change':str(round(Decimal(row('ratios','gross_profit_margin')['change_pp']),4))}
        for k,v in reference.items():assert Decimal(actual[k])==Decimal(v),(name,k,actual[k],v)
        residuals=[r['amount'] for r in tables['bridge']['rows'] if r['direction']=='残差']
        assert residuals==['0']*4
        interest=[r for r in tables['bridge']['rows'] if 'interest received' in r['item'].lower()]
        if name=='carote':assert [r['direction'] for r in interest]==['加','加']
        folder=service.store.root/'research'/project/'deliveries'/data['delivery']['id']
        assert json.loads((folder/'chart_data.json').read_text(encoding='utf-8'))==data['report']
        result['cases'].append({'name':name,'project':project,'document':document,'reference':reference,'actual':actual,
                                'bridge_residuals':residuals,'interest_directions':interest,'tables':len(tables),
                                'delivery_files':len(data['delivery']['files']),'source_locators':len(response['source_refs']),
                                'tables_data':{k:v['rows'] for k,v in tables.items()}})
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({c['name']:c['actual'] for c in result['cases']},ensure_ascii=False))


if __name__=='__main__':main()

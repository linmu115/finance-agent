"""Audit the already prepared research documents from an isolated SQLite copy."""
import argparse
from collections import Counter
import json
from pathlib import Path
from service.core import FinanceService


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-copy',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();s=FinanceService(args.data_copy)
    result={'kind':'report_audit','llm_calls':0,'new_ingestion':0,'cases':[]}
    for name,project,doc in [('cmbi','03b52dde-19da-49c1-949a-ee6d93bf036b','cebeadc4df2147a4ab7c1c5c85b8032c'),('guosen','374beac2-a970-4972-b210-e91018bbd6e6','585db15e768043b7b465d1af7c690e90')]:
        response=s.financial_workpaper(project,kind='report_audit',document_id=doc)
        assert response['status']=='ok',response
        tables=response['data']['report']['tables']
        rows=[r for name,t in tables.items() if name!='observations' for r in t['rows']]
        selected=[r for r in rows if r['check'].startswith(('DCF标题','目标价=EPS','目标价区间','币种标注'))]
        if name=='cmbi':
            assert any(r['check']=='DCF标题预测年份' for r in selected)
            assert any(r.get('recomputed')=='8.8810' and r['status']=='舍入范围内' for r in selected)
        else:
            assert any(r.get('recomputed')=='33.82' for r in selected)
        result['cases'].append({'name':name,'document':doc,'counts':dict(Counter(r['status'] for r in rows)),'requested_findings':selected,
                               'all_checks':rows,'delivery_files':len(response['data']['delivery']['files'])})
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({r['name']:r['counts'] for r in result['cases']},ensure_ascii=False))


if __name__=='__main__':main()

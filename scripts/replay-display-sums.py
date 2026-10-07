"""Trusted calculators plus frozen B2/Carote inputs; no LLM and no held-out reads."""
import copy,csv,io,json,sys,tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.financial_workpapers import statement_analysis
from service.model_comparison import compare_models
from service.analysis_report import compile_report,display_table,render_table,write_csv,ROUNDING_NOTE

folder=ROOT/'docs/evidence/display-sums-20261007';folder.mkdir(parents=True,exist_ok=True)
events=[json.loads(x) for x in (ROOT/'data/evaluation/harness-v2-smoke-20261007/B2-scenarios-audit.jsonl').read_text(encoding='utf8').splitlines()]
models=[e['data']['result']['data'] for e in events if e['type']=='tool_result' and e['data']['name']=='run_financial_model']
comparison=compare_models('dcf_fcf',models[0]['spec'],models[1]['spec'],['wacc','fcf'])
contributions=comparison['report']['tables']['dcf_update_contributions']
assert contributions['rows'][:2]==models[1]['numeric_tables']['dcf_update_contributions']['rows']
evidence={'method':'Frozen B2 saved input replay and K1 Carote fixture, trusted host calculators only; no LLM. Display at 2 and 4 decimals.','cases':[]}
with tempfile.TemporaryDirectory() as root:
    service=FinanceService(root);service.create_project('p','rounding replay')
    facts=json.loads((ROOT/'service/tests/fixtures/workpapers/carote.json').read_text(encoding='utf8'))
    with patch('service.financial_workpapers.load_facts',return_value=facts):raw,records=statement_analysis(service,'p')
    bridge=compile_report(raw,records)['tables']['bridge']
    for name,source,column in [('b2_contributions',contributions,'contribution'),('k1_carote_cash_bridge',bridge,'amount')]:
        original=copy.deepcopy(source['rows'])
        for decimals in (2,4):
            table=copy.deepcopy(source);table['columns'][column]['decimals']=decimals;view=display_table(table);keys=table['row_keys'];checks=[]
            for relation in table['sum_relations']:
                value=lambda ref:Decimal(view['rows'][keys.index(ref['row'])][ref['column']])
                parts=[value(ref) for ref in relation['parts']];total=value(relation['total'])
                checks.append({'parts':[str(x) for x in parts],'sum':str(sum(parts)),'total':str(total),'equal':sum(parts)==total})
            assert all(check['equal'] for check in checks);assert table['rows']==original
            assert ROUNDING_NOTE in view['notes']
            stem=name+'_'+str(decimals)+'dp';write_csv(folder/(stem+'.csv'),table)
            with (folder/(stem+'.csv')).open(encoding='utf-8-sig') as handle:csv_rows=list(csv.DictReader(handle))
            position=list(table['columns']).index(column)
            assert [list(row.values())[position] for row in csv_rows]==[str(row[column]) for row in original]
            (folder/(stem+'.md')).write_text(render_table(table),encoding='utf8',newline='\n')
            evidence['cases'].append({'name':stem,'exact_rows_unchanged':True,'csv_exact_values_unchanged':True,'checks':checks,'display_note':view['notes'],'files':[stem+'.md',stem+'.csv']})
(folder/'replay.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
print(json.dumps(evidence,ensure_ascii=False,indent=2))

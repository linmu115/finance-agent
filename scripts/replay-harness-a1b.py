"""Replay every original failed report/edit payload in isolated Docker, without LLM calls."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sandbox import create_runner
from service.analysis_edits import apply_edits, AnalysisEditError
from service.analysis_report import convert, cell_column
from decimal import Decimal

out=ROOT/'docs/evidence/harness-v2-20261007/a1b-replay.json'
trial=ROOT/'data/evaluation/harness-v2-a1b-20261007';trial.mkdir(exist_ok=True)
calls=json.loads((ROOT/'tmp/harness-v2-20261007/failed-interface-calls.json').read_text(encoding='utf8'))
runner=create_runner(trial/'runs'); results=[]
selected = {int(x) for x in sys.argv[1:]} if len(sys.argv)>1 else None
if selected: results=json.loads(out.read_text(encoding='utf8'))['cases']

def cause(error):
    if 'edit_' in error:return 'edit_match'
    if 'Container cleanup' in error:return 'container_cleanup'
    if 'SyntaxError' in error or 'unpack' in error or 'unsupported format character' in error:return 'participant_python'
    if 'KeyError' in error:return 'report_or_reference_key'
    if '需要 currency' in error:return 'missing_currency'
    if '不同币种' in error or '不能把' in error or '或比率' in error or '见项目单位' in error or '每股除外' in error or '数值引用' in error:return 'heterogeneous_metric_units'
    if '未知单位' in error:return 'unit_spelling'
    return 'other'

for n,call in enumerate(calls):
    if selected and n+1 not in selected:continue
    audit=ROOT/'data/evaluation'/call['study']/(call['label']+'-audit.jsonl')
    args=json.loads(audit.read_text(encoding='utf8').splitlines()[call['auditLine']-1])['data']['args']
    original=call.get('error') or call.get('stderr') or call.get('analysisError') or ''
    row={'study':call['study'],'label':call['label'],'audit_line':call['auditLine'],'original_run_id':call['analysisId'],
         'original_payload':args,'original_error':original,'root_cause':cause(original)}
    frozen=ROOT/'data/active/analysis'/(call['analysisId'] or args['source_run_id'])/'input'
    code=args.get('code')
    if code is None:
        source=ROOT/'data/active/analysis'/args['source_run_id']/'input/analysis.py' if args.get('source_run_id') else frozen/'analysis.py'
        code=source.read_text(encoding='utf8')
    try:
        code=apply_edits(code,args.get('edits'))
    except AnalysisEditError as exc:
        row.update(status='rejected',error=str(exc),details=exc.details)
    else:
        folder=trial/str(n);folder.mkdir(exist_ok=True)
        (folder/'analysis.py').write_text(code,encoding='utf8')
        inputs={p.name:p for p in frozen.iterdir() if p.name!='__analysis__.py' and p.is_file()}
        inputs['analysis.py']=folder/'analysis.py'
        for name in ('analysis_report.py','model_units.py'):inputs[name]=ROOT/'service'/name
        if args.get('report') is not None:
            (folder/'analysis_report.json').write_text(json.dumps(args['report'],ensure_ascii=False),encoding='utf8');inputs['analysis_report.json']=folder/'analysis_report.json'
        result=runner.run((frozen/'__analysis__.py').read_text(encoding='utf8'),inputs,project_id='harness-a1b',timeout_seconds=120)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        row.update(status=result['status'],replay_run_id=result['run_id'],error=result.get('error'),stderr=result.get('stderr'),container_removed=result.get('container_removed'))
        if result['status']=='succeeded':
            artifact=next((a for a in result['artifacts'] if a['name']=='numeric_tables.json'),None)
            validated=0
            if artifact:
                tables=json.loads(runner.artifact_path(result['run_id'],'numeric_tables.json',project_id='harness-a1b').read_text(encoding='utf8'))['tables']
                for table in tables.values():
                    for i, values in enumerate(table['rows']):
                        for key,q in table.get('evidence',[{}]*len(table['rows']))[i].items():
                            expected=convert(q['value'],q['unit'],cell_column(table,i,key)['unit'])
                            assert expected==values[key],(call['label'],i,key,expected,values[key]);validated+=1
            row['converted_cells_verified']=validated
            row['correctness_boundary']='All resolved numeric cells match their original declared quantity and unit conversion. This does not validate financial claims or fix false units/numbers already embedded in the original payload.'
        if call['label']=='C1' and call['study'].startswith('pi-cowork'):
            row['known_payload_defect']='metrics.change_2025_vs_2024 labels absolute revenue/profit changes as %. Preserved, not claimed financially correct.'
        if call['label']=='E2' and '见项目单位' in original:
            row['known_payload_defect']='Original dcf_summary uses 5.3292246775 人民币亿元 for EV; should be 53.2922467751 亿元 given 5329.22467751 百万元. Interface acceptance preserves this pre-existing wrong scaling.'
        if call['label']=='B1' and call['study'].startswith('pi-cowork'):
            row['known_payload_defect']='Original prose says 扣除银行存款利息收款; numerical bridge adds interest. Semantic error is not solved by accepting mixed units.'
    if selected:results[n]=row
    else:results.append(row)
    payload={'scope':'32 original failed calls, including 5 edit-matching rejections; no modified participant code except the original requested edits. Frozen project inputs; current report interface; Docker isolation; no LLM.',
             'counts':{s:sum(r['status']==s for r in results) for s in sorted({r['status'] for r in results})},'completed':len(results),'total':len(calls),'cases':results}
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'done':n+1,'label':call['label'],'cause':row['root_cause'],'status':row['status'],'error':(row.get('stderr') or row.get('error') or '').splitlines()[-1:]},ensure_ascii=False),flush=True)

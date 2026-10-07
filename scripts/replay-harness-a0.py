"""Read frozen outputs only: exact numbers returned, without running participant code."""
import json
from pathlib import Path
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.analysis_tables import collect_tables, table_view
diagnosis=json.loads((ROOT/'docs/evidence/seam-diagnosis-20261007.json').read_text(encoding='utf8'))
seen=set();runs=[];failed_calls=[]
for task in diagnosis['question2']['perTask']:
    for call in task['toolSequence']:
        if call['name']!='run_analysis':continue
        if call.get('error') or call.get('analysisStatus') not in (None,'succeeded'):
            if any(call['features'].get(x) for x in ('report_parameter','report_file_protocol','body_placeholders','source_run_id_edits')):
                failed_calls.append({'study':task['study'],'label':task['label'],**call})
        run=call.get('analysisId')
        if not run or run in seen:continue
        seen.add(run)
        directory=ROOT/'data/active/analysis'/run
        if not (directory/'state.json').exists():
            runs.append({'run_id':run,'available':False});continue
        state=json.loads((directory/'state.json').read_text(encoding='utf8'))
        paths={item['name']:directory/'output'/item['name'] for item in state.get('artifacts',[]) if Path(item['name']).suffix in ('.csv','.json')}
        tables,warnings=collect_tables(paths)
        view={k:table_view(t) for k,t in tables.items()}
        runs.append({'study':task['study'],'label':task['label'],'run_id':run,'status':state['status'],
                     'table_count':len(tables),'return_chars':len(json.dumps(view,ensure_ascii=False,separators=(',',':'))),
                     'warnings':warnings})
        if run in ('9d76f07716584ccabce39cb4909ed810','5cb01aa8858044a2b4cee37d4087291d'):
            out=ROOT/'docs/evidence/harness-v2-20261007'/('a0-'+task['label']+'-returned-tables.json')
            out.write_text(json.dumps(view,ensure_ascii=False,indent=2),encoding='utf8')
            text=json.dumps(view,ensure_ascii=False)
            for value in (('33.65','-7.73') if task['label']=='C1' else ('11.23',)):
                assert value in text,(task['label'],value)
sizes=sorted(r['return_chars'] for r in runs if r.get('table_count'))
result={'scope':'All run_analysis calls in the 29 frozen task records; failed calls without outputs return zero tables.',
        'calls':sum(c['name']=='run_analysis' for t in diagnosis['question2']['perTask'] for c in t['toolSequence']),
        'unique_runs':len(runs),'runs_with_numeric_tables':len(sizes),'runs':runs,
        'nonempty_return_chars':{'min':min(sizes),'median':statistics.median(sizes),'p90':sizes[int((len(sizes)-1)*.9)],'max':max(sizes)},
        'model_budget_chars':24000,'budget_note':'24k is a row-content budget, not a hard truncation of the task. Every table remains listed with explicit remaining-row counts and artifact continuation. Column inventories can exceed it.',
        'token_estimate_note':'Character count is measured; tokenizer counts are not. Rough 2–4 characters/token estimate only; Chinese headers vary. Tool output adds input tokens in later model turns and can be cached.',
        'key_values_verified':['C1 33.65% and -7.73 at gross-margin 2025H1 row','E2 11.23 HKD/share at growth 0.01 / WACC 11.2%'],
        'limitation':'Historical C1 mixed-unit CSV labels delta as the same % unit. A0 returns that source labelling with an explicit ambiguity note, and does not silently relabel it as pp. A1b/A1 typed tables distinguish the dimensions.'}
out=ROOT/'docs/evidence/harness-v2-20261007'
(out/'a0-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'tmp/harness-v2-20261007/failed-interface-calls.json').write_text(json.dumps(failed_calls,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ('runs',)},ensure_ascii=False,indent=2))

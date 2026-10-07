"""Bind frozen result tables to chat/report output, without participant-code execution."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.analysis_tables import collect_tables
from service.analysis_report import bind_text, compile_report, render_table
out=ROOT/'docs/evidence/harness-v2-20261007';checks=[]
for label,run in [('E2','5cb01aa8858044a2b4cee37d4087291d'),('C2','3975b7c387d34bdea3eb3ff48cd165f6')]:
    root=ROOT/'data/active/analysis'/run/'output'
    tables,warnings=collect_tables({p.name:p for p in root.iterdir() if p.suffix in ('.csv','.json')})
    if label=='E2':
        body='低 WACC / 低 g：{{DCF敏感性.0.01.WACC 11.2%（港元/股）}}\n\n{{table:DCF敏感性}}'
        rendered=bind_text(body,tables)
        assert rendered.startswith('低 WACC / 低 g：11.23 HKD 元/股')
        assert '| 0.01 | 11.23 | 10.22 | 9.39 |' in rendered
        checks.append({'case':label,'run_id':run,'wrong_cell_prevented':True,'grid_cells':9,'exact_cell':tables['DCF敏感性']['rows'][0]['WACC 11.2%（港元/股）']})
    else:
        # The original CSV has no metric name. Preserve that limitation; do not silently
        # pretend that positional rows are reliable revenue/profit labels.
        rendered=bind_text('{{table:forecast_and_valuation_inputs}}\n\n{{table:dcf_sensitivity}}',tables)
        assert '2,402.00' in rendered and '人民币百万元' in rendered
        forecast=json.loads((root/'chart_data.json').read_text(encoding='utf8'))['forecast']
        report=compile_report({'tables':{'forecast':{'columns':{'year':{},'revenue':{'unit':'人民币亿元'},'profit':{'unit':'人民币亿元'},'eps':{'unit':'人民币/股'}},'rows':[
            {'year':str(r['year'])+'E','revenue':{'value':r['revenue_RMB_mn'],'unit':'人民币百万元'},'profit':{'value':r['net_profit_RMB_mn'],'unit':'人民币百万元'},'eps':{'value':r['EPS_RMB'],'unit':'人民币/股'}} for r in forecast]}}})
        converted=bind_text('{{table:forecast}}',report['tables']);assert '| 2024E | 24.02 | 3.48 | 0.63 |' in converted
        rendered+='\n\n来源字段明确为 RMB_mn 的 forecast 转为亿元：\n\n'+converted
        checks.append({'case':label,'run_id':run,'csv_exact_scale_preserved':True,'typed_conversion_from_explicit_json_field_units':True,'json_global_wrong_unit_ignored_in_favour_of_explicit_per_field_RMB_mn':True,'csv_missing_metric_name_unresolved':True,'limitation':'This is explicit deterministic field mapping for the replay, not an automatic recovery of bad/missing source metadata. Bound output does not fix incorrect source numbers or the already-generated old report/charts.'})
    (out/('a1-'+label+'-bound.md')).write_text(rendered,encoding='utf8')
(out/'a1-replay.json').write_text(json.dumps({'checks':checks,'programmatic_binding_guarantee':'Rendered values equal the registered table and use report.md formatter. Wrong source values/units, hand-written numbers and existing historical files remain outside this guarantee.'},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(checks,ensure_ascii=False))

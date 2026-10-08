"""Readable A1 handoff, using the very same units/rounding as the final answer.

Summary tables carry key values; detail tables remain fully available through
their table binding and the published files. No company-specific selection.
"""
from .analysis_report import cell_column, display_table, format_cell, row_keys

# Detail/evidence tables are accessed as whole tables, not duplicated cell by cell.
DETAIL_TABLES={'cash','bridge','working_capital','nonrecurring_items','indirect_bridge',
               'quarterly_reconciliation','reconciliation','drivers_evidence',
               'report_columns','contribution_sources','inventory_charge_rates'}
CONTEXT=('period','metric_label','metric','item','signal','driver','axis','view','mode',
         'comparison','institution','publisher','published_at','role')


def answer_handoff(report):
    lines=[];bindings={}
    for name,t in report['tables'].items():
        bindings[name]='{{table:'+name+'}}'
        if name in DETAIL_TABLES:continue
        display=display_table(t);keys=row_keys(t)
        for i,row in enumerate(display['rows']):
            context=' / '.join(dict.fromkeys(str(row[k]) for k in CONTEXT if row.get(k) not in (None,''))) or keys[i]
            cells=[];missing=[]
            for key in t['columns']:
                c=cell_column(t,i,key)
                if not c.get('unit'):continue
                # Intermediate running totals are not extra profit contributions.
                if name=='profit_bridge' and key=='running':continue
                value=row.get(key);token='{{'+name+'.'+keys[i]+'.'+key+'}}'
                evidence=t.get('evidence',[{} for _ in t['rows']])[i].get(key,{})
                reason=evidence.get('reason') or evidence.get('source',{}).get('missing_reason')
                cells.append(f'{c.get("label",key)}={format_cell(value,c,with_unit=True)} `{token}`')
                if value is None and reason:missing.append(reason)
            if not cells:continue
            notes=[str(row[k]) for k in ('baseline','threshold','threshold_source','triggered','status','missing','basis','note') if row.get(k) not in (None,'')]
            notes+=missing
            lines.append(name+' / '+context+'：'+'；'.join(cells)+('；'+'；'.join(dict.fromkeys(notes)) if notes else ''))
    periods=report.get('periods',[])
    return {'periods':periods,'period_roles':{'current':periods[0] if periods else None,'comparison':periods[1] if len(periods)>1 else None},
            'key_values':lines,'table_bindings':bindings,
            'answer_usage':'关键值后的表达式可直接粘贴，已带单位；整表使用 table_bindings。缺失为未知。明细、原文与来源在交付文件中，get_artifact 的 run_id 可直接填 delivery.id。'}

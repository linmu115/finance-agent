"""Stable version names for scenarios; repairs continue to replace plain names."""
from copy import deepcopy
import re
if __package__:
    from .analysis_comparison import differences
    from .analysis_report import render_table
else:
    from analysis_comparison import differences
    from analysis_report import render_table

PREFERRED='基准_情景_差额'

def scenario_tables(baseline,scenario,baseline_id,scenario_id,summary_table=None):
    left={summary_table:baseline[summary_table]} if summary_table else baseline
    right={summary_table:scenario[summary_table]} if summary_table else scenario
    comparison,skipped=differences(left,right)
    comparison['evidence']=[]
    for row in comparison['rows']:
        sources={}
        for side,data,version in [('old',left,baseline_id),('new',right,scenario_id)]:
            table=data[row['table']];index=table['row_keys'].index(row['row'])
            sources[side]={'version_id':version,'source':table.get('evidence',[{}]*len(table['rows']))[index].get(row['column'],{})}
        comparison['evidence'].append({**sources,'delta':{'source':sources}})
    comparison['columns']['old']['label']='基准'
    comparison['columns']['new']['label']='情景'
    comparison['columns']['delta']['label']='差额（情景减基准）'
    comparison['label']='基准 / 情景 / 差额'
    if summary_table:
        comparison['row_keys']=[r['row'] for r in comparison['rows']]
        comparison['columns'].pop('table');comparison['columns'].pop('column')
        comparison['columns']['row']['label']='指标'
        for row in comparison['rows']:row.pop('table');row.pop('column')
    tables={PREFERRED:comparison};context={'operation':'scenario_update','preferred_table':PREFERRED,'preferred_embedding':'{{table:'+PREFERRED+'}}','unqualified_names':list(dict.fromkeys([*baseline,*scenario])),
        'meaning':'基准是本次 source 指定的原版本；情景是修改参数后的新版本。比较优先嵌入基准_情景_差额，单值使用下列带版本表名。','skipped':skipped}
    for role,label,version,data in [('baseline','基准',baseline_id,baseline),('scenario','情景',scenario_id,scenario)]:
        names={}
        for name,table in data.items():
            qualified=label+'_'+re.sub(r'[^\w-]','_',version)+'__'+name
            tables[qualified]={**deepcopy(table),'label':label+' · '+name,'scenario_role':role,'version_id':version,'original_table':name}
            names[name]=qualified
        context[role]={'label':label,'version_id':version,'tables':names}
    return tables,context

def scenario_report(tables,context):
    return {'title':'基准 / 情景 / 差额','tables':tables,'body':context['meaning']+'\n\n基准版本：'+context['baseline']['version_id']+'\n\n情景版本：'+context['scenario']['version_id']+'\n\n'+render_table(tables[PREFERRED])}

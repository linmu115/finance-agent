"""Exact model differences and optional ordered DCF substitution, with no LLM."""
from copy import deepcopy
from decimal import Decimal, localcontext
from .model_inputs import set_input, get_input
from .research_models import evaluate_model, ValidationError

METADATA={'source_refs','input_basis','input_transformations'}


def leaves(value, path=''):
    if isinstance(value,dict):
        for key,item in value.items():
            if key not in METADATA:yield from leaves(item,f'{path}.{key}' if path else key)
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from leaves(item,f'{path}.{i}')
    else:yield path,value


def compare_models(kind, baseline, scenario, order=None):
    with localcontext() as ctx:
        ctx.prec=50
        return _compare_models(kind,baseline,scenario,order)


def _compare_models(kind, baseline, scenario, order):
    before=dict(leaves(baseline));after=dict(leaves(scenario))
    changed=[{'path':key,'before':before.get(key),'after':after.get(key)}
             for key in sorted(before.keys()|after.keys()) if before.get(key)!=after.get(key)]
    left=evaluate_model(kind,baseline);right=evaluate_model(kind,scenario)
    deltas={}
    for key,value in left['results'].items():
        other=right['results'].get(key)
        if isinstance(value,(str,int,float)) and not isinstance(value,bool) and isinstance(other,(str,int,float)):
            try:deltas[key]={'before':str(value),'after':str(other),'change':str(Decimal(str(other))-Decimal(str(value)))}
            except ArithmeticError:continue
    result={'kind':kind,'changed_inputs':changed,'result_changes':deltas,'decomposition':None,
            'interpretation':'差异来自所列全部参数；模型差异或接近目标值本身不证明经济因果。'}
    # Different currencies/scales or time anchors are not like-for-like values.
    incompatible=[key for key in ('currency','price_currency','amount_scale','base_year','valuation_date') if baseline.get(key)!=scenario.get(key)]
    if incompatible:
        result['result_changes']={};result['comparison_unavailable']='不可直接比较：'+', '.join(incompatible)
        return result
    if kind=='dcf':
        left_rows={r['year']:r for r in left['tables']['forecast']}
        changes=[]
        for row in right['tables']['forecast']:
            prior=left_rows.get(row['year'])
            if prior is None:continue
            amounts={key:Decimal(row[key])-Decimal(prior[key]) for key in ('nopat','da','capex','delta_nwc','fcff')}
            changes.append({'year':row['year'],**{key+'_change':str(value) for key,value in amounts.items()},
                'fcff_bridge_residual':str(amounts['fcff']-amounts['nopat']-amounts['da']+amounts['capex']+amounts['delta_nwc'])})
        result['forecast_changes']=changes
    if kind=='dcf_fcf' and order is None:
        order=list(dict.fromkeys(change['path'].split('.')[0] for change in changed))
    if order is not None:
        if kind not in {'dcf','dcf_fcf'}:raise ValueError('ordered_decomposition_requires_dcf')
        paths=[c['path'] for c in changed]
        covered=[p for group in order for p in paths if p==group or kind=='dcf_fcf' and p.startswith(group+'.')]
        if len(order)!=len(set(order)) or len(covered)!=len(set(covered)) or set(covered)!=set(paths):raise ValueError('decomposition_order_must_cover_changed_inputs_once: '+', '.join(paths))
        metric='value_per_share' if left['results'].get('value_per_share') is not None and right['results'].get('value_per_share') is not None else 'enterprise_value'
        current=deepcopy(baseline);previous=Decimal(left['results'][metric]);steps=[]
        for path in order:
            try:old_value=get_input(baseline,path);new_value=get_input(scenario,path)
            except ValueError:
                result['decomposition']={'steps':steps,'complete':False,'reason':'结构变化不能逐字段替换；仍保留两份完整模型结果。'}
                break
            set_input(current,path,new_value)
            try:value=Decimal(evaluate_model(kind,current)['results'][metric])
            except ValidationError as exc:
                result['decomposition']={'steps':steps,'complete':False,'reason':str(exc),'failed_path':path}
                break
            steps.append({'path':path,'before':old_value,'after':new_value,'metric':metric,**({'per_share_before':str(previous),'per_share_after':str(value)} if metric=='value_per_share' else {'value_before':str(previous),'value_after':str(value)}),'contribution':str(value-previous)})
            previous=value
        else:
            result['decomposition']={'steps':steps,'complete':True,'order':order,
                'metric':metric,'total_change':str(Decimal(right['results'][metric])-Decimal(left['results'][metric])),
                'interpretation':'按指定顺序逐项替换；交互影响分配给后替换的参数，改变顺序可能改变各项贡献。'}
    if kind=='dcf_fcf':
        from .analysis_comparison import differences
        from .analysis_report import compile_report,render_table
        changes,skipped=differences(left['report']['tables'],right['report']['tables'])
        changes['evidence']=[]
        for row in changes['rows']:
            sources={}
            for side,model in [('old',left),('new',right)]:
                table=model['report']['tables'][row['table']];index=table['row_keys'].index(row['row'])
                sources[side]=table.get('evidence',[{}]*len(table['rows']))[index].get(row['column'],{})
            changes['evidence'].append({**sources,'delta':{'source':sources}})
        tables={'dcf_update_changes':changes};decomposition=result.get('decomposition')
        if decomposition and decomposition.get('steps'):
            from .model_units import AMOUNT_UNITS
            unit={'unit':'元/股','currency':scenario.get('price_currency',scenario['currency'])} if decomposition.get('metric')=='value_per_share' else {'unit':AMOUNT_UNITS.get(str(scenario['amount_scale']),'元'),'currency':scenario['currency']}
            multiplier=Decimal(scenario['amount_scale']) if decomposition.get('metric')!='value_per_share' and str(scenario['amount_scale']) not in AMOUNT_UNITS else Decimal(1)
            report=compile_report({'tables':{'dcf_update_contributions':{'columns':{'parameter':{},'contribution':{**unit,'decimals':4}},'row_key':'parameter',
                'rows':[{'parameter':step['path'],'contribution':{'value':str(Decimal(step['contribution'])*multiplier),**unit,'source':{'baseline':baseline.get('source_refs',{}),'scenario':scenario.get('source_refs',{}),'order':order}}} for step in decomposition['steps']]}}})
            tables.update(report['tables'])
        result['report']={'title':'DCF 参数更新','tables':tables,'body':'贡献依赖替换顺序。\n\n'+'\n\n'.join(render_table(t) for t in tables.values()),'skipped':skipped}
    return result

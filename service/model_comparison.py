"""Exact model differences and optional ordered DCF substitution, with no LLM."""
from copy import deepcopy
from decimal import Decimal, localcontext
from .model_inputs import set_input
from .research_models import evaluate_model, ValidationError

METADATA={'source_refs','input_basis'}


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
    incompatible=[key for key in ('currency','amount_scale','base_year') if baseline.get(key)!=scenario.get(key)]
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
    if order is not None:
        if kind!='dcf':raise ValueError('ordered_decomposition_requires_dcf')
        paths=[c['path'] for c in changed]
        if len(order)!=len(set(order)) or set(order)!=set(paths):raise ValueError('decomposition_order_must_cover_changed_inputs_once')
        current=deepcopy(baseline);previous=Decimal(left['results']['value_per_share']);steps=[]
        for path in order:
            if path not in before or path not in after:
                result['decomposition']={'steps':steps,'complete':False,'reason':'结构变化不能逐字段替换；仍保留两份完整模型结果。'}
                break
            set_input(current,path,after[path])
            try:value=Decimal(evaluate_model(kind,current)['results']['value_per_share'])
            except ValidationError as exc:
                result['decomposition']={'steps':steps,'complete':False,'reason':str(exc),'failed_path':path}
                break
            steps.append({'path':path,'before':before[path],'after':after[path],'per_share_before':str(previous),'per_share_after':str(value),'contribution':str(value-previous)})
            previous=value
        else:
            result['decomposition']={'steps':steps,'complete':True,'order':order,
                'total_change':str(Decimal(right['results']['value_per_share'])-Decimal(left['results']['value_per_share'])),
                'interpretation':'按指定顺序逐项替换；交互影响分配给后替换的参数，改变顺序可能改变各项贡献。'}
    return result

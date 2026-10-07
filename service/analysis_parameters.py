"""Static numeric parameters and exact operators. Participant code is never evaluated."""
import ast
from decimal import Decimal, InvalidOperation, localcontext


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('参数须为有限数值、数字列表或数字字典')
    try: result=Decimal(str(value))
    except InvalidOperation: raise ValueError(f'参数 {value!r} 不是数字') from None
    if not result.is_finite():raise ValueError('参数须为有限数值')
    return result


def numeric_value(value):
    if isinstance(value,list):return [numeric_value(v) for v in value]
    if isinstance(value,dict):return {k:numeric_value(v) for k,v in value.items()}
    return number(value)


def apply_operator(value, override):
    """A2 params and B2 overrides use the same elementwise +/* semantics."""
    if isinstance(override,dict) and set(override) in ({'+'},{'*'}):
        op=next(iter(override));operand=number(override[op])
        def each(v):
            if isinstance(v,list):return [each(x) for x in v]
            if isinstance(v,dict):return {k:each(x) for k,x in v.items()}
            with localcontext() as context:
                context.prec=50
                return number(v)+operand if op=='+' else number(v)*operand
        return each(value)
    return numeric_value(override)


def serializable(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,list):return [serializable(v) for v in value]
    if isinstance(value,dict):return {k:serializable(v) for k,v in value.items()}
    return value


def _constant(node, decimal_names):
    if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)) and not isinstance(node.value,bool):return number(node.value),None
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
        v,kind=_constant(node.operand,decimal_names)
        if isinstance(v,Decimal):return (-v if isinstance(node.op,ast.USub) else v),kind
    if isinstance(node,ast.List) and node.elts:
        items=[_constant(v,decimal_names) for v in node.elts]
        return [x[0] for x in items],next((x[1] for x in items if x[1]),None)
    if isinstance(node,ast.Dict) and node.keys:
        keys=[ast.literal_eval(k) for k in node.keys]
        if any(not isinstance(k,(int,str)) or isinstance(k,bool) for k in keys):raise ValueError('非数值字典键')
        values=[_constant(v,decimal_names) for v in node.values]
        return dict(zip(keys,[v[0] for v in values])),next((v[1] for v in values if v[1]),None)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in decimal_names and len(node.args)==1 and not node.keywords:
        arg=node.args[0]
        if isinstance(arg,ast.Constant):return number(arg.value),node.func.id
    # Frozen E2 expresses its numeric list as list(map(D, ['288', ...])).
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='list' and len(node.args)==1 and not node.keywords:
        inner=node.args[0]
        if isinstance(inner,ast.Call) and isinstance(inner.func,ast.Name) and inner.func.id=='map' and len(inner.args)==2 and not inner.keywords:
            constructor,items=inner.args
            if isinstance(constructor,ast.Name) and constructor.id in decimal_names and isinstance(items,ast.List) and all(isinstance(x,ast.Constant) for x in items.elts):
                return [number(x.value) for x in items.elts],constructor.id
    raise ValueError('不是静态数字常量')


def parameters(code):
    parsed=ast.parse(code);decimal_names=set();found={}
    for node in parsed.body:
        if isinstance(node,ast.ImportFrom) and node.module=='decimal':
            decimal_names.update(item.asname or item.name for item in node.names if item.name=='Decimal')
        target=node.targets[0] if isinstance(node,ast.Assign) and len(node.targets)==1 else node.target if isinstance(node,ast.AnnAssign) else None
        if not isinstance(target,ast.Name):continue
        if isinstance(node.value,ast.Name) and node.value.id in decimal_names:
            decimal_names.add(target.id);continue
        decimal_names.discard(target.id)
        # A name assigned more than once is not a single input parameter.
        if target.id in found:found[target.id]=None;continue
        try:value,constructor=_constant(node.value,decimal_names)
        except (ValueError,TypeError):continue
        found[target.id]={'value':value,'constructor':constructor,'node':node.value}
    return {k:v for k,v in found.items() if v is not None}


def parameter_inventory(code):
    return {k:serializable(v['value']) for k,v in parameters(code).items()}


def _literal(value,constructor):
    if isinstance(value,list):return '['+', '.join(_literal(v,constructor) for v in value)+']'
    if isinstance(value,dict):return '{'+', '.join(repr(k)+': '+_literal(v,constructor) for k,v in value.items())+'}'
    return f'{constructor}({str(value)!r})' if constructor else str(value)


def override_parameters(code, overrides, order=None):
    available=parameters(code)
    missing=set(overrides)-set(available)
    if missing:raise ValueError(f'未知参数 {sorted(missing)}；可覆盖参数：{parameter_inventory(code)}')
    if order is not None and (len(order)!=len(set(order)) or set(order)!=set(overrides)):
        raise ValueError(f'params_order 须恰好列出每个修改参数一次：{list(overrides)}')
    lines=code.encode('utf8').splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    replacements=[];changes={}
    for name,override in overrides.items():
        item=available[name];value=apply_operator(item['value'],override);node=item['node']
        replacements.append((offsets[node.lineno-1]+node.col_offset,offsets[node.end_lineno-1]+node.end_col_offset,_literal(value,item['constructor']).encode('utf8')))
        changes[name]={'old':serializable(item['value']),'new':serializable(value)}
    data=code.encode('utf8')
    for start,end,replacement in sorted(replacements,reverse=True):data=data[:start]+replacement+data[end:]
    return data.decode('utf8'),changes

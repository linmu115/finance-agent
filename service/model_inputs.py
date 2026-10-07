"""Bind saved project records to calculator inputs without a model retyping values."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import json
import re


def get_input(spec, path):
    value=spec
    try:
        for part in path.split('.'):value=value[int(part)] if isinstance(value,list) else value[part]
    except (KeyError,IndexError,TypeError,ValueError):raise ValueError('model_input_path_not_found: '+path) from None
    return value


def apply_overrides(spec, overrides):
    from .analysis_parameters import apply_operator, serializable
    output=deepcopy(spec);values={}
    for path,value in overrides.items():
        value=serializable(apply_operator(get_input(output,path),value)) if isinstance(value,dict) and set(value) in ({'+'},{'*'}) else deepcopy(value)
        set_input(output,path,value);values[path]=value
    return {'spec':output,'values':values}


def set_input(spec, path, value):
    if not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*', path):
        raise ValueError('invalid_model_input_path')
    parts=path.split('.');target=spec
    try:
        for part in parts[:-1]:
            target=target[int(part)] if isinstance(target,list) else target[part]
        if isinstance(target,list):target[int(parts[-1])]=value
        else:target[parts[-1]]=value
    except (KeyError,IndexError,TypeError,ValueError):
        raise ValueError('model_input_path_not_found: '+path) from None


def read_record(db, project_id, reference):
    fact_id, record_id = reference.get('fact_id'), reference.get('record_id')
    if bool(fact_id) == bool(record_id):raise ValueError('binding_requires_fact_id_or_record_id')
    table, key = ('facts', 'fact_id') if fact_id else ('research_records', 'record_id')
    row = db.execute(f'SELECT * FROM {table} WHERE project_id=? AND {key}=?', (project_id, fact_id or record_id)).fetchone()
    if row is None:raise ValueError('model_record_not_in_project')
    return dict(row)


def resolve_inputs(service, project_id, spec, bindings, kind=None):
    service.store.project(project_id)
    spec=deepcopy(spec);resolved=[]
    with service.store.connect() as db:
        for path,binding in bindings.items():
            fact_id=binding.get('fact_id');record_id=binding.get('record_id')
            row=read_record(db,project_id,binding);source=json.loads(row['source_json'])
            metadata=source.get('normalization',{}) if fact_id else json.loads(row['record_json'])
            currency=row['currency']
            # Price and FX records retain their explicitly declared currencies.
            price_currency=spec.get('price_currency',spec.get('currency'))
            rate_currency=str(price_currency)+'/'+str(spec.get('currency'))
            expected_price=path in {'target_price'} or path.startswith('target_assumptions.target_price')
            expected_fx=path=='fx' or path=='target_assumptions.fx'
            if expected_price and currency!=str(price_currency)+'/share':raise ValueError('target_price record currency must equal price_currency/share')
            if expected_fx and currency not in {rate_currency,'multiple','倍','ratio'}:raise ValueError('fx record must be '+rate_currency+' or an explicitly directed ratio (price currency per source currency)')
            if kind=='dcf_fcf':
                parts=path.removeprefix('target_assumptions.').split('.');field=parts[0]
                expected={spec.get('currency')} if field in {'fcf','net_cash','net_debt','non_controlling_interest','terminal_ebitda','terminal_net_income','terminal_net_cash','terminal_non_controlling_interest'} else {'percent','ratio'} if field in {'wacc','g'} else {'shares','股'} if field=='shares' else {str(spec.get('currency'))+'/share'} if field=='eps' else None
                if expected and currency not in expected:raise ValueError(f'{path}: record currency/unit {currency} incompatible; expected {sorted(expected)}')
            if 'scale' in binding:divisor=binding['scale']
            elif currency==spec.get('currency'):divisor=spec['amount_scale']
            elif currency in {'shares','股'}:
                owner=spec
                for part in path.split('.')[:-1]:owner=owner[int(part)] if isinstance(owner,list) else owner[part]
                divisor=owner['scale']
            elif currency in {'percent','percentage_points'}:divisor='100'
            elif currency in {str(spec.get('currency'))+'/share',str(price_currency)+'/share',rate_currency,'ratio','multiple','count','倍'}:divisor='1'
            else:raise ValueError('binding_unit_unknown: '+path+'; provide a compatible currency and explicit scale')
            try:
                scale=Decimal(str(divisor));value=Decimal(str(row['value']))
            except (KeyError,TypeError,InvalidOperation):raise ValueError('binding_requires_numeric_record_and_scale') from None
            if not scale.is_finite() or scale<=0 or not value.is_finite():raise ValueError('invalid_binding_scale_or_value')
            if row['currency'] not in {spec.get('currency'),str(spec.get('currency'))+'/share',str(price_currency)+'/share',rate_currency,'ratio','percent','percentage_points','shares','multiple','count','倍','股'}:
                raise ValueError('binding_currency_mismatch')
            with localcontext() as ctx:
                ctx.prec=50
                number=str(value/scale)
            set_input(spec,path,number)
            ref={'kind':'document','id':row['document_id'],'locator':'page:'+str(source['page']),
                 'record_id':fact_id or record_id,'period':row.get('period'),'currency':currency,
                 **{k:source[k] for k in ('table_id','row','column','cell','start','end','offset_unit') if k in source}}
            span=source.get('normalization',{}).get('numeric_span')
            if span:ref['numeric_span']=span
            spec.setdefault('source_refs',{})[path]=[ref]
            data_kind='disclosed_actual' if fact_id else row['data_kind']
            source_kind={'quoted_actual':'disclosed_actual','company_guidance':'management_guidance'}.get(data_kind,data_kind)
            if source_kind not in {'disclosed_actual','analyst_forecast','management_guidance','assumption'}:source_kind='unknown'
            spec.setdefault('input_basis',{})[path]={
                'basis':'assumption' if data_kind=='assumption' else 'disclosed',
                'source_kind':source_kind,'rationale':f"记录 {fact_id or record_id}，规范值 {row['value']} / 输入单位倍率 {scale}。"}
            resolved.append({'path':path,'record_id':fact_id or record_id,'record_type':'fact' if fact_id else 'research',
                'value':number,'source_value':row['value'],'scale':str(scale),'period':row.get('period'),
                'scope':row.get('scope'),'currency':row.get('currency'),'quality':row.get('quality',metadata.get('quality')),
                'data_kind':data_kind,'source':source,'document_id':row['document_id']})
    return {'spec':spec,'bindings':resolved}

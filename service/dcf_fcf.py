"""Given-FCF valuation, exact diagnostics and typed, source-preserving delivery."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from .research_models import _calculation, _num, _decimal, _json, ValidationError, PRECISION, VERSION
from .analysis_report import compile_report
from .model_units import AMOUNT_UNITS


def _calculate(spec, wacc=None, growth=None):
    w=_num(spec,'wacc',positive=True) if wacc is None else wacc
    g=_num(spec,'g') if growth is None else growth
    if g<=-1 or w<=g:raise ValidationError('dcf_fcf requires -1 < g < WACC')
    fcf=[_decimal(x,f'fcf.{i}') for i,x in enumerate(spec['fcf'])]
    periods=[_decimal(x,'discount.periods') for x in spec['discount'].get('periods',range(1,len(fcf)+1))]
    if len(periods)!=len(fcf) or any(t<=0 for t in periods) or any(a>=b for a,b in zip(periods,periods[1:])):
        raise ValidationError('discount.periods must match FCF and be positive, increasing year fractions from valuation_date')
    mid=spec['discount']['cashflow_timing']=='mid_year'
    exponents=[t-Decimal('.5') if mid else t for t in periods]
    if min(exponents)<0:raise ValidationError('mid_year cash-flow discount exponent cannot precede valuation_date')
    pv=[v/(1+w)**t for v,t in zip(fcf,exponents)];tv=fcf[-1]*(1+g)/(w-g);pvt=tv/(1+w)**periods[-1];ev=sum(pv)+pvt
    if 'net_cash' in spec and 'net_debt' in spec:raise ValidationError('provide net_cash OR net_debt, not both')
    cash=_num(spec,'net_cash') if 'net_cash' in spec else -_num(spec,'net_debt') if 'net_debt' in spec else None
    nci=_num(spec,'non_controlling_interest',minimum=Decimal(0)) if 'non_controlling_interest' in spec else None
    equity=ev+cash-(nci if nci is not None else 0) if cash is not None else None
    shares=spec.get('shares');count=_num(shares,'count',positive=True)*_num(shares,'scale',positive=True) if shares else None
    fx=_num(spec,'fx',positive=True) if 'fx' in spec else Decimal(1)
    currency=spec['currency'];price_currency=spec.get('price_currency',currency)
    if price_currency!=currency and 'fx' not in spec:raise ValidationError('fx is required: units of price_currency per 1 currency')
    if price_currency==currency and fx!=1:raise ValidationError('same currency requires fx=1; otherwise specify price_currency')
    scale=_num(spec,'amount_scale',positive=True)
    price=equity*scale/count*fx if equity is not None and count else None
    results={'enterprise_value':ev,'equity_value':equity,'value_per_share':price,'explicit_forecast_pv':sum(pv),
        'terminal_value':tv,'terminal_pv':pvt,'terminal_value_share':pvt/ev if ev else None,
        'net_cash':cash,'non_controlling_interest':nci,'shares_outstanding':count,'fx':fx}
    notes=[]
    if cash is None:notes.append('净现金/净债务未提供，股权价值和每股价值未知。')
    if nci is None:notes.append('未提供少数股东调整；所列股权价值未扣此项，不表示少数股东为零。')
    if count is None:notes.append('未提供股本，每股价值未知。')
    if ev<=0:notes.append('企业价值非正；终值比重不宜作常规估值依赖度解释。')
    for denominator,result,numerator in [('terminal_ebitda','ev_ebitda',tv),('terminal_net_income','pe',None)]:
        if denominator in spec:
            earnings=_num(spec,denominator)
            # P/E must use terminal-date equity, not today's net cash mixed with terminal EV.
            terminal_cash=_num(spec,'terminal_net_cash') if 'terminal_net_cash' in spec else None
            terminal_nci=_num(spec,'terminal_non_controlling_interest',minimum=Decimal(0)) if 'terminal_non_controlling_interest' in spec else None
            numerator=tv+terminal_cash-(terminal_nci if terminal_nci is not None else 0) if result=='pe' and terminal_cash is not None else numerator
            results[result]=numerator/earnings if earnings>0 and numerator is not None else None
            if results[result] is None:notes.append(result+' 未计算：需要正的同口径终年盈利；退出 P/E 另需 terminal_net_cash，不能把现时净现金套到终年。')
            elif result=='pe' and terminal_nci is None:notes.append('退出 P/E 未扣未提供的终年少数股东调整。')
    if 'eps' in spec:results['eps']=_num(spec,'eps')
    if 'target_price' in spec:
        target=_num(spec,'target_price');results.update(target_price=target,target_price_gap=price-target if price is not None else None)
    rows=[{'period':str(i+1),'fcf':value,'discount_exponent':exponent,'discount_factor':1/(1+w)**exponent,'pv_fcf':present} for i,(value,exponent,present) in enumerate(zip(fcf,exponents,pv))]
    return results,rows,notes


def _sources(spec,paths):
    refs=spec.get('source_refs',{});basis=spec.get('input_basis',{});origins=[]
    for path in paths:
        matches=[key for key in refs if key==path or key.startswith(path+'.')]
        transforms=spec.get('input_transformations',{})
        origins.extend({'path':key,'references':refs[key],'basis':basis.get(key,{}),'transformations':{p:v for p,v in transforms.items() if key==p or key.startswith(p+'.')}} for key in matches)
        if not matches:origins.append({'path':path,'references':[],'basis':basis.get(path,{'basis':'assumption','rationale':'用户给定的模型输入，未绑定记录。'})})
    return {'inputs':origins}


def result_report(spec,results,forecast,sensitivity,bridge,notes):
    scale=_num(spec,'amount_scale');currency=spec['currency'];pc=spec.get('price_currency',currency)
    money={'unit':AMOUNT_UNITS.get(str(scale),'元'),'currency':currency,'decimals':2};price={'unit':'元/股','currency':pc,'decimals':2}
    money_multiplier=1 if str(scale) in AMOUNT_UNITS else scale
    table={'columns':{'metric':{'label':'指标'},'value':{'label':'数值','decimals':2}},'row_key':'metric','rows':[]}
    rate={'unit':'%','decimals':2};ratio={'unit':'ratio','decimals':4}
    money_keys={'enterprise_value','equity_value','explicit_forecast_pv','terminal_value','terminal_pv','net_cash','non_controlling_interest'}
    price_keys={'value_per_share','target_price','target_price_gap'}
    calc_paths=['fcf','wacc','g','discount'];equity_paths=calc_paths+['net_cash' if 'net_cash' in spec else 'net_debt','non_controlling_interest'];per_share_paths=equity_paths+['shares','fx']
    def cell(value,unit,paths,multiplier=1):return {'value':str(value*multiplier) if value is not None else None,**unit,'source':_sources(spec,paths)}
    for key,value in results.items():
        unit=money if key in money_keys else price if key in price_keys else {'unit':'元/股','currency':currency} if key=='eps' else rate if key=='terminal_value_share' else {'unit':'股'} if key=='shares_outstanding' else {'unit':'倍'} if key in {'pe','ev_ebitda'} else ratio
        paths=per_share_paths if key in price_keys else ['eps'] if key=='eps' else ['shares'] if key=='shares_outstanding' else ['fx'] if key=='fx' else equity_paths if key=='equity_value' else calc_paths
        if key in {'target_price','target_price_gap'}:paths=paths+['target_price']
        if key=='ev_ebitda':paths=calc_paths+['terminal_ebitda']
        if key=='pe':paths=calc_paths+['terminal_net_income','terminal_net_cash','terminal_non_controlling_interest']
        if key in {'net_cash','non_controlling_interest'}:paths=['net_debt' if key=='net_cash' and 'net_debt' in spec else key]
        table['rows'].append({'metric':key,'value':cell(value,unit,paths,money_multiplier if key in money_keys else 100 if key=='terminal_value_share' else 1)})
    ftable={'columns':{'period':{'label':'预测期'},'fcf':{**money,'label':'给定 FCFF'},'discount_exponent':{'label':'折现年数','unit':'年','decimals':2},'discount_factor':ratio,'pv_fcf':{**money,'label':'现值'}},'row_key':'period','rows':[]}
    for i,row in enumerate(forecast):ftable['rows'].append({k:cell(v,money,[f'fcf.{i}','wacc','discount'],money_multiplier) if k in {'fcf','pv_fcf'} else cell(v,ratio,['wacc','discount']) if k=='discount_factor' else cell(v,{'unit':'年'},['discount','valuation_date']) if k=='discount_exponent' else str(v) for k,v in row.items()})
    stable={'columns':{'wacc':rate,'g':rate,'enterprise_value':money,'value_per_share':price,'reason':{}},'row_keys':[str(i) for i in range(len(sensitivity))],'rows':[]}
    for row in sensitivity:stable['rows'].append({'wacc':cell(row['wacc'],rate,['wacc'],100),'g':cell(row['g'],rate,['g'],100),'enterprise_value':cell(row.get('enterprise_value'),money,calc_paths,money_multiplier),'value_per_share':cell(row.get('value_per_share'),price,per_share_paths),'reason':row.get('reason','')})
    tables={'dcf_summary':table,'dcf_forecast':ftable,'dcf_sensitivity':stable}
    if bridge:
        tables['dcf_target_bridge']={'columns':{'parameter':{},'before':price,'after':price,'contribution':price},'row_key':'parameter','rows':[{k:cell(v,price,per_share_paths+['target_assumptions','target_price']) if k!='parameter' else v for k,v in row.items()} for row in bridge]}
        table=tables['dcf_target_bridge'];start=bridge[0]['before'];end=bridge[-1]['after']
        table['rows'].append({'parameter':'合计',**{k:cell(v,price,per_share_paths+['target_assumptions','target_price']) for k,v in {'before':start,'after':end,'contribution':end-start}.items()}})
        table['sum_relations']=[{'parts':[{'row':row['parameter'],'column':'contribution'} for row in bridge],'total':{'row':'合计','column':'contribution'}}]
    body='估值基准日：'+spec['valuation_date']+'；折现约定：'+spec['discount']['cashflow_timing']+'；汇率为每 1 '+currency+' 对应的 '+pc+'。\n\n{{table:dcf_summary}}\n\n{{table:dcf_forecast}}\n\n{{table:dcf_sensitivity}}'
    if bridge:body+='\n\n{{table:dcf_target_bridge}}\n\n贡献按表中顺序替换，依赖替换顺序；remaining_gap 为未解释差额。'
    body+='\n\n'+'\n\n'.join(notes)
    return compile_report({'title':'给定自由现金流 DCF','body':body,'tables':tables})


@_calculation
def value_dcf_fcf(spec):
    if not isinstance(spec.get('fcf'),list) or not spec['fcf']:raise ValidationError('fcf: provide a nonempty numeric sequence (record references are resolved by the host)')
    if not isinstance(spec.get('currency'),str) or not spec['currency']:raise ValidationError('currency is required')
    try:date.fromisoformat(spec['valuation_date'])
    except (KeyError,TypeError,ValueError):raise ValidationError('valuation_date requires YYYY-MM-DD') from None
    if spec.get('discount',{}).get('cashflow_timing') not in {'year_end','mid_year'}:raise ValidationError('discount.cashflow_timing requires year_end or mid_year')
    results,forecast,notes=_calculate(spec);w=_num(spec,'wacc');g=_num(spec,'g');grid=spec.get('sensitivity',{})
    ws=[_decimal(v,'sensitivity.wacc') for v in grid.get('wacc',[w+Decimal('.005')*i for i in range(-2,3)])]
    gs=[_decimal(v,'sensitivity.growth') for v in grid.get('growth',[g+Decimal('.005')*i for i in range(-2,3)])]
    if not ws or not gs:raise ValidationError('sensitivity axes cannot be empty')
    sensitivity=[]
    for growth in gs:
        for discount in ws:
            if discount<=0 or discount<=growth or growth<=-1:
                sensitivity.append({'wacc':discount,'g':growth,'enterprise_value':None,'value_per_share':None,'reason':'需要正 WACC 且 -1 < g < WACC'});continue
            r,_,_=_calculate(spec,discount,growth);sensitivity.append({'wacc':discount,'g':growth,'enterprise_value':r['enterprise_value'],'value_per_share':r['value_per_share']})
    bridge=[]
    if 'target_price' in spec:
        assumptions=spec.get('target_assumptions')
        if assumptions and results['value_per_share'] is not None:
            allowed=['wacc','g','fcf','fx','shares'];unknown=set(assumptions)-set(allowed)
            if unknown:raise ValidationError('target_assumptions unsupported paths: '+', '.join(sorted(unknown)))
            order=spec.get('target_order',[k for k in allowed if k in assumptions])
            if len(order)!=len(set(order)) or set(order)!=set(assumptions):raise ValidationError('target_order must name each target_assumptions field exactly once')
            current=deepcopy(spec);previous=results['value_per_share']
            for path in order:
                current[path]=deepcopy(assumptions[path]);r,_,_=_calculate(current);value=r['value_per_share']
                bridge.append({'parameter':path,'before':previous,'after':value,'contribution':value-previous});previous=value
            target=_num(spec,'target_price');bridge.append({'parameter':'remaining_gap','before':previous,'after':target,'contribution':target-previous})
        else:notes.append('目标价仅给出一个数，未提供可复算的目标假设；WACC/g/FCF/汇率/股本贡献不可识别，只报告价差。')
    notes.append('给定 FCF 保留其披露/机构预测身份；最后一期 FCF 按 g 延伸到永续阶段属于估值假设。')
    report=result_report(spec,results,forecast,sensitivity,bridge,notes)
    return {'schema_version':'1.0','model_version':VERSION,'kind':'dcf_fcf','input_assumptions':spec,
        'precision':{'arithmetic':'Decimal','significant_digits':PRECISION},
        'formulas':{'EV':'sum(FCF[t]/(1+WACC)^exponent[t]) + FCF[-1]*(1+g)/(WACC-g)/(1+WACC)^terminal_period',
            'equity':'EV + net_cash - supplied NCI; omitted NCI remains unassessed','value_per_share':'equity * amount_scale / (shares.count * shares.scale) * fx',
            'exit_multiples':'terminal EV / terminal EBITDA; (terminal EV + terminal net cash - supplied terminal NCI) / terminal ordinary net income'},
        'units':{'currency':spec['currency'],'amount_scale':spec['amount_scale'],'value_per_share':spec.get('price_currency',spec['currency'])+'/share'},
        'results':results,'tables':{'forecast':forecast,'sensitivity':sensitivity,'target_bridge':bridge},'warnings':notes,'report':report,
        'input_usage':[{'path':'g','usage':'perpetual_growth_assumption','source_refs':spec.get('source_refs',{}).get('g',[])},
                       {'path':'fcf.'+str(len(spec['fcf'])-1),'usage':'terminal_extrapolation_assumption','source_refs':spec.get('source_refs',{}).get('fcf.'+str(len(spec['fcf'])-1),[])}]}


def schema(common,decimal,obj,shares,sensitivity):
    return obj({**common,'fcf':{'type':'array','minItems':1,'items':decimal},'valuation_date':{'type':'string','format':'date'},
        'discount':obj({'cashflow_timing':{'enum':['year_end','mid_year']},'periods':{'type':'array','items':decimal,'description':'Positive increasing year fractions from valuation_date to each year end; default 1..N. Midyear subtracts 0.5 only from explicit cash flows, not terminal value.'}},['cashflow_timing']),
        **{k:decimal for k in ('wacc','g','net_cash','net_debt','non_controlling_interest','fx','terminal_ebitda','terminal_net_income','terminal_net_cash','terminal_non_controlling_interest','eps','target_price')},
        'shares':shares,'price_currency':{'type':'string','description':'Per-share and target price currency. fx is price_currency per 1 currency.'},'sensitivity':sensitivity,
        'target_assumptions':{'type':'object','description':'Optional independently sourced target methodology: subset of wacc,g,fcf,fx,shares. A scalar target alone cannot identify parameter contributions.'},
        'target_order':{'type':'array','items':{'type':'string'}}},['currency','amount_scale','fcf','valuation_date','discount','wacc','g'])


EXAMPLE={'currency':'CNY','amount_scale':'1000000','fcf':['100','110','120'],'valuation_date':'2025-12-31','discount':{'cashflow_timing':'year_end'},'wacc':'.10','g':'.02','net_cash':'20','non_controlling_interest':'0','shares':{'count':'100','scale':'1000000'}}

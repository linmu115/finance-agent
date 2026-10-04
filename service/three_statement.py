"""Annual three-statement model with explicit financing; no balancing plug."""
from .research_models import (_calculation, _num, _integer, _obj, _rows, _result, ValidationError, ZERO, ONE)

OPENING=['cash','receivables','inventory','ppe','other_assets','payables','debt','other_liabilities','equity']
DRIVERS=['revenue_growth','gross_margin','opex_ratio','tax_rate','interest_rate','days_in_year','dso','dio','dpo','da','capex','new_debt','debt_repayment','dividends','equity_issuance','other_assets_change','other_liabilities_change']

@_calculation
def three_statement(spec):
    base_year=_integer(spec.get('base_year'),'base_year',1900)
    opening=_obj(spec.get('opening'),'opening')
    b={k:_num(opening,k,minimum=None if k=='equity' else ZERO,path='opening') for k in OPENING}
    revenue=_num(spec,'base_revenue',positive=True)
    if sum(b[k] for k in ['cash','receivables','inventory','ppe','other_assets']) != sum(b[k] for k in ['payables','debt','other_liabilities','equity']):
        raise ValidationError('opening: assets must equal liabilities plus equity; no balancing plug is permitted')
    forecast=_rows(spec.get('forecast'),'forecast')
    if len(forecast)>50: raise ValidationError('forecast: at most 50 annual periods')
    income=[];cashflow=[];balance=[];checks=[];warnings=[]
    for i,row in enumerate(forecast):
        year=_integer(row.get('year'),f'forecast[{i}].year',1900)
        if year!=base_year+i+1: raise ValidationError('forecast years must be consecutive after base_year')
        p=f'forecast[{i}]'
        d={k:_num(row,k,minimum=None if k in {'revenue_growth','other_assets_change','other_liabilities_change'} else ZERO,path=p) for k in DRIVERS}
        if d['revenue_growth']<=-ONE: raise ValidationError(p+': revenue growth must be greater than -1')
        for k in ['gross_margin','tax_rate']:
            if d[k]>ONE: raise ValidationError(p+'.'+k+': ratio must not exceed 1')
        if d['days_in_year'] not in {360,365,366}: raise ValidationError(p+': days_in_year must be 360, 365 or 366')
        revenue*=ONE+d['revenue_growth'];cogs=revenue*(ONE-d['gross_margin']);opex=revenue*d['opex_ratio']
        ebit=revenue-cogs-opex-d['da'];interest=b['debt']*d['interest_rate'];ebt=ebit-interest
        tax=max(ebt,ZERO)*d['tax_rate'];ni=ebt-tax
        ar=revenue*d['dso']/d['days_in_year'];inventory=cogs*d['dio']/d['days_in_year'];ap=cogs*d['dpo']/d['days_in_year']
        working_change=(ar-b['receivables'])+(inventory-b['inventory'])-(ap-b['payables'])
        cfo=ni+d['da']-working_change-d['other_assets_change']+d['other_liabilities_change']
        cfi=-d['capex'];cff=d['new_debt']-d['debt_repayment']+d['equity_issuance']-d['dividends']
        end={**b,'receivables':ar,'inventory':inventory,'payables':ap,'ppe':b['ppe']+d['capex']-d['da'],
             'debt':b['debt']+d['new_debt']-d['debt_repayment'],'other_assets':b['other_assets']+d['other_assets_change'],
             'other_liabilities':b['other_liabilities']+d['other_liabilities_change'],
             'equity':b['equity']+ni+d['equity_issuance']-d['dividends'],'cash':b['cash']+cfo+cfi+cff}
        for k in ['ppe','debt','other_assets','other_liabilities']:
            if end[k]<ZERO: raise ValidationError(p+': negative closing '+k+'; revise explicit assumptions')
        assets=sum(end[k] for k in ['cash','receivables','inventory','ppe','other_assets'])
        liabilities=sum(end[k] for k in ['payables','debt','other_liabilities'])
        residual=assets-liabilities-end['equity']
        # Decimal repeating fractions can leave a rounding residual at the 50-digit boundary.
        tolerance=max(abs(assets),abs(liabilities),abs(end['equity']),ONE)*_num({'t':'1e-45'},'t')
        if abs(residual)>tolerance: raise ValidationError('internal_three_statement_balance_failed')
        if end['cash']<ZERO: warnings.append(f'{year}: cash shortfall {abs(end["cash"])}; no financing has been invented')
        income.append({'year':year,'revenue':revenue,'cogs':cogs,'gross_profit':revenue-cogs,'opex':opex,'da':d['da'],'ebit':ebit,'interest_expense':interest,'profit_before_tax':ebt,'tax':tax,'net_income':ni})
        cashflow.append({'year':year,'opening_cash':b['cash'],'net_income':ni,'da':d['da'],'working_capital_change':working_change,'operating_cash_flow':cfo,'investing_cash_flow':cfi,'financing_cash_flow':cff,'net_cash_change':cfo+cfi+cff,'closing_cash':end['cash']})
        balance.append({'year':year,**end,'assets':assets,'liabilities':liabilities,'liabilities_and_equity':liabilities+end['equity']})
        checks.append({'year':year,'balance_residual':residual,'cash_rollforward_residual':end['cash']-b['cash']-cfo-cfi-cff,'debt_rollforward_residual':end['debt']-b['debt']-d['new_debt']+d['debt_repayment'],'funding_shortfall':max(-end['cash'],ZERO)})
        b=end
    return _result('three_statement',spec,{'net_income':'(revenue-cogs-opex-da)-opening_debt*interest_rate-tax','operating_cash_flow':'net_income+da-delta(receivables+inventory-payables)-other_assets_change+other_liabilities_change','closing_cash':'opening_cash+operating_cash_flow-capex+new_debt-debt_repayment+equity_issuance-dividends','closing_equity':'opening_equity+net_income+equity_issuance-dividends'},
                   {'period_count':len(forecast),'closing_cash':b['cash'],'closing_debt':b['debt'],'closing_equity':b['equity'],'balance_check':'passed_with_decimal_tolerance'},
                   {'income_statement':income,'cash_flow_statement':cashflow,'balance_sheet':balance,'checks':checks},
                   warnings+['Annual simplified model. Interest is charged on opening debt; no tax-loss carryforward, automatic revolver, minority interests or OCI. Other asset/liability changes are operating cash items. Negative cash is an explicit funding shortfall.'])

def schema(common,decimal,obj):
    return obj({**common,'base_year':{'type':'integer'},'base_revenue':decimal,'opening':obj({k:decimal for k in OPENING},OPENING),'forecast':{'type':'array','minItems':1,'maxItems':50,'items':obj({'year':{'type':'integer'},**{k:decimal for k in DRIVERS}},['year',*DRIVERS])}},['currency','amount_scale','base_year','base_revenue','opening','forecast'])

EXAMPLE={'currency':'CNY','amount_scale':'1','base_year':2024,'base_revenue':'1000','opening':{'cash':'100','receivables':'100','inventory':'120','ppe':'400','other_assets':'30','payables':'80','debt':'200','other_liabilities':'70','equity':'400'},'forecast':[{'year':2025,'revenue_growth':'0.1','gross_margin':'0.4','opex_ratio':'0.15','tax_rate':'0.25','interest_rate':'0.05','days_in_year':'365','dso':'36.5','dio':'73','dpo':'36.5','da':'40','capex':'60','new_debt':'0','debt_repayment':'20','dividends':'20','equity_issuance':'0','other_assets_change':'0','other_liabilities_change':'0'}]}

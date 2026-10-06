"""Units of existing calculator outputs; no inference from numeric magnitude."""
MONEY_FIELDS = set('revenue cogs gross_profit opex da ebit ebitda nopat net_income cfo capex nwc delta_nwc fcff pv_fcff enterprise_value equity_value net_debt cash debt receivables inventory payables assets liabilities equity amount terminal_revenue terminal_ebit terminal_nopat terminal_da terminal_capex terminal_nwc terminal_delta_nwc terminal_fcff terminal_value pv_terminal_value sum_pv_fcff net_working_capital non_controlling_interest preferred_equity non_operating_assets_ex_cash explicit_forecast_pv terminal_pv terminal_reinvestment cash_tax'.split())
RATIO_FIELDS = set('revenue_growth gross_margin ebit_margin net_margin tax_rate nwc_ratio da_ratio capex_ratio wacc growth discount_factor cash_conversion debt_ratio current_ratio quick_ratio roe roa capex_to_cfo roic terminal_reinvestment_rate terminal_value_share'.split())
PER_SHARE_FIELDS = {'value_per_share', 'reference_value_per_share', 'eps', 'price_per_share'}


def quantity_unit(model, path):
    parts = path.split('.')
    # An item of a list takes the unit of the list: sensitivity.wacc.0 is a wacc.
    key = next((part for part in reversed(parts) if not part.isdigit()), '')
    # A comparable peer's own price, EPS, EV and EBITDA are in that peer's currency and unit; only their ratio enters the model.
    peer_input = model['kind'] == 'comparables' and (parts[0] == 'peers' or parts[:2] == ['spec', 'peers'])
    if key in MONEY_FIELDS:
        return None if peer_input else {'unit': '元', 'scale': model['spec']['amount_scale']}
    if key in RATIO_FIELDS or key.endswith('_growth'):
        return {'unit': 'ratio'}
    if key in PER_SHARE_FIELDS:
        return None if peer_input else {'unit': '元/股'}
    if key in {'multiple', 'selected_multiple', 'pe', 'pb', 'ev_ebitda'}:
        return {'unit': '倍'}
    if key in {'days', 'receivable_days', 'inventory_days', 'payable_days', 'cash_conversion_cycle'}:
        return {'unit': '天'}
    if key == 'shares_outstanding':
        return {'unit': '股'}
    return None


AMOUNT_UNITS = {'1': '元', '1000': '千元', '10000': '万元', '1000000': '百万元', '100000000': '亿元', '1000000000': '十亿元'}


def unit_label(model, path):
    """Unit text for an exported column or input, e.g. 'CNY 百万元', 'ratio', 'CNY/股'. '' when the field has no unit."""
    info = quantity_unit(model, path)
    if info is None:
        return ''
    currency = model['spec'].get('currency', '')
    if info['unit'] == '元':
        scale = str(info['scale'])
        return (currency + ' ' + AMOUNT_UNITS.get(scale, '元×' + scale)).strip()
    if info['unit'] == '元/股':
        return currency + '/股' if currency else '元/股'
    return info['unit']

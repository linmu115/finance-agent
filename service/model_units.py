"""Units of existing calculator outputs; no inference from numeric magnitude."""
MONEY_FIELDS = set('revenue cogs gross_profit opex da ebit ebitda nopat net_income cfo capex nwc delta_nwc fcff pv_fcff enterprise_value equity_value net_debt cash debt receivables inventory payables assets liabilities equity amount terminal_revenue terminal_ebit terminal_nopat terminal_da terminal_capex terminal_nwc terminal_delta_nwc terminal_fcff terminal_value pv_terminal_value sum_pv_fcff'.split())
RATIO_FIELDS = set('revenue_growth gross_margin ebit_margin net_margin tax_rate nwc_ratio da_ratio capex_ratio wacc growth discount_factor cash_conversion debt_ratio current_ratio quick_ratio roe roa capex_to_cfo'.split())
PER_SHARE_FIELDS = {'value_per_share', 'reference_value_per_share', 'eps', 'price_per_share'}


def quantity_unit(model, path):
    key = path.split('.')[-1]
    if key in MONEY_FIELDS:
        return {'unit': '元', 'scale': model['spec']['amount_scale']}
    if key in RATIO_FIELDS or key.endswith('_growth'):
        return {'unit': 'ratio'}
    if key in PER_SHARE_FIELDS:
        return {'unit': '元/股'}
    if key in {'multiple', 'pe', 'pb', 'ev_ebitda'}:
        return {'unit': '倍'}
    if key in {'days', 'receivable_days', 'inventory_days', 'payable_days', 'cash_conversion_cycle'}:
        return {'unit': '天'}
    if key == 'shares_outstanding':
        return {'unit': '股'}
    return None

"""Units of existing calculator outputs; no inference from numeric magnitude."""
MONEY_FIELDS = set('revenue cogs gross_profit opex da ebit ebitda nopat net_income cfo capex nwc delta_nwc fcff pv_fcff enterprise_value equity_value net_debt cash debt receivables inventory payables assets liabilities equity amount terminal_revenue terminal_ebit terminal_nopat terminal_da terminal_capex terminal_nwc terminal_delta_nwc terminal_fcff terminal_value pv_terminal_value sum_pv_fcff net_working_capital non_controlling_interest preferred_equity non_operating_assets_ex_cash explicit_forecast_pv terminal_pv terminal_reinvestment cash_tax'.split())
MONEY_FIELDS.update('''
earnings base_revenue fixed_cash_opex ppe other_assets other_liabilities
new_debt debt_repayment dividends equity_issuance other_assets_change other_liabilities_change
interest_expense interest_income profit_before_tax tax opening_cash closing_cash closing_debt closing_equity
working_capital_change operating_cash_flow investing_cash_flow financing_cash_flow net_cash_change
liabilities_and_equity balance_residual cash_rollforward_residual debt_rollforward_residual funding_shortfall
credit_sales purchases receivables_begin receivables_end inventory_begin inventory_end payables_begin payables_end
assets_begin assets_end nonrecurring_net_income recurring_net_income other_operating_income reported_operating_profit
finance_expense net_interest_expense finance_expense_noninterest_residual cfo_less_capex cash_profit_gap
ebit_adjustments_total starting_profit explained_cfo reported_cfo unexplained_residual
revenue_change net_income_change ebit_change equity_value_change reported_operating_profit_change
volume_effect price_effect revenue_residual ebit_residual reported_operating_profit_residual
revenue_effect cogs_effect opex_effect other_operating_income_effect finance_expense_effect ebit_adjustments_effect
baseline_revenue scenario_revenue baseline_ebitda scenario_ebitda baseline_ebit scenario_ebit
'''.split())
RATIO_FIELDS = set('revenue_growth gross_margin ebit_margin net_margin tax_rate nwc_ratio da_ratio capex_ratio wacc growth discount_factor cash_conversion debt_ratio current_ratio quick_ratio roe roa capex_to_cfo roic terminal_reinvestment_rate terminal_value_share'.split())
RATIO_FIELDS.update('''
opex_ratio interest_rate cfo_margin accruals_to_assets revenue_yoy net_income_yoy
exposed_material_share pass_through_rate price_elasticity material_cost_changes volume_changes autonomous_price_changes demand_factor
'''.split())
PER_SHARE_FIELDS = {'value_per_share', 'reference_value_per_share', 'eps', 'price_per_share'}
VOLUME_FIELDS = {'volume', 'baseline_volume', 'scenario_volume'}
UNIT_PRICE_FIELDS = {'unit_price', 'material_cost_per_unit', 'other_variable_cost_per_unit',
                     'baseline_unit_price', 'scenario_unit_price', 'exposed_material_cost_change_per_unit', 'price_pass_through_per_unit'}


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
    if key in {'multiple', 'selected_multiple', 'pe', 'pb', 'ev_ebitda', 'receivables_turnover', 'inventory_turnover', 'payables_turnover'}:
        return {'unit': '倍'}
    if key in {'days', 'days_in_year', 'receivable_days', 'inventory_days', 'payable_days', 'cash_conversion_cycle', 'dso', 'dio', 'dpo'}:
        return {'unit': '天'}
    if parts[-2:] == ['shares', 'count']:
        shares = model['spec']
        for part in parts[:-1]:
            if part != 'spec':
                shares = shares[part]
        return {'unit': '股', 'scale': shares['scale']}
    if key == 'shares_outstanding':
        return {'unit': '股'}
    if key in {'period_count', 'included_peers', 'excluded_peers'}:
        return {'unit': '个'}
    return None


AMOUNT_UNITS = {'1': '元', '1000': '千元', '10000': '万元', '1000000': '百万元', '100000000': '亿元', '1000000000': '十亿元'}
SHARE_UNITS = {'1': '股', '10000': '万股', '1000000': '百万股', '100000000': '亿股'}


def unit_label(model, path):
    """Unit text for an exported column or input, e.g. 'CNY 百万元', 'ratio', 'CNY/股'. '' when the field has no unit."""
    key = next((part for part in reversed(path.split('.')) if not part.isdigit()), '')
    currency = model['spec'].get('currency', '')
    if key in VOLUME_FIELDS | UNIT_PRICE_FIELDS:
        volume = model['spec'].get('volume_unit', '')
        if key in VOLUME_FIELDS or not volume:
            return volume
        scale = str(model['spec']['amount_scale'])
        return (currency + ' ' + AMOUNT_UNITS.get(scale, '元×' + scale) + '/' + volume).strip()
    if key in {'lag_years', 'discount_exponent', 'terminal_discount_exponent'}:
        return '年'
    if key == 'amount_scale' or path.removeprefix('spec.').endswith('shares.scale'):
        return '倍'
    info = quantity_unit(model, path)
    if info is None:
        return ''
    if info['unit'] == '元':
        scale = str(info['scale'])
        return (currency + ' ' + AMOUNT_UNITS.get(scale, '元×' + scale)).strip()
    if info['unit'] == '元/股':
        return currency + '/股' if currency else '元/股'
    if info['unit'] == '股':
        scale = str(info.get('scale', '1'))
        return SHARE_UNITS.get(scale, '股×' + scale)
    return info['unit']

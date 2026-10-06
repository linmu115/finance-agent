"""Local, non-blocking checks. Preserve supplied evidence and computed results."""
from decimal import Decimal, InvalidOperation


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def review_model(kind, spec):
    checks, usage = [], []
    basis = spec.get('input_basis') or {}
    refs = spec.get('source_refs') or {}

    def check(rule, status, paths, message, **detail):
        checks.append({'rule': rule, 'status': status, 'input_paths': paths,
                       'message': message, **detail})

    # A citation establishes where an input came from, not that a perpetual
    # extension of it is an observed fact. Keep both classifications intact.
    if kind in {'dcf', 'manufacturing_scenario'}:
        prefix = 'dcf.' if kind == 'manufacturing_scenario' else ''
        model = spec.get('dcf', {}) if prefix else spec
        for name in model.get('terminal', {}):
            path = prefix + 'terminal.' + name
            declared = basis.get(path, {})
            usage.append({'path': path, 'usage': 'model_assumption',
                          'source_basis': declared.get('basis', 'unclassified'),
                          'source_kind': declared.get('source_kind', 'unknown'),
                          'rationale': '用于永续阶段的设定；引用可支持选择依据，但不使外推成为已实现事实。',
                          'source_refs': refs.get(path, [])})
        if usage:
            check('terminal_use_is_assumption', 'assumption', [item['path'] for item in usage],
                  '终值参数是长期估值假设，需结合敏感性理解结果。',
                  affected_results=['enterprise_value', 'equity_value', 'value_per_share'])

    if kind != 'financial_quality' or not spec.get('profit_bridge'):
        return checks, usage
    contract = spec['profit_bridge']
    treatment = contract['finance_expense_treatment']
    for index, row in enumerate(spec.get('periods', [])):
        prefix = f'periods.{index}'
        components = row.get('opex_components')
        if isinstance(components, list) and components:
            amounts = [number(item.get('amount')) for item in components if isinstance(item, dict)]
            opex = number(row.get('opex'))
            if len(amounts) == len(components) and all(value is not None for value in amounts) and opex is not None:
                total = sum(amounts, Decimal(0))
                residual = opex - total
                check('opex_component_total', 'passed' if residual == 0 else 'needs_review',
                      [prefix + '.opex', prefix + '.opex_components'],
                      '费用明细与汇总一致。' if residual == 0 else '费用明细与汇总存在差额，需核对遗漏或重复项目。',
                      year=row.get('year'), residual=str(residual), component_total=str(total))
            finance = [i for i, item in enumerate(components) if isinstance(item, dict) and item.get('kind') == 'finance_expense']
            if finance and treatment == 'separate' and number(row.get('finance_expense')) not in (None, Decimal(0)):
                check('finance_expense_double_count', 'needs_review',
                      [prefix + '.opex_components.' + str(i) for i in finance] + [prefix + '.finance_expense'],
                      '费用汇总已包含财务费用，同时又单列扣减；需修正费用范围后重算相关利润。',
                      year=row.get('year'), affected_results=['profit_attribution'])

        keys = ['revenue', 'cogs', 'opex', 'other_operating_income', 'reported_operating_profit']
        if treatment == 'separate':
            keys.append('finance_expense')
        values = {key: number(row.get(key)) for key in keys}
        # Check each period, not just the change. Equal duplicate deductions in
        # two years can disappear from a change-only reconciliation.
        if any(value is None for value in values.values()):
            check('reported_profit_reconciliation', 'not_checked',
                  [prefix + '.' + key for key, value in values.items() if value is None],
                  '缺少利润小计或费用组成，本期尚不能完整勾稽；保留已提供数值，不将缺项补零。',
                  year=row.get('year'), affected_results=['profit_attribution'])
            continue
        expected = values['revenue'] - values['cogs'] - values['opex'] + values['other_operating_income']
        if treatment == 'separate':
            expected -= values['finance_expense']
        residual = values['reported_operating_profit'] - expected
        message = '按声明的费用范围与报表利润小计一致。' if residual == 0 else '按声明的费用范围无法解释报表利润小计，差额需核对列报、遗漏项目或舍入。'
        if residual != 0 and treatment == 'separate' and residual == values['finance_expense']:
            message += ' 差额恰为单列财务费用，可能已在费用汇总中扣除；需查明细确认。'
        check('reported_profit_reconciliation', 'passed' if residual == 0 else 'needs_review',
              [prefix + '.' + key for key in keys], message, year=row.get('year'),
              declared_subtotal=str(values['reported_operating_profit']), calculated_subtotal=str(expected),
              residual=str(residual), affected_results=['profit_attribution'])
    return checks, usage

"""Cash/working-capital references for explanation retrieval, not profit steps."""
from datetime import date, timedelta

from .analysis_report import record_quantity
from .financial_workpapers import ALIASES, cell, col, table, meta, dimensions_ok, source
from .workpaper_analyst import delta, unknown


def balance_quantity(a, metric, period, begin=False):
    if metric in ALIASES:
        return a.balance(metric, period, begin)
    start, end = a.window(period)
    if not start or not end: return unknown(f'{period} 缺少报告起止日期')
    when = str(date.fromisoformat(start)-timedelta(days=1)) if begin else end
    matches = [r for r in a.records if r['metric'] == metric and r['period'] == when
               and meta(r).get('statement') == 'balance' and dimensions_ok(r) and r['currency'] == a.currency]
    if matches and len({r['value'] for r in matches}) == 1 and all(r.get('quality') != 'conflict' for r in matches):
        return record_quantity(matches[0])
    return cell(None, currency=a.currency, sources=[source(r) for r in matches],
                reason=f'{when} {metric} ' + ('同口径金额冲突' if matches else '缺少唯一同口径披露'))


def context_changes(a):
    now = a.ps[0]; before = a.ps[1] if len(a.ps) > 1 else None
    rows = []
    for key, label, statement in [('interest_income', '利息收入', 'income'), ('cfo', '经营活动现金流量净额', 'cashflow')]:
        current = a.pick(key, now, statement)
        previous = a.pick(key, before, statement) if before else unknown('没有可比期')
        rows.append({'key': key, 'item': label, 'current': current, 'previous': previous,
                     'change': delta(current, previous), 'query_keys': [key], 'basis': f'{now} 对 {before}；同期间原值变化，不作为额外利润贡献'})
    for key, label in [('inventory', '存货'), ('receivables', '应收账款'), ('payables', '应付账款及票据'),
                       ('prepayments', '预付款项'), ('other_receivables', '其他应收款'),
                       ('contract_assets', '合同资产'), ('contract_liabilities', '合同负债'),
                       ('other_payables', '其他应付款'), ('taxes_payable', '应交税费'),
                       ('employee_benefits_payable', '应付职工薪酬')]:
        current = balance_quantity(a, key, now); previous = balance_quantity(a, key, now, True)
        rows.append({'key': key, 'item': label, 'current': current, 'previous': previous,
                     'change': delta(current, previous), 'query_keys': [key],
                     'basis': f'{now} 期末对期初；余额变化不等于现金流影响，不当作同比'})
    cash_rows = a.base['tables'].get('indirect_bridge', {}).get('rows', [])
    for original in cash_rows:
        if original['period'] != now or original['category'] != '营运资本': continue
        previous = [r['amount'] for r in cash_rows if r['period'] == before and r['item'] == original['item']]
        prior = previous[0] if len(previous) == 1 else unknown('没有唯一同口径间接法比较行')
        label = original['item']
        topic = 'inventory' if '存货' in label else 'receivables' if '应收' in label else 'payables' if '应付' in label else 'working_capital'
        rows.append({'key': 'indirect_' + original['key'], 'item': label, 'current': original['amount'], 'previous': prior,
                     'change': delta(original['amount'], prior), 'query_keys': [topic, 'working_capital'],
                     'basis': '间接法披露的营运资金调整行，本期对上期；与余额变化分开，不重复加总'})
    cols = {k: col(label) for k, label in [('key', '行键'), ('item', '变动项'), ('basis', '口径') ]}
    cols.update({k: col(label, '百万元', a.currency) for k, label in [('current', '本期/期末'), ('previous', '比较期/期初'), ('change', '原值变化')]})
    return table(cols, rows, '现金与营运资金变动参考（不重复计入利润桥）')

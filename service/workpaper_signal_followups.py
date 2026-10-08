"""Questions to investigate triggered phenomena; hypotheses are never facts."""
from .financial_workpapers import col, table
from .workpaper_explanations import driver_evidence


# Topic, test, indicators. These are signal-type hypotheses, not issuer rules.
ALTERNATIVES = {
    '利润与现金流': [
        ('季节性备货或渠道扩张占用现金', '对照同季库存及次期去化，区分增长备货与滞销', ['存货周转天数', '存货减值', '经营现金流']),
        ('结算和回款时点变化', '核对销售渠道账期、期后回款及应付结算', ['应收回款率', '应收/应付周转天数']),
        ('一次性税款、非现金收益或减值影响利润现金差', '把税款及非现金调整与现金流补充资料逐项对应', ['支付税费', '扣非利润', '非现金调整'])],
    '应收': [
        ('线下渠道或客户结构改变带来较长账期', '分别核对渠道账期与逾期分布，不能用发票账龄代替逾期', ['分渠道信用期', '应收周转天数', '逾期占比']),
        ('结算节奏或季节性销售集中', '查看同季和期后回款，区分时点效应与信用恶化', ['期后回款率', '客户集中度', '信用减值'])],
    '存货': [
        ('季节性备货或国际运输周期延长', '核对订单、库存地域与次期销量，检验备货能否去化', ['库存地域/品类', '周转天数', '期后销量']),
        ('需求变化导致滞销或成本/产品组合变化', '分品类核对库龄、售价和跌价准备', ['库龄', '跌价计提率', '毛利率'])],
    '其他资产异动': [
        ('预付采购、工程或结算时点变化', '核对交易对象、合同履行和期后结转', ['预付款账龄', '交易对手', '期后结转']),
        ('存款期限变化或资产重分类', '核对附注组成及到期日，区分资金用途与科目搬移', ['定期存款期限', '受限资金', '其他资产构成'])],
    '存贷双高': [
        ('集团地域、币种或期限错配', '核对现金可动用范围与债务到期结构', ['受限资金', '分币种头寸', '短期偿债额']),
        ('定期存款、季节性营运资金安排或融资备用', '对齐利息分子与存款分母，核对存款收益和借款成本', ['定期存款余额/期限', '利息收入', '借款成本'])],
    '季度集中': [
        ('节庆时点、季节性出货或结算集中', '比较至少三个可比年度的同季数据及期后反转', ['同季收入/利润', '期后退货', '次季现金流']),
        ('年末减值、奖金、税费或一次性处置集中', '核对单季调整事项，不能把全年原因自动归给Q4', ['单季减值', '扣非利润', '一次性项目'])],
    '减值与商誉': [
        ('信用、库存或资产组经营预期变化', '核对对应资产组、账龄及管理层关键估计', ['逾期率', '可收回金额', '预测现金流']),
        ('单项处置、组合变化或一次性估计更新', '区分计提、转回和核销，检查下一期是否重复', ['减值新增/转回/核销', '资产组范围', '关键估计敏感性'])],
    '非经常性损益依赖': [
        ('处置、补助或公允价值等一次性收益', '核对项目金额、税效与现金实现，不把发生过等同可重复', ['税后非经常性损益', '扣非利润', '处置现金流']),
        ('经常性利润下降造成分母效应', '同时看绝对额及扣非利润变化，避免只看占比', ['归母利润', '扣非利润增速', '非经常损益绝对额'])],
    '审计与治理': [
        ('审计师轮换、任期或业务安排变化', '读取变更理由及前后任沟通披露，不能仅凭变更推断问题', ['变更原因', '审计费用', '前任意见']),
        ('特定事项不确定性或会计判断差异', '核对审计意见原段、事项后续及是否已解决', ['审计意见', '强调事项', '整改/事项进展'])],
}


def signal_topics(row):
    key = row['key']
    if key.startswith('q4_'): return ['quarter']
    if row['family'] == '利润与现金流': return ['cfo', 'working_capital', 'inventory', 'receivables', 'payables']
    if key.startswith('receivables'): return ['receivables', 'credit_impairment']
    if key.startswith('inventory'): return ['inventory']
    if key.startswith('other_receivables'): return ['other_receivables']
    if key.startswith('prepayments'): return ['prepayments']
    if key.startswith('other_noncurrent'): return ['other_noncurrent']
    if key == 'interest_yield': return ['interest_income', 'finance_net']
    if row['family'] == '存贷双高': return ['cash_balance', 'debt', 'finance_net']
    if key.startswith('credit_impairment'): return ['credit_impairment']
    if row['family'] == '减值与商誉': return ['asset_impairment']
    if row['family'] == '非经常性损益依赖': return ['nonrecurring']
    return ['audit']


def persistence(row, rows, periods):
    suffix = next((row['key'][len(p):] for p in periods if row['key'].startswith(p + '_')), None)
    if row['key'] == 'cash_divergence_run': suffix = '_cash_conversion'
    if suffix:
        by_key = {r['key']: r for r in rows}
        samples = [(p, by_key.get(p + suffix)) for p in periods]
    else:
        # Two inputs yield one change observation, not two repeated signals.
        samples = [(periods[0], row)]
    known = [(p, r) for p, r in samples if r and r['value']['value'] is not None and r['triggered'] != '未知']
    missing = [p for p, r in samples if not r or r['value']['value'] is None or r['triggered'] == '未知']
    triggered = [p for p, r in known if r['triggered'] == '是']
    adjacent = all(int(a[:4]) - int(b[:4]) == 1 and a[4:] == b[4:] for (a, _), (b, _) in zip(samples, samples[1:]))
    allowed = len(known) >= 3 and not missing and adjacent and len(triggered) == len(known)
    n = len(known)
    summary = (f'{n}期同窗口相邻样本均触发，可描述这{n}期持续现象；观察窗以外未知' if allowed else
               f'仅有{n}期可计算样本，不足三期，不能判断持续性' if n < 3 else
               f'{n}期可计算样本中{len(triggered)}期触发；有未触发、缺值或期间间隔，不作持续性断言')
    if not suffix: summary += '；两期作差或单次披露只形成一次信号观察'
    return {'sample_periods': [p for p, _ in known], 'known_sample_count': n, 'triggered_periods': triggered,
            'missing_periods': missing, 'allow_continuous_claim': allowed, 'summary': summary}


def signal_followups(a, rows):
    results = []; evidence = []
    for row in rows:
        if row['triggered'] != '是': continue
        period = next((p for p in a.ps if row['key'].startswith(p + '_')), a.ps[0])
        item = driver_evidence(a, row['key'], row['signal'], {'table': 'signals', 'row_key': row['key'], 'column': 'value'},
                               period, signal_topics(row))
        evidence.append(item)
        alternatives = [{'hypothesis': h, 'status': 'candidate_not_evidence', 'test': test, 'tracking_metrics': metrics}
                        for h, test, metrics in ALTERNATIVES[row['family']]]
        results.append({'key': row['key'], 'signal_ref': {'table': 'signals', 'row_key': row['key']},
                        'management_explanation': {k: item[k] for k in ('disclosure_status', 'status', 'evidence', 'quantitative_limit', 'alignment_note', 'search')},
                        'alternative_explanations': alternatives, 'persistence': persistence(row, rows, a.ps),
                        'tracking_metrics': list(dict.fromkeys(x for alt in alternatives for x in alt['tracking_metrics']))})
    columns = {k: col(v) for k, v in [('key', '信号行键'), ('management_explanation', '管理层解释'), ('pages', 'PDF页'),
                                    ('alternative_explanations', '待检验替代解释（不是事实）'), ('persistence', '样本与持续性'), ('tracking_metrics', '后续跟踪指标')]}
    readable = [{'key': r['key'], 'management_explanation': r['management_explanation']['status'] + '：' +
                '\n\n'.join(x['quote'] for x in r['management_explanation']['evidence']),
                'pages': ', '.join(str(p) for p in sorted({x['page'] for x in r['management_explanation']['evidence']})),
                'alternative_explanations': '\n'.join(x['hypothesis'] + '；核验：' + x['test'] for x in r['alternative_explanations']),
                'persistence': r['persistence']['summary'], 'tracking_metrics': '、'.join(r['tracking_metrics'])} for r in results]
    return results, evidence, table(columns, readable, '已触发信号的解释与追问')

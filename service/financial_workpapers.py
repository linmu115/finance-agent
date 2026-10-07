"""Deterministic, project-scoped workpapers. No model or sandbox execution."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal, localcontext

from .analysis_report import compile_report, record_quantity, render_report
from .research_models import financial_quality


class WorkpaperInputError(ValueError):
    pass


# Semantic aliases, not document-specific row numbers or company-specific values.
ALIASES = {
    'revenue': ('revenue', 'operating_revenue'),
    'cogs': ('cost_of_revenue', 'cost_of_sales', 'operating_cost'),
    'gross_profit': ('gross_profit',),
    'selling': ('selling_expenses', 'selling_expense'),
    'administrative': ('administrative_expenses', 'administrative_expense'),
    'research': ('research_and_development_expenses', 'research_expense'),
    'operating_profit': ('operating_profit', 'operating_loss'),
    'finance_net': ('finance_income_net', 'finance_costs_net', 'net_finance_income'),
    'finance_income': ('finance_income',), 'finance_costs': ('finance_costs',),
    'other_income': ('other_income',), 'other_gains_net': ('other_gains_net',),
    'impairment': ('impairment_reversal_loss_financial_assets', 'reversal_of_ecls_on_financial_and_contract_assets'),
    'fair_value_gains': ('fair_value_gains_on_financial_assets_at_fvtpl',),
    'associates': ('share_of_profits_of_associates',),
    'profit_before_tax': ('profit_before_tax', 'profit_before_income_tax'),
    'tax': ('income_tax_expense', 'income_tax_credit', 'income_tax_credit_expense'),
    'net_profit': ('net_profit', 'profit_for_the_period', 'profit_for_the_period_total'),
    'parent_profit': ('net_profit_parent', 'profit_attributable_to_owners_of_the_company', 'owners_of_the_company'),
    'minority_profit': ('profit_attributable_to_non_controlling_interests', 'non_controlling_interests'),
    'cfo': ('operating_cash_flow', 'net_cash_flow_operating', 'net_cash_used_in_generated_from_operating_activities', 'net_cash_used_in_operating_activities', 'net_cash_generated_from_operating_activities', 'net_cash_inflow_outflow_operating_activities'),
    'cfi': ('investing_cash_flow', 'net_cash_generated_from_used_in_investing_activities', 'net_cash_used_in_investing_activities', 'net_cash_inflow_outflow_investing_activities'),
    'cff': ('financing_cash_flow', 'net_cash_used_in_financing_activities', 'net_cash_generated_from_financing_activities', 'net_cash_inflow_outflow_financing_activities'),
    'operations': ('net_cash_generated_from_operations', 'cash_used_in_operations', 'cash_generated_from_operations'),
    'cash_begin': ('cash_and_cash_equivalents_at_beginning_of_the_period', 'cash_and_cash_equivalents_at_beginning_of_period'),
    'cash_end': ('cash_and_cash_equivalents_at_end_of_the_period', 'cash_and_cash_equivalents_at_end_of_period'),
    'cash_fx': ('effects_of_exchange_rate_changes_on_cash_and_cash_equivalents', 'effect_of_currency_translation_differences'),
    'receivables': ('trade_receivables', 'accounts_receivable', 'trade_receivables_net'),
    'inventory': ('inventories', 'inventory'),
    'payables': ('trade_and_bills_payables', 'trade_payables', 'accounts_payable'),
    'assets': ('total_assets',), 'equity': ('total_equity', 'owners_equity'),
}
INCOME = [('revenue', '收入'), ('cogs', '销售成本（原披露符号）'), ('gross_profit', '毛利'),
          ('selling', '销售费用（原披露符号）'), ('administrative', '管理费用（原披露符号）'),
          ('research', '研发费用（原披露符号）'), ('other_income','其他收入'), ('other_gains_net','其他净收益'),
          ('impairment','减值损失/转回'), ('operating_profit', '营业利润'),
          ('finance_net', '财务净收益/费用（税前、营业利润之后，非现金收息）'),
          ('fair_value_gains','公允价值收益'), ('associates','联营公司损益'),
          ('profit_before_tax', '税前利润'), ('tax', '所得税（原披露符号）')]


def number(value):
    return None if value is None else Decimal(str(value))


def cell(value, unit='元', currency=None, sources=(), formula=None, reason=None):
    return {'value': None if value is None else str(value), 'unit': unit, 'currency': currency,
            'source': {'data_kind': 'calculation', 'inputs': list(sources), 'formula': formula, 'missing_reason': reason}}


def col(label, unit=None, currency=None, **metadata):
    return {'label': label, **({'unit': unit, 'decimals': 4} if unit else {}),
            **({'currency': currency} if currency else {}), **metadata}


def table(columns, rows, title=None):
    return {'columns': columns, 'rows': rows, 'row_key': 'key', **({'title': title} if title else {})}


def source(record):
    return {'fact_id': record['fact_id'], **record['source_ref']}


def meta(record):
    return record['source_ref'].get('normalization', {})


def dimensions_ok(record):
    # source_table locates evidence; it is not a business segment.
    return not (set(record.get('dimensions') or meta(record).get('dimensions', {})) - {'source_table'})


def source_position(record):
    # Extractors may retain several logical rows inside one physical PDF cell.
    return (record['source_ref'].get('row', 0), meta(record).get('numeric_span', {}).get('start', 0))


def load_facts(service, project, document_id=None, company=None):
    service.store.project(project)
    if document_id:
        service.store.document(project, document_id)
    with service.store.connect() as db:
        query = 'SELECT DISTINCT metric FROM current_financial_facts WHERE project_id=?'
        args = [project]
        if document_id:
            query += ' AND document_id=?'; args.append(document_id)
        metrics = [r[0] for r in db.execute(query, args)]
    records = []
    for start in range(0, len(metrics), 30):
        result = service.get_financial_metrics(project, metrics[start:start+30], company=company, document_id=document_id)
        records.extend(result['data']['items'])
    return records


class Statement:
    def __init__(self, service, project, facts, scope='consolidated', periods=None):
        self.service, self.project = service, project
        scope = {'合并': 'consolidated', '母公司': 'parent'}.get(scope, scope)
        facts = [r for r in facts if r['scope'] == scope or r['scope'].startswith(scope + '_')]
        companies = sorted({r['company'] for r in facts})
        if len(companies) != 1:
            raise WorkpaperInputError(f'请指定 company 或 document_id，当前口径主体为：{companies}')
        docs = {r['document_id'] for r in facts}
        if len(docs) > 1:
            # Prefer the latest statement, with its own comparatives; retain documents as a tie-break request.
            latest = max((meta(r).get('period_end', '') for r in facts), default='')
            docs = {r['document_id'] for r in facts if meta(r).get('period_end') == latest}
            if len(docs) != 1:
                raise WorkpaperInputError(f'同一最新期有多份资料，请指定 document_id：{sorted(docs)}')
            facts = [r for r in facts if r['document_id'] in docs]
        currencies = sorted({r['currency'] for r in facts if r['metric'] in ALIASES['revenue'] and dimensions_ok(r)})
        if len(currencies) != 1:
            raise WorkpaperInputError(f'收入币种不唯一或缺失：{currencies}；请指定 document_id')
        self.currency, self.company, self.facts = currencies[0], companies[0], facts
        scopes = {r['scope'] for r in facts if r['currency'] == self.currency and r['metric'] in ALIASES['revenue']}
        if len(scopes) != 1:
            raise WorkpaperInputError(f'存在不同会计口径，请指定 scope：{sorted(scopes)}')
        self.scope, self.missing = scope, []
        candidates = sorted({r['period'] for r in facts if r['metric'] in ALIASES['revenue'] and meta(r).get('statement') == 'income' and dimensions_ok(r)})
        if not candidates:
            raise WorkpaperInputError('没有可定位到利润表的收入期间；请先完成财报入库')
        if isinstance(periods, str): periods = [periods]
        if periods:
            self.periods = list(dict.fromkeys(periods))
        else:
            latest = candidates[-1]
            previous = str(int(latest[:4])-1) + latest[4:]
            self.periods = [latest, previous]
        self.income_pages = {}
        for period in self.periods:
            anchors = [r for r in facts if r['period'] == period and r['metric'] == 'net_profit' and meta(r).get('statement') == 'income' and dimensions_ok(r)]
            self.income_pages[period] = {r['source_ref'].get('page') for r in anchors}

    def pick(self, key, period, statement=None):
        aliases = ALIASES.get(key, (key,))
        matches = [r for r in self.facts if r['period'] == period and r['metric'] in aliases and dimensions_ok(r)
                   and r['currency'] == self.currency and (not statement or meta(r).get('statement') == statement)]
        if statement == 'income' and self.income_pages.get(period):
            primary = [r for r in matches if r['source_ref'].get('page') in self.income_pages[period]]
            if primary: matches = primary
        if matches:
            # Alias order favours canonical totals over presentation synonyms.
            best = min(aliases.index(r['metric']) for r in matches)
            matches = [r for r in matches if aliases.index(r['metric']) == best]
            values = {r['value'] for r in matches}
            if len(values) == 1 and all(r.get('quality') != 'conflict' for r in matches):
                return matches[0]
        reason = '来源存在冲突' if matches else '缺少同口径披露'
        self.missing.append({'metric': key, 'period': period, 'reason': reason,
                             'candidates': [source(r) for r in matches]})
        return None

    def calculate(self, operation, inputs, unit, refs=(), reason=None):
        if any(value is None for value in inputs.values()) or reason:
            return cell(None, unit, self.currency if unit == '元' else None, refs, reason=reason or '缺少计算输入')
        result = self.service.calculate_financial_metrics(self.project, operation, inputs)
        data = result['data']
        return cell(data.get('value'), unit, self.currency if unit == '元' else None, refs,
                    data.get('formula'), data.get('reason_code'))


def statement_analysis(service, project, document_id=None, company=None, scope='consolidated', periods=None, focus=None):
    st = Statement(service, project, load_facts(service, project, document_id, company), scope, periods)
    currency, ps = st.currency, st.periods
    selected = {}
    for p in ps:
        selected[p] = {k: st.pick(k, p, 'income') for k in [k for k, _ in INCOME] + ['net_profit', 'parent_profit', 'minority_profit']}
        selected[p].update({k: st.pick(k, p, 'cashflow') for k in ('cfo', 'cfi', 'cff', 'operations', 'cash_begin', 'cash_end', 'cash_fx')})
    def val(r): return r['value'] if r else None
    def q(r, reason='缺少同期间、同口径来源'):
        return record_quantity(r) if r else cell(None, currency=currency, reason=reason)
    amount_cols = {p: col(p, '百万元', currency, scope=scope, data_kind='disclosed_actual') for p in ps}
    income_rows = [{'key': k, 'metric': label, **{p: q(selected[p][k]) for p in ps}} for k, label in INCOME]
    # Attribution is represented in different columns, so it cannot be read as consolidated profit.
    profit_rows = [{'key': p, 'period': p, 'consolidated': q(selected[p]['net_profit']),
                    'parent': q(selected[p]['parent_profit']), 'minority': q(selected[p]['minority_profit'])} for p in ps]
    tables = {'income': table({'key': col('行键'), 'metric': col('应计利润表项目'), **amount_cols}, income_rows),
              'profit_attribution': table({'key': col('行键'), 'period': col('期间'),
                  'consolidated': col('合并净利润' if scope not in ('parent', '母公司') else '母公司净利润', '百万元', currency, basis=scope),
                  'parent': col('归母净利润', '百万元', currency, basis='attributable_to_owners'),
                  'minority': col('少数股东损益', '百万元', currency)}, profit_rows)}
    ratios = []
    for key, label in [('gross_profit', '毛利率'), ('selling', '销售费用率'), ('administrative', '管理费用率'), ('research', '研发费用率'), ('net_profit', '合并净利率')]:
        row = {'key': key + '_margin', 'metric': label}
        for p in ps:
            a, b = selected[p][key], selected[p]['revenue']
            numerator = abs(number(val(a))) if a and key in ('selling', 'administrative', 'research') else val(a)
            row[p] = st.calculate('margin', {'numerator': numerator, 'denominator': val(b)}, '%', [source(r) for r in (a, b) if r])
        if len(ps) >= 2:
            row['change_pp'] = st.calculate('subtract', {'a': row[ps[0]]['value'], 'b': row[ps[1]]['value']}, '个百分点', [row[p]['source'] for p in ps[:2]])
        ratios.append(row)
    tables['ratios'] = table({'key': col('行键'), 'metric': col('比率'), **{p: col(p, '%', basis=scope) for p in ps},
                              **({'change_pp': col('本期减可比期', '个百分点')} if len(ps) >= 2 else {})}, ratios)
    growth = []
    if len(ps) >= 2:
        for k, label in INCOME + [('net_profit', '合并净利润'), ('parent_profit', '归母净利润')]:
            a, b = selected[ps[0]][k], selected[ps[1]][k]
            growth.append({'key': k, 'metric': label, 'change': st.calculate('yoy', {'current': val(a), 'previous': val(b)}, '%', [source(r) for r in (a,b) if r]),
                           'basis': f'{ps[0]} 对 {ps[1]}；(本期-基期)/基期；负基期不可解读为改善'})
    tables['growth'] = table({'key': col('行键'), 'metric': col('指标'), 'change': col('增速', '%'), 'basis': col('定义')}, growth)
    cash_rows, bridge_rows, wc_rows, quality_rows = [], [], [], []
    for p in ps:
        picked = selected[p]
        for k in ('cfo', 'cfi', 'cff'):
            cash_rows.append({'key': p+'_'+k, 'period': p, 'metric': k.upper(), 'amount': q(picked[k]), 'classification': k})
        # The source table containing CFO defines operating classification, not the word "interest".
        anchor = picked['cfo']
        if anchor:
            src = anchor['source_ref']
            flows = [r for r in st.facts if r['period'] == p and meta(r).get('statement') == 'cashflow'
                     and r['source_ref'].get('table_id') == src.get('table_id') and r['currency'] == currency and dimensions_ok(r)
                     and source_position(r) < source_position(anchor)]
            start = picked['operations']
            # When one source table spans all activities, only rows after the operating subtotal belong here.
            if start: flows = [r for r in flows if source_position(r) > source_position(start)]
            flows = [r for r in flows if r['metric'] not in sum((list(ALIASES[k]) for k in ('cfo','cfi','cff','operations')), [])]
            bridge_inputs = ([start] if start else []) + flows
            for r in bridge_inputs:
                bridge_rows.append({'key': p+'_operating_'+r['fact_id'], 'period': p, 'bridge': '经营小计至CFO',
                                    'item': meta(r).get('label', r['metric']), 'direction': '起点' if r is start else ('加' if number(r['value']) >= 0 else '减'),
                                    'amount': q(r), 'reason': '披露的经营活动项目；符号决定方向'})
            explained = st.calculate('sum', {'values': [r['value'] for r in bridge_inputs]}, '元', [source(r) for r in bridge_inputs]) if bridge_inputs else cell(None, currency=currency, reason='缺少经营现金流明细')
            residual = st.calculate('subtract', {'a': val(anchor), 'b': explained['value']}, '元', [source(anchor), explained['source']])
            bridge_rows.extend([{'key': p+'_operating_cfo', 'period': p, 'bridge': '经营小计至CFO', 'item': '披露CFO', 'direction': '终点', 'amount': q(anchor), 'reason': ''},
                                {'key': p+'_operating_residual', 'period': p, 'bridge': '经营小计至CFO', 'item': '未解释差额', 'direction': '残差', 'amount': residual, 'reason': 'CFO-已列经营项目；不以配平项掩盖缺失'}])
            for r in flows:
                cash_rows.append({'key': p+'_'+r['fact_id'], 'period': p, 'metric': meta(r).get('label', r['metric']), 'amount': q(r), 'classification': 'operating'})
        for kind, previous in [('cfi','cfo'),('cff','cfi')]:
            anchor, previous_anchor = picked[kind], picked[previous]
            if not anchor: continue
            for r in st.facts:
                same_table = r['source_ref'].get('table_id') == anchor['source_ref'].get('table_id')
                after_previous = not previous_anchor or previous_anchor['source_ref'].get('table_id') != anchor['source_ref'].get('table_id') or source_position(r) > source_position(previous_anchor)
                if r['period']==p and meta(r).get('statement')=='cashflow' and dimensions_ok(r) and r['currency']==currency and same_table and after_previous and source_position(r)<source_position(anchor):
                    cash_rows.append({'key':p+'_'+r['fact_id'],'period':p,'metric':meta(r).get('label',r['metric']),'amount':q(r),'classification':'investing' if kind=='cfi' else 'financing'})
        cash_parts = [picked[k] for k in ('cash_begin','cfo','cfi','cff','cash_fx')]
        for k, r in zip(('cash_begin','cfo','cfi','cff','cash_fx'), cash_parts):
            bridge_rows.append({'key': p+'_cash_'+k, 'period': p, 'bridge': '期初至期末现金', 'item': k,
                                'direction': '起点' if k == 'cash_begin' else ('加' if r and number(r['value']) >= 0 else '减' if r else '未知'), 'amount': q(r), 'reason': ''})
        explained = st.calculate('sum', {'values': [r['value'] for r in cash_parts]}, '元', [source(r) for r in cash_parts]) if all(cash_parts) else cell(None, currency=currency, reason='缺少现金桥项目，未按零处理')
        bridge_rows += [{'key': p+'_cash_end', 'period': p, 'bridge': '期初至期末现金', 'item': '期末现金', 'direction': '终点', 'amount': q(picked['cash_end']), 'reason': ''},
                        {'key': p+'_cash_residual', 'period': p, 'bridge': '期初至期末现金', 'item': '未解释差额', 'direction': '残差',
                         'amount': st.calculate('subtract', {'a': val(picked['cash_end']), 'b': explained['value']}, '元', [source(r) for r in cash_parts if r]), 'reason': ''}]
        rev = picked['revenue']
        begin, end = (meta(rev).get('period_start'), meta(rev).get('period_end')) if rev else (None,None)
        days = (date.fromisoformat(end)-date.fromisoformat(begin)).days+1 if begin and end else None
        inputs = {'year': int(p[:4]), 'days': days}
        for key, rawkey in [('revenue','revenue'),('net_income','net_profit'),('cfo','cfo'),('cogs','cogs')]:
            if picked[rawkey]: inputs[key] = str(abs(number(val(picked[rawkey])))) if key == 'cogs' else val(picked[rawkey])
        balance_refs = []
        for key, label in [('receivables','应收'),('inventory','存货'),('payables','应付')]:
            opening = st.pick(key, str(date.fromisoformat(begin)-timedelta(days=1)), 'balance') if begin else None
            closing = st.pick(key, end, 'balance') if end else None
            for suffix,r in [('begin',opening),('end',closing)]:
                if r:
                    inputs[key+'_'+suffix] = val(r)
                    balance_refs.append(source(r))
            wc_rows.append({'key': p+'_'+key, 'period': p, 'item': label, 'begin': q(opening), 'end': q(closing),
                            'change': st.calculate('subtract', {'a': val(closing),'b': val(opening)}, '元', [source(r) for r in (opening,closing) if r]),
                            'basis': f'{begin or "缺期初日期"} 至 {end or "缺期末日期"}，不挪用其他期间'})
        if days:
            quality = financial_quality({'currency': currency, 'amount_scale': '1', 'period_basis': p[4:] or 'FY',
                                         'receivables_sales_basis':'revenue_proxy','payables_cost_basis':'cogs_proxy','periods':[inputs]})['tables']['quality'][0]
        else: quality = {}
        refs = [source(r) for r in picked.values() if r] + balance_refs
        quality_rows.append({'key':p, 'period':p, **{k:cell(quality.get(k), 'ratio' if k=='cash_conversion' else '天', sources=refs,
                              formula='financial_quality.'+k, reason=quality.get(k+'_reason') or ('缺期间日期' if not days else None)) for k in ('cash_conversion','dso','dio','dpo','cash_conversion_cycle')},
                             'basis': 'CFO/同口径净利润；应收天数采用收入代理，应付天数采用成本代理；按实际期间天数'})
    tables['cash'] = table({'key':col('行键'),'period':col('期间'),'metric':col('现金项目'),'amount':col('披露现金流','百万元',currency),'classification':col('活动类别')},cash_rows)
    tables['bridge'] = table({'key':col('行键'),'period':col('期间'),'bridge':col('现金桥'),'item':col('项目'),'direction':col('方向'),'amount':col('有符号金额','百万元',currency),'reason':col('依据')},bridge_rows)
    tables['working_capital'] = table({'key':col('行键'),'period':col('期间'),'item':col('项目'),**{k:col(label,'百万元',currency) for k,label in [('begin','期初'),('end','期末'),('change','变动')]},'basis':col('期间口径')},wc_rows)
    tables['cash_quality'] = table({'key':col('行键'),'period':col('期间'),'cash_conversion':col('CFO/合并净利润','ratio'),**{k:col(k,'天') for k in ('dso','dio','dpo','cash_conversion_cycle')},'basis':col('计算口径')},quality_rows)
    observations = []
    for row in ratios:
        v = number(row.get('change_pp',{}).get('value'))
        if v is not None:
            observations.append((abs(v), {'key':row['key'], 'finding':f'{row["metric"]}{"上升" if v>=0 else "下降"} {abs(v):.4f} 个百分点', 'basis':'ratios.'+row['key']}))
    for p in ps:
        a,b = selected[p]['net_profit'],selected[p]['cfo']
        if a and b and number(a['value']) > 0 > number(b['value']):
            observations.append((Decimal('Infinity'), {'key':p+'_profit_cash_sign','finding':f'{p} 同口径净利润为正而CFO为负','basis':'profit_attribution / cash'}))
    tables['observations'] = table({'key':col('行键'),'finding':col('确定性数值发现（按百分点幅度排序，符号背离优先）'),'basis':col('对应底稿')}, [r for _,r in sorted(observations,key=lambda x:x[0],reverse=True)])
    tables['missing'] = table({'key':col('行键'),'metric':col('指标'),'period':col('期间'),'reason':col('缺失原因'),'candidates':col('候选来源')},
                               [{'key':str(i),**m,'candidates':json.dumps(m['candidates'],ensure_ascii=False)} for i,m in enumerate(st.missing)])
    return {'title':st.company+' 财报分析底稿','body':f'口径：{scope}；财务净收益属于应计利润，现金桥的收付款分类依据原现金流量表。'+ (f'关注点：{focus}。' if focus else ''), 'tables':tables}, st.facts


def publish(service, project, kind, report, records):
    compiled = compile_report(report, records)
    delivery_id = uuid.uuid4().hex
    folder = service.store.root/'research'/project/'deliveries'/delivery_id
    folder.mkdir(parents=True)
    render_report(compiled, folder)
    (folder/'workpaper.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Required by the existing delivery download endpoint; reuse its manifest contract.
    files = [{'name':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in folder.iterdir() if p.is_file()]
    manifest = {'delivery_id':delivery_id,'files':files,'attachments':[f['name'] for f in files]}
    (folder/'delivery.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    summary = {name:{'columns':t['columns'],'row_key':t.get('row_key','key'),'row_keys':[r.get('key') for r in t['rows']],'rows':len(t['rows'])} for name,t in compiled['tables'].items()}
    return {'kind':kind,'report':compiled,'numeric_tables':compiled['tables'], 'summary':summary,
            'observations':compiled['tables']['observations']['rows'][:5],
            'delivery':{'id':delivery_id,'files':[{'name':f['name'],'url':f'/api/projects/{project}/research/deliveries/{delivery_id}/{f["name"]}'} for f in files]}}


def report_sources(report):
    found = {}
    def visit(value):
        if isinstance(value, dict):
            if value.get('document_id') and value.get('page'):
                locator = {k:value[k] for k in ('document_id','page','table_id','row','column','cell') if k in value}
                found[json.dumps(locator,sort_keys=True)] = locator
            for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(report)
    return list(found.values())


def financial_workpaper(service, project_id, kind='statement_analysis', **options):
    service.store.project(project_id)
    if kind != 'statement_analysis':
        raise WorkpaperInputError('kind 当前支持 statement_analysis；其他计算核心尚在实现')
    with localcontext() as ctx:
        ctx.prec = 40
        report, records = statement_analysis(service, project_id, **options)
        return publish(service, project_id, kind, report, records)

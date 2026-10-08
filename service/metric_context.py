"""Resolve homonymous financial labels from the nearest source statement block."""
import re


def block_kind(text):
    text = re.sub(r'\s+', ' ', str(text)).strip().casefold()
    if re.search(r'other comprehensive (?:income|loss).*attributable|其他综合收益.*归属|其他綜合收益.*歸屬', text):
        return 'other_comprehensive'
    if re.search(r'(?:total )?comprehensive (?:income|loss).*attributable|综合收益.*归属|綜合收益.*歸屬', text):
        return 'comprehensive'
    if re.search(r'(?:profit|loss|income).*attributable|利润.*归属|利潤.*歸屬', text):
        return 'profit'
    if re.fullmatch(r'(?:total )?equity(?: attributable to)?[:：]?|权益|權益|所有者权益|股东权益|股東權益', text):
        return 'balance'
    if re.search(r'financial position|balance sheet|changes in equity|资产负债表|資產負債表|资产(?:及|和)?负债(?:状况|情况)|权益变动表|權益變動表', text):
        return 'balance'
    if re.search(r'(?:statement|statements) of .*comprehensive (?:income|loss)', text):
        return 'comprehensive_statement'
    if re.search(r'(?:statement|statements) of (?:profit or loss|income)(?!.*comprehensive)|利润表|利潤表', text):
        return 'profit'
    return None


def source_metric_context(table, row, context=None):
    """Local attribution headings take precedence over a broad page title.

    Stop inheritance at the next explicit, unrelated table-block heading. An
    income-statement tag alone cannot distinguish profit from comprehensive
    income. No model-assigned metric or statement tag supplies missing proof.
    """
    context = context or {}
    kind, evidence = None, None
    for line in context.get('text', '').splitlines():
        candidate = block_kind(line)
        if candidate:
            kind, evidence = candidate, {'text':line.strip(), 'source':'preceding_heading'}
        elif line.strip().endswith((':', '：')) or re.match(r'^\s*\d+(?:[、.．]\s*|\s+)[A-Za-z\u4e00-\u9fff]', line):
            kind, evidence = None, None
    if kind is None and context.get('statement') in {'balance', 'equity'}:
        kind, evidence = 'balance', {'source':'source_statement', 'statement':context['statement']}
    for i, cells in enumerate(table['rows'][:row - 1], 1):
        label = str(cells[0]).strip() if cells else ''
        candidate = block_kind(label)
        if candidate:
            kind, evidence = candidate, {'row':i, 'column':1, 'text':label, 'source':'table_block'}
        elif label.endswith((':', '：')) and not any(str(c).strip() for c in cells[1:]):
            kind, evidence = None, None
    return {'kind':kind, 'evidence':evidence}


def column_semantics(table, row, column, declared=None):
    """A category row cannot replace a gross, allowance, net or movement column.

    Read physical headings as well as the mapped label: old mappings sometimes
    omit the column label entirely. Comparative dates are the same measure;
    gross/allowance/net and movements are different measures.
    """
    from .cleaning_rules import mapping_headers
    headers = mapping_headers(table)
    physical = [str(cells[column - 1]).strip() for cells in headers
                if column <= len(cells) and str(cells[column - 1]).strip()]
    # Some mappings repeat the row's full metric as a column label. Its words
    # (e.g. cash flow "net") are not an independent column measure.
    from .standard_metrics import normalize_label
    row_labels = table['rows'][row - 1][:column - 1] if 1 <= row <= len(table['rows']) else []
    independent_declared = declared and all(normalize_label(declared) != normalize_label(c) for c in row_labels)
    labels = list(dict.fromkeys(physical + ([str(declared)] if independent_declared else [])))
    kinds = []
    patterns = {
        'allowance': r'跌价准备|減值準備|减值准备|坏账准备|壞賬準備|allowance|provision|impairment',
        'gross': r'账面余额|賬面餘額|账面原值|原值|gross(?: carrying| book)?',
        'net': r'账面价值|賬面價值|净额|淨額|net carrying|net book',
        'movement': r'增加|减少|增减|变动|變動|调整数|调整金额|影响金额|购买|购入|出售|售出|赎回|初始投资|计提|转回|核销|处置|重分类|不含|未包含|additions|disposals|increase|decrease|movement|change|purchases|reversal|write.off|charge',
        'ratio': r'%|％|比例|比重|占比|百分点|percentage|percent|ratio',
    }
    for label in labels:
        compact = re.sub(r'\s+', '', label).casefold()
        if re.fullmatch(r'\(?inmillions?,exceptpercentages\)?', compact):
            continue
        kinds.extend(kind for kind, pattern in patterns.items()
                     if re.search(pattern.replace(' ', r'\s*'), compact, re.I))
    unknown = [label for label in physical if not period_only_column(label)]
    if not physical:
        # Misaligned/merged headers cannot lend a different measure to an
        # empty heading cell. Preserve the mapped ID instead of guessing the
        # nearest period, movement or profit-impact heading.
        measure_headers = [str(c) for cells in headers for c in cells[1:]
                           if any(re.search(pattern.replace(' ', r'\s*'), re.sub(r'\s+','',str(c)), re.I)
                                  for pattern in patterns.values())]
        unknown.extend(measure_headers)
    return {'labels':labels, 'physical_headers':physical, 'measure_kinds':sorted(set(kinds)),
            'unresolved_headers':unknown, 'row_metric_safe':not kinds and not unknown}


def period_only_column(label):
    """Only explicit comparative periods/units/scope are measure-neutral."""
    text = re.sub(r'\s+', '', str(label)).casefold()
    text = re.sub(r'\d+|[\W_]', '', text)
    words = (r'期初|期末|年初|年末|本期|上期|本年|上年|当期|同期|末|初|本报告期|报告期|年初至报告期末|年度|年|月|日|数|金额|余额|发生额|合并|母公司|调整前|调整后|重述前|重述后|'
             r'人民币|币种|单位|百万元|千元|万元|亿元|元|'
             r'january|february|march|april|may|june|july|august|september|october|november|december|'
             r'inmillions?exceptpercentages|rmb|cny|hkd|usd|million|thousand|currency|unaudited|audited|restated|original|'
             r'forthe|sixmonthsended|ninemonthsended|threemonthsended|yearended|asat|asof|currentperiod|priorperiod|previousperiod|'
             r'currentyear|prioryear|previousyear|thisperiod|lastperiod|amount|balance|consolidated|parent|fy|h|q|m')
    return not re.sub(words, '', text)

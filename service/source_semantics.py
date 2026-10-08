"""Resolve stock dates and quarterly scope from the table's source evidence."""
import calendar
import re

from .normalization import compact, unit_kind
from .source_periods import column_period, report_month
from .standard_metrics import normalize_label


VERSION = 'source-period-scope-1'


def quarterly_scope(table, context):
    headers = ' '.join(str(c) for row in table['rows'][:2] for c in row)
    if not re.search(r'第?[一二三四1234]季度', compact(headers)):
        return None
    text = context['text'] + '\n' + headers
    headings = [line for line in text.splitlines()
                if re.search(r'(?:分季度|季度).*(?:财务|会计)数据', compact(line))]
    if not headings:
        return None
    heading = compact(headings[-1])
    if '母公司' in heading:
        return {'scope': 'parent', 'quote': headings[-1]}
    if '合并' in heading:
        return {'scope': 'consolidated', 'quote': headings[-1]}
    # Attributable profit/equity names the group reporting perspective even
    # before the first consolidated statement appears later in the report.
    for row in table['rows']:
        label = compact(row[0]) if row else ''
        if re.search(r'归属于(?:上市公司股东|母公司(?:股东|所有者)).*(?:净利润|净资产|权益)', label):
            return {'scope': 'consolidated', 'quote': headings[-1] + '\n' + str(row[0])}
    return None


def apply_source_semantics(parsed, table, facts, context):
    from .cleaning_rules import mapping_headers, source_year
    scope = quarterly_scope(table, context)
    headers = mapping_headers(table)
    report_end = report_month(parsed)
    year = source_year(parsed)
    for fact in facts:
        ref = fact['source']; meta = ref['normalization']
        row = table['rows'][ref['row'] - 1]
        label = normalize_label(row[0]) if row else ''
        evidence = {}
        if scope:
            updated = re.sub(r'^(?:unspecified|parent|consolidated)(?=_|$)', scope['scope'], fact['scope'])
            if updated != fact['scope']:
                fact['scope'] = updated
                evidence['scope'] = scope
        # Cash-flow addbacks, changes and ratios keep their duration. A mixed
        # segment table's total assets/liabilities are stocks, unlike revenue.
        column = ref['column']
        header = ' '.join(str(r[column-1]) for r in headers if len(r) >= column)
        endpoint = r'(?:期末|年末|期初|年初)(?:余额|账面价值)'
        stock = context['statement'] == 'balance' or bool(re.search(endpoint, compact(header))) or bool(re.fullmatch(
            r'(?:分部)?(?:资产|负债)(?:总额|总计|合计)|总资产|总负债|' + endpoint, label))
        change = re.search(r'增减|增长|增加|减少|变动|变更|调整金额|差额', label + compact(header))
        period = fact['period']
        if stock and not change and unit_kind(fact['currency']) == 'money' and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', period):
            period_label = header
            if re.fullmatch(r'(?:期初|年初)(?:余额|账面价值)', label) and re.fullmatch(r'\d{4}-FY', period):
                period_label = f'{int(period[:4])-1}年12月31日'
            source = column_period(period_label, context['text'], 'balance', report_end, year)
            point = source['period']
            if point == 'unknown' and report_end and re.fullmatch(r'\d{4}-(?:FY|H[12]|9M|Q[1-4])', period):
                # Segment columns identify businesses, so the already resolved
                # comparative year combines with this report's closing date.
                end = {'H1': 6, 'H2': 12, '9M': 9, 'Q1': 3, 'Q2': 6, 'Q3': 9, 'Q4': 12}.get(period[5:], report_end)
                point = f'{period[:4]}-{end:02d}-{calendar.monthrange(int(period[:4]), end)[1]}'
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', point):
                fact['period'] = point; fact['year'] = int(point[:4])
                meta['period_start'] = point; meta['period_end'] = point
                evidence['period'] = {'kind': 'instant', 'row_label': str(row[0]), 'column_header': header,
                                      'report_end_month': report_end, 'previous_period': period}
        if evidence:
            meta.setdefault('source_semantics', {}).update(evidence)
            meta['source_semantics']['version'] = VERSION

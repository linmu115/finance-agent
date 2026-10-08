"""Shared sandbox wording and deterministic checks of explicit signed changes."""
import csv
from decimal import Decimal, InvalidOperation
import io
import re
import unicodedata


def _number(value):
    text = unicodedata.normalize('NFKC', str(value)).strip().replace(',', '').replace('−', '-')
    text = re.sub(r'^([+-])\s+', r'\1', text)
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f'变化量不是数字：{value!r}') from None
    if not number.is_finite():
        raise ValueError('变化量须为有限数值')
    return number


def _absolute(number):
    text = format(abs(number), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def fmt_change(delta, unit, pct=None):
    """Signed delta -> 增加/减少 + absolute magnitude. pct uses percent, e.g. -5 = -5%."""
    value = _number(delta)
    percent = None if pct is None else _number(pct)
    if percent is not None and percent != 0 and (value == 0 or (value < 0) != (percent < 0)):
        raise ValueError('变化量与百分比方向不一致，不能生成确定方向的表述')
    if value == 0:
        return '持平'
    return ('增加 ' if value > 0 else '减少 ') + _absolute(value) + str(unit) + (
        '（' + _absolute(percent) + '%）' if percent is not None else '')


_WORDS = r'同比增长|同比增加|同比减少|同比下降|增长|增加|上升|提升|减少|下降|降低|下滑|\bincreas(?:e[ds]?|ing)\b|\brose\b|\brise[sn]?\b|\bgrew\b|\bdecreas(?:e[ds]?|ing)\b|\bdeclin(?:e[ds]?|ing)\b|\bfell\b|\bfall(?:en|ing)?\b'
_NUM = r'(?:\d[\d,]*(?:\.\d+)?|\.\d+)'
_UNIT = r'(?:个百分点|百分点|亿元|百万元|万元|元|%|percentage\s+points?|pp|billion|million)?'
_SIGNED = rf'(?:[−-]\s*{_NUM}|\(\s*[−-]?\s*{_NUM}\s*{_UNIT}\s*\)|\+\s*{_NUM})'
_CHANGE = re.compile(rf'(?P<word>{_WORDS})(?:\s|\*|_)*(?:了|约|:|by\s+)?\s*(?P<number>{_SIGNED})\s*{_UNIT}', re.I)
_DOWN = re.compile(r'减少|下降|降低|下滑|decreas|declin|fell|fall', re.I)
_VALUE = rf'[+−-]?\s*{_NUM}'
_ORDER_UNIT = r'(?:人民币\s*)?(?:个百分点|百分点|百万元|亿元|万元|元|%|percentage\s+points?|pp|billion|million)'
_FIRST = rf'(?P<first>{_VALUE})\s*(?P<first_unit>{_ORDER_UNIT})?\s*'
_LAST = rf'(?P<last>{_VALUE})\s*(?P<last_unit>{_ORDER_UNIT})?'
_ORDERS = [
    re.compile(rf'(?:由|从)\s*{_FIRST}(?P<word>下降|降低|减少|增长|增加|上升|提高|提升|降|减|增|升)(?:至|到|为)\s*{_LAST}', re.I),
    re.compile(rf'(?P<word>{_WORDS})\s+from\s+{_FIRST}to\s+{_LAST}', re.I),
    re.compile(rf'from\s+{_FIRST}(?P<word>{_WORDS})\s+to\s+{_LAST}', re.I),
]
_RELATION = re.compile(r'方向相反|反向|方向不同|同方向|同向|\bopposite(?:\s+directions?)?\b|\bsame\s+direction\b', re.I)
_DELTA = re.compile(rf'(?<![A-Za-z0-9_.])(?P<value>[+−-]\s*{_NUM})(?![\d.])')


def _ordered_values(match):
    units=[(match[k] or '').replace('人民币','').strip().lower() for k in ('first_unit','last_unit')]
    if not units[0]:units[0]=units[1]
    if not units[1]:units[1]=units[0]
    scales={'元':1,'万元':10000,'百万元':1000000,'亿元':100000000,'million':1000000,'billion':1000000000}
    if units[0]!=units[1] and not all(u in scales for u in units):return None
    return [_number(match[key])*scales.get(unit,1) for key,unit in zip(('first','last'),units)]


def _relation_issues(line, source, line_number, table_row=False):
    issues=[]
    # A table row is one assertion scope; prose is bounded by sentence punctuation.
    for sentence in [line] if table_row else re.split(r'[。！？!?；;]|(?<!\d)\.(?!\d)',line):
        matches=list(_RELATION.finditer(sentence))
        if not matches:continue
        values=[_number(m['value']) for m in _DELTA.finditer(sentence)]
        for match in matches:
            item={'kind':'direction_relation','source':source,'line':line_number,'text':sentence.strip(),'assertion':match[0]}
            if len(values)!=2 or any(v==0 for v in values):
                if not any(i.get('severity')=='notice' for i in issues):
                    issues.append({**item,'severity':'notice','message':'关系方向断言需核对：本句或表行未能唯一解析出两个非零带符号变化值。'})
                continue
            opposite=bool(re.search(r'相反|反向|不同|opposite',match[0],re.I))
            negated=bool(re.search(r'(?:并非|不是|不|\bnot(?:\s+in)?)\s*$',sentence[:match.start()],re.I))
            if negated:opposite=not opposite
            actual_opposite=(values[0]<0)!=(values[1]<0)
            if actual_opposite!=opposite:
                issues.append({**item,'message':'关系方向断言与两个带符号变化值矛盾：'+('实际方向相反。' if actual_opposite else '实际同向。')})
    return issues


def _contradiction(word, raw):
    parenthesized = raw.strip().startswith('(')
    number = _number(re.search(rf'[−+\-]?\s*{_NUM}', raw)[0])
    if number == 0:
        return False
    # A decrease is described with an absolute magnitude too; a signed delta belongs
    # under neutral labels such as 变化/增减额. Rates labelled 增长率 may be negative.
    return parenthesized or number < 0 or bool(_DOWN.search(word)) and raw.strip().startswith('+')


def direction_issues(text, source='回答', csv_text=False, table_row=False):
    normalized = unicodedata.normalize('NFKC', text)
    # Code examples are not asserted changes; keep line offsets for diagnostics.
    normalized = re.sub(r'```[\s\S]*?```|`[^`\n]*`', lambda m: re.sub(r'[^\n]', ' ', m[0]), normalized)
    issues = []
    lines=list(enumerate(normalized.splitlines(),1)) if not csv_text else []
    if csv_text:
        reader=csv.reader(io.StringIO(normalized))
        for row in reader:lines.append((reader.line_num,' | '.join(row)))
    for line_number, line in lines:
        for match in _CHANGE.finditer(line):
            if _contradiction(match['word'], match['number']):
                issues.append({'kind': 'direction', 'source': source, 'line': line_number,
                               'text': match[0], 'message': '方向词后应为绝对变化量；请核对符号或改用“变化/增减额”标签'})
        plain=line.replace('**','').replace('__','')
        for pattern in _ORDERS:
            for match in pattern.finditer(plain):
                values=_ordered_values(match)
                if values is None:continue
                first,last=values
                down=bool(re.search(r'降|减|decreas|declin|fell|fall',match['word'],re.I))
                if not (first>last if down else first<last):
                    issues.append({'kind':'direction_order','source':source,'line':line_number,'text':match[0],
                        'message':'期间顺序与方向词矛盾：下降要求起值大于终值，上升要求起值小于终值。'})
        issues.extend(_relation_issues(plain,source,line_number,table_row or csv_text or line.strip().startswith('|')))
    if csv_text:
        reader = csv.reader(io.StringIO(normalized))
        header = next(reader, [])
        directional = [(i, h) for i, h in enumerate(header) if re.fullmatch(rf'\s*(?:{_WORDS})\s*(?:\([^)]*\))?\s*', h, re.I)]
        for row in reader:
            for i, heading in directional:
                if i < len(row) and re.fullmatch(rf'{_SIGNED}\s*{_UNIT}', row[i].strip()) and _contradiction(heading, row[i]):
                    issues.append({'kind': 'direction', 'source': source, 'line': reader.line_num,
                                   'text': heading + ': ' + row[i], 'message': '方向列含带符号变化量；请核对标签与数值'})
    return issues


def xlsx_direction_issues(path, source=None):
    """Inspect string cells and same-row relation assertions; never recalculate/edit."""
    from openpyxl import load_workbook
    workbook=load_workbook(path,read_only=True,data_only=False)
    issues=[]
    try:
        for sheet in workbook:
            for row in sheet:
                strings=[c for c in row if isinstance(c.value,str) and c.data_type!='f']
                row_text=' | '.join(c.value for c in strings)
                for cell in strings:
                    location={'source':source or str(path),'sheet':sheet.title,'cell':cell.coordinate,'line':cell.row}
                    found=[i for i in direction_issues(cell.value,location['source']) if i['kind']!='direction_relation']
                    issues.extend({**i,**location} for i in found)
                if strings:
                    relations=_relation_issues(unicodedata.normalize('NFKC',row_text),source or str(path),strings[0].row,True)
                    for issue in relations:
                        cell=next(c for c in strings if issue['assertion'] in unicodedata.normalize('NFKC',c.value))
                        issues.append({**issue,'sheet':sheet.title,'cell':cell.coordinate})
    finally:workbook.close()
    return issues

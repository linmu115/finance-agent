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


def _contradiction(word, raw):
    parenthesized = raw.strip().startswith('(')
    number = _number(re.search(rf'[−+\-]?\s*{_NUM}', raw)[0])
    if number == 0:
        return False
    # A decrease is described with an absolute magnitude too; a signed delta belongs
    # under neutral labels such as 变化/增减额. Rates labelled 增长率 may be negative.
    return parenthesized or number < 0 or bool(_DOWN.search(word)) and raw.strip().startswith('+')


def direction_issues(text, source='回答', csv_text=False):
    normalized = unicodedata.normalize('NFKC', text)
    # Code examples are not asserted changes; keep line offsets for diagnostics.
    normalized = re.sub(r'```[\s\S]*?```|`[^`\n]*`', lambda m: re.sub(r'[^\n]', ' ', m[0]), normalized)
    issues = []
    for line_number, line in enumerate(normalized.splitlines(), 1):
        for match in _CHANGE.finditer(line):
            if _contradiction(match['word'], match['number']):
                issues.append({'kind': 'direction', 'source': source, 'line': line_number,
                               'text': match[0], 'message': '方向词后应为绝对变化量；请核对符号或改用“变化/增减额”标签'})
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

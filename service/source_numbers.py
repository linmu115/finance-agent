"""Numeric data in source cells, including amounts embedded in prose."""
import re
from .normalization import decimal_value


def data_number(raw):
    text=str(raw).strip()
    value=decimal_value(text)
    if value is not None:
        return not (1900<=value<=2100 and value==int(value))
    # Dates and period headings are not amounts. Monetary literals retain
    # their currency and thousands separators in bond/payment prose (t87).
    return bool(re.search(r'\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:美元|港元|人民币|亿元|万元|元|股)',text))

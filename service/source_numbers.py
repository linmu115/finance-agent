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
    return bool(re.search(r'\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:美元|港元|人民币|亿元|万元|元|股|吨|人|户|台|件|千克|公斤|平方米|mg\b|kg\b|kWh\b)',text,re.I)
                or re.search(r'(?<!\d)\d+\.\d+\s*[A-Za-zμ㎡³]',text))


IDENTIFIER = re.compile(r'证券代码|股票代码|统一社会信用代码|组织机构代码|注册号|邮政编码|邮编|电话|传真|页码|序号|编号|日期|^年份$|^年度$|\b(?:postal.?code|stock.?code|ticker|telephone|fax|date|year|page)\b|^no\.?$',re.I)
DATE = re.compile(r'(?:19|20)\d{2}\s*[-/.年]\s*\d{1,2}(?:\s*[-/.月]\s*\d{1,2}\s*日?)?\s*月?')
MONEY = re.compile(r'(?:RMB|HK\$|CNY|人民币)\s*\d|\d[\d,.，]*\s*(?:美元|港元|人民币|亿元|万元|元|股|%|％)',re.I)


def identifier_reason(table, row, column):
    """One-based source coordinates. Labels apply to their value, not the whole row."""
    cells=table['rows'];raw=str(cells[row-1][column-1]).strip()
    if MONEY.search(raw):return None  # A dated interest payment still has an amount.
    if DATE.fullmatch(raw):return 'date'
    value=decimal_value(raw)
    if value is not None and 1900<=value<=2100 and value==int(value):return 'year'
    # Key/value company tables can have several pairs in one row. The closest
    # left-hand label and the aligned column heading identify each value.
    labels=[]
    if column>1:labels.append(str(cells[row-1][column-2]).strip())
    labels.extend(str(r[column-1]).strip() for r in reversed(cells[:min(row-1,5)]) if len(r)>=column)
    label=next((s for s in labels if len(s)<35 and IDENTIFIER.search(s)),None)
    if label and re.fullmatch(r'[\dA-Za-z\s()+\-./、]+',raw):return label
    return None


def numeric_cells(table):
    return [{'row':r,'column':c,'raw_value':raw} for r,row in enumerate(table['rows'],1)
            for c,raw in enumerate(row,1) if data_number(raw) and not identifier_reason(table,r,c)]


def identifier_table_exclusion(table):
    """Only positively identified identifier-only tables get a program exclusion."""
    if numeric_cells(table):return None
    identifiers=[{'row':r,'column':c,'raw_value':raw,'reason':reason}
                 for r,row in enumerate(table['rows'],1) for c,raw in enumerate(row,1)
                 if re.search(r'\d',str(raw)) and (reason:=identifier_reason(table,r,c))]
    if not identifiers:return None
    # Dates alone can be the remaining header of a badly parsed financial table.
    if all(i['reason'] in {'date','year','序号','编号','页码'} for i in identifiers):return None
    if any(re.search(r'利润表|资产负债表|现金流量表|每股|比率|收入|余额',str(c)) for row in table['rows'] for c in row):return None
    return {'reason':'identifier_only_table','cells':identifiers}

"""Exact numeric operations and legacy aliases; semantic mapping lives in semantic.py."""
from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation

METRICS = {
    "revenue": ["营业收入", "revenue", "revenues", "net sales"],
    "net_profit_parent": ["归属于上市公司股东的净利润", "归属于母公司所有者的净利润", "归属于母公司股东的净利润", "归母净利润"],
    "net_profit": ["净利润", "net income"],
    "operating_cash_flow": ["经营活动产生的现金流量净额", "经营现金流净额", "经营现金流", "net cash provided by operating activities"],
    "assets": ["总资产", "资产总计", "total assets"],
    "equity_parent": ["归属于上市公司股东的净资产", "归属于母公司所有者权益合计", "归属于母公司股东权益合计", "归属于母公司所有者权益", "归母净资产"],
    "liabilities": ["负债合计", "负债总计", "total liabilities"],
    "cost_of_revenue": ["营业成本", "cost of revenue", "cost of sales"],
    "gross_profit": ["毛利润", "毛利", "gross profit"],
    "net_profit_excluding_nonrecurring": ["归属于上市公司股东的扣除非经常性损益的净利润", "扣非归母净利润"],
    "eps": ["基本每股收益", "basic earnings per share"],
    "roe": ["加权平均净资产收益率", "return on equity"],
}
ALIASES = {"profit_parent":"net_profit_parent", "cash_flow_operating":"operating_cash_flow", "ocf":"operating_cash_flow", "net_profit_attributable":"net_profit_parent"}
BALANCE_METRICS = {"assets", "equity_parent", "liabilities"}
UNIT_FACTORS = {"亿元": Decimal("100000000"), "万元": Decimal("10000"), "千元": Decimal("1000"), "元": Decimal(1),
                "billion": Decimal("1000000000"), "million": Decimal("1000000"), "thousand": Decimal("1000")}

def compact(value):
    return re.sub(r"\s+", "", str(value or "")).replace("／", "/").replace("（", "(").replace("）", ")")

def metric_id(label):
    norm = compact(label).lower()
    if norm in METRICS:
        return norm
    if norm in ALIASES:
        return ALIASES[norm]
    # Longest aliases first: do not confuse reported net profit with non-recurring-adjusted profit.
    for alias, key in sorted(((a, k) for k, names in METRICS.items() for a in names), key=lambda x:len(x[0]), reverse=True):
        base = compact(alias).lower()
        if norm == base or norm.startswith(base + "("):
            return key
    return None

def decimal_value(value):
    text = compact(value).replace(",", "").replace("，", "").replace("−", "-").replace("﹣", "-").replace("％", "%")
    if not text or text in {"-", "—", "--", "/", "不适用", "N/A", "None", "nan"}:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = text.rstrip("%")
    text = re.sub(r"^(人民币|RMB|CNY|USD|HKD|￥|¥|\$)", "", text, flags=re.I)
    text = re.sub(r"(亿元|万元|千元|元)$", "", text)
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        return None
    try:
        number = Decimal(text)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None

def unit_info(text, metric=None):
    label = compact(text).lower()
    if label in {"年","year","years"}:return str(text).strip(),Decimal(1),"years"
    if label in {"个百分点","百分点","percentagepoint","percentagepoints","percentage_points","pp","p.p."}:
        return str(text).strip(),Decimal(1),"percentage_points"
    if metric == "roe" or "%" in label or "百分比" in label:
        return "%", Decimal(1), "percent"
    share_basis=re.search(r"/(\d+(?:\.\d+)?)股",label)
    if share_basis:
        currency = "USD" if "美元" in label or "usd" in label else "HKD" if "港元" in label or "hkd" in label else "EUR" if "欧元" in label or "eur" in label else "CNY"
        return str(text).strip(),Decimal(1),currency+"/"+share_basis[1]+"shares"
    if metric == "eps" or "/股" in label or "/share" in label:
        currency = "USD" if "美元" in label or "usd" in label else "HKD" if "港元" in label or "hkd" in label else "EUR" if "欧元" in label or "eur" in label else "CNY"
        return str(text).strip() or "元/股", Decimal(1), currency+"/share"
    # Parse magnitude independently of currency: 百万元 is not 万元, 千港元 is not 元.
    currencies = [("HKD", ("港元", "港币", "hkd", "hk$")), ("USD", ("美元", "美金", "usd", "us$")),
                  ("EUR", ("欧元", "eur", "€")), ("JPY", ("日元", "jpy")),
                  ("CNY", ("人民币", "cny", "rmb", "元", "￥", "¥"))]
    currency = next((code for code, names in currencies if any(n in label for n in names)), "unknown")
    if currency == "unknown" and "$" in label: currency = "USD"
    if currency == "unknown":
        currency = next((unit for unit in ("shares","count","股","人","吨","台","倍","个","次","ratio") if unit in label), "unknown")
    for unit, factor in [("billion", "1000000000"), ("million", "1000000"), ("thousand", "1000"),
                        ("十亿", "1000000000"), ("亿", "100000000"), ("千万", "10000000"),
                        ("百万", "1000000"), ("十万", "100000"), ("万", "10000"), ("千", "1000")]:
        if unit in label:
            return str(text).strip(), Decimal(factor), currency
    if currency != "unknown": return str(text).strip(), Decimal(1), currency
    if label in {"%", "percent", "percentage"}: return "%", Decimal(1), "percent"
    if label in {"股", "人", "吨", "台", "倍", "个", "次", "ratio", "shares", "count"}:
        return str(text).strip(), Decimal(1), label
    return None, None, "unknown"


def unit_kind(unit):
    """Numerical dimension, independent of a financial indicator's label."""
    if unit in {"percent","%","％"}:return "ratio_percent"
    if unit in {"percentage_points","个百分点","百分点"}:return "percentage_points"
    if re.fullmatch(r"[A-Z]{3}",str(unit)):return "money"
    if re.fullmatch(r"[A-Z]{3}/(?:\d+(?:\.\d+)?)?shares?",str(unit)):return "money_per_share_basis"
    return str(unit or "unknown")


def numeric_candidate(value):
    """Surface number shapes only; the model decides whether they are data.

    Textual decimal quantities and percent/point expressions need a model
    span. A bare year heading does not become a guessed financial value.
    """
    text=str(value or "")
    return decimal_value(text) is not None or bool(re.search(r"\d+[.,]\d+",text) or
        (re.search(r"\d",text) and re.search(r"[%％]|百分点|percentage\s*points?|\bpct\b|\bp\.p\.",text,re.I)))

def period_for(year, metric):
    return f"{year}-12-31" if metric in BALANCE_METRICS else f"{year}-FY"

def tokens(text):
    # Deterministic Chinese overlapping bigrams plus latin terms, avoiding a large dictionary dependency.
    lowered = str(text).lower()
    terms = re.findall(r"[a-z0-9_]+", lowered)
    for word in re.findall(r"[\u4e00-\u9fff]+", lowered):
        terms.extend(word[i:i+2] for i in range(max(1, len(word)-1)))
    return " ".join(terms)

def number_text(value):
    return format(value, "f")

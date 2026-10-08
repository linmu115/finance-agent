"""Period-change explanations, quoted from the selected report, without an LLM.

These are retrieval candidates, not causal estimates. Numbers in a headline do
not turn the explanation following it into a quantified contribution.
"""
import json
import re

from .financial_workpapers import col, table
from .workpaper_annual import compact


DRIVER_TERMS = {
    'revenue_effect': r'营业(?:总)?收入|主营业务收入|revenue',
    'margin_effect': r'营业成本|主营业务成本|毛利率|gross profit|cost of sales',
    'selling': r'销售费用|selling expenses',
    'administrative': r'管理费用|administrative expenses',
    'research': r'研发费用|research and development expenses',
    'finance_costs': r'财务费用|finance costs|financing costs',
    'finance_net': r'财务费用|finance costs|finance income|financing costs',
    'interest_income': r'利息收入|interest income|finance income',
    'other_income': r'其他收益|其他收入|other income',
    'other_gains_net': r'其他.*?收益|other gains',
    'investment_income': r'投资收益|investment income',
    'asset_impairment': r'资产减值|商誉|goodwill|asset impairment',
    'credit_impairment': r'信用减值|保理风险准备|credit losses',
    'impairment': r'减值|credit losses|impairment',
    'fair_value_gains': r'公允价值|fair\s+value',
    'tax': r'所得税|income tax',
    'minority_profit': r'少数股东|non.controlling',
    'nonoperating_income': r'营业外收入', 'nonoperating_expenses': r'营业外支出',
    'asset_disposal': r'资产处置|disposal', 'surcharges': r'税金及附加',
    'other_operating_revenue': r'利息收入|interest income',
    'cfo': r'经营活动.*?现金|cash (?:used in|generated from|flows? from) operating|cash inflow from operations|cash conversion',
    'receivables': r'应收账款|经营性应收|trade(?: and other)? receivables|accounts receivable',
    'inventory': r'存货|库存量|inventor(?:y|ies)',
    'payables': r'应付账款|应付票据|经营性应付|trade (?:and bills )?payables',
    'prepayments': r'预付款|prepayments|prepaid',
    'other_receivables': r'其他应收款|other receivables',
    'contract_assets': r'合同资产|contract assets',
    'contract_liabilities': r'合同负债|预收.*?货款|contract liabilities|advance.*?customers',
    'other_payables': r'其他应付款|other payables',
    'taxes_payable': r'应交税费|tax(?:ation)? payable',
    'employee_benefits_payable': r'应付职工薪酬|employee benefits payable',
    'working_capital': r'营运(?:资本|资金)|working capital',
    'other_noncurrent': r'其他非流动资产|other non.current assets',
    'cash_balance': r'货币资金|现金及现金等价物|cash and cash equivalents',
    'debt': r'借款|应付债券|租赁负债|borrowings|lease liabilities|bonds payable',
    'nonrecurring': r'非经常性损益|投资收益|资产处置|政府补助|listing expenses|non.recurring|adjusted net profit',
    'quarter': r'第四季度|四季度|Q4|fourth quarter',
    'audit': r'审计意见|强调事项|会计师事务所|审计机构|auditor|audit opinion|emphasis of matter',
}
CAUSE = re.compile(
    r'变动原因|减少(?:主要)?原因|增加(?:主要)?原因|主要原因|主要是|主要因|所致|由于|导致|因(?=[^。；]{0,50}(?:增加|减少|下降|变动|影响))|'
    r'due to|because(?: of)?|attribut(?:able|ed) to|driven by|result(?:ed|ing) (?:in|from)|leading to|'
    r'in line with|contribut(?:ed|ing) to|main reason', re.I)
QUANTIFIED_CAUSE = re.compile(
    r'(?:增加|减少|影响|导致|贡献|支付|计提|确认|损失|收益)[^。；，,]{0,40}?[+-]?\d[\d,.]*\s*(?:亿元|万元|百万元|千元|元|个百分点|%|吨|件)|'
    r'(?:RMB|HK\$|US\$|USD|CNY)\s*[\d,.]+\s*(?:million|billion|thousand)|'
    r'\b[\d,.]+\s*(?:million|billion|percentage points|tonnes|units)\b', re.I)
STATUS = {'quantitative': '原文给出定量原因', 'qualitative': '原文只给定性原因', 'not_stated': '原文未说明'}


def mdna_pages(a):
    result = set(); active = False
    for page, text in sorted(a.d.pages.items()):
        if re.search(r'(?im)^\s*(?:Management Discussion and Analysis|Operating (?:and Financial )?Review|Financial Review)\s*$', text):
            result.add(page)
        for m in re.finditer(r'(?m)^\s*第[一二三四五六七八九十]+节\s*([^\n]+)', text):
            title = compact(m[1])
            if re.search(r'\.{3}|…{2}|[.．·]{3}', title): continue
            active = bool(re.search('管理层讨论|经营情况讨论|董事会报告', title))
        if active: result.add(page)
    return result


def parent_note_start(a):
    found = [p for p, text in a.d.pages.items() if re.search(r'(?m)^\s*(?:[一二三四五六七八九十]+[、.])?\s*母公司财务报表.{0,8}注释', text)]
    return min(found) if found else None


def normalized(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)


def passages(text):
    """Keep English causal follow-up sentences together; CJK ends at 。/；.

    A PDF's empty line is often just a Chinese line wrap, not a paragraph.
    """
    if re.search(r'[\u4e00-\u9fff]', text):
        return [m.group().strip() for m in re.finditer(r'[^。；]+[。；]?', text) if m.group().strip()]
    return [part.strip() for part in re.split(r'\n\s*\n', text) if part.strip()]


def _current_period_quote(a, text, period):
    # Comparative figures inside the current discussion do not explain the old
    # year's signal. Prior-year causes require an explicit temporal subject.
    if not period or not getattr(a, 'ps', None) or period == a.ps[0]: return True
    year = re.escape(period[:4])
    return bool(re.match(r'(?:在)?' + year + r'年|(?:In|During)\s+' + year + r'\b', normalized(text), re.I))


def quantified_cause(text):
    """Check a causal sentence, never unrelated later headline numbers."""
    for sentence in re.split(r'[。；]|\.(?!\d)(?=\s|$)', text):
        cause = CAUSE.search(sentence)
        if not cause: continue
        quantified = QUANTIFIED_CAUSE.search(sentence[cause.end():])
        if quantified: return quantified.group()
        # A separately quantified cause can precede the causal verb, e.g. a
        # stated tax payment that offset operating cash. Headline changes lack
        # this explicit component/contribution construction.
        if re.search(r'(?:tax payment|impairment charge|tariff costs?).*?(?:offset|contribut|reduced|increased)', sentence, re.I):
            quantified = QUANTIFIED_CAUSE.search(sentence)
            if quantified: return quantified.group()
    return None


def english_causal_subject(text, cause, terms, structural=False):
    before = text[:cause.start()]
    breaks = [m for m in re.finditer(r'\.(?!\d)\s+(?=[A-Z])', before)]
    starts = [0, *[m.end() for m in breaks]]
    start = starts[-1]; clause = before[start:]
    if not re.search(terms, clause, re.I) and re.match(r'(?:Such|This|These|The (?:main reason|increase|decrease))', clause, re.I) and len(starts) > 1:
        start = starts[-2]; clause = before[start:breaks[-1].start()]
    if not re.search(terms, clause, re.I): return None
    verb = re.search(r'\b(?:increased|decreased|declined|grew|was|were|amounted|remained|experienced)\b', clause, re.I)
    if not verb: return None  # Recognition policies are not period-change explanations.
    return start if structural or re.search(terms, clause[:verb.start()], re.I) else None


def find_explanations(a, key, label, period=None):
    terms = DRIVER_TERMS.get(key, re.escape(label).replace('_', r'\s+'))
    preferred = mdna_pages(a); parent = parent_note_start(a); candidates = []
    for page, text in sorted(a.d.pages.items()):
        if parent and page >= parent and getattr(a.st, 'scope', 'consolidated') == 'consolidated': continue
        for quote in passages(text):
            search = normalized(quote)
            if re.search(r'[\u4e00-\u9fff]', search): search = compact(quote)
            chinese = bool(re.search(r'[\u4e00-\u9fff]', search))
            causes = list(CAUSE.finditer(search))
            cause = next((c for c in causes if re.search(terms, search[:c.start()], re.I)
                          and (chinese or english_causal_subject(search, c, terms, key.startswith('contribution_')) is not None)), None)
            if not cause: continue
            # The metric is the subject before the causal clause, not a stray
            # word in its explanation (e.g. revenue in a tax explanation).
            subject = search[:cause.start()]
            if re.search(r'预计|预期将|可能|将会|\b(?:may|might|will|expect(?:ed)? to)\b', subject, re.I): continue
            matches = list(re.finditer(terms, subject, re.I))
            if not matches: continue
            if key.startswith('contribution_') and not re.search(r'(?:收入|revenue)', subject, re.I): continue
            strong_cause = cause.group().lower() != 'in line with'
            if not chinese:
                start = english_causal_subject(search, cause, terms, key.startswith('contribution_'))
                quote = a.source_text(page, search[start:])['quote']
                search = normalized(quote)
            if re.search(r'[\u4e00-\u9fff]', search):
                match = matches[-1]
                # A numeric table preceding a sentence cannot supply its subject.
                prose = '本期实现' in subject
                if not prose and (cause.start() - match.end() > 70 or re.search(r'\d[\d,]*\.\d+', subject[match.end():])): continue
                start = match.start()
                if prose:
                    # Keep the business category with its directly disclosed
                    # volume/price effects, not just the last monetary label.
                    raw_product = re.search(r'(?m)^\s*([^\n。；：:]{1,45}本期实现)', quote)
                    if raw_product:
                        product = compact(raw_product[1])
                        start = subject.find(product)
                # Preserve the whole noun phrase/list and original whitespace.
                enum = list(re.finditer(r'[（(]\d+[）)]', subject[:start]))
                if enum and start - enum[-1].end() < 40: start = enum[-1].start()
                quote = a.source_text(page, search[start:])['quote']
                offset = text.find(quote)
                if offset >= 0 and not prose:
                    line_start = text.rfind('\n', 0, offset) + 1
                    prefix = text[line_start:offset]
                    if len(prefix.strip()) <= 35 and not re.search(r'\d[\d,.]*\s', prefix):
                        quote = (prefix + quote).strip()
                search = compact(quote); cause = CAUSE.search(search)
            if re.search(r'□适用\s*√不适用|不适用。?$', quote): continue
            if not _current_period_quote(a, quote, period): continue
            if page not in preferred:
                period_change = re.search(r'(?:本期|本年|报告期).*(?:所致|导致)|变动原因|减少(?:主要)?原因|增加(?:主要)?原因', compact(quote))
                english_change = re.search(r'(?:increased|decreased|declined|grew).*(?:due to|because|attribut|driven)', normalized(quote), re.I)
                if not period_change and not english_change: continue
            # Quantify only the causal tail. A change's headline amount is not
            # a quantified tariff, deposit-mix or seasonality contribution.
            quantified = quantified_cause(search)
            ref = a.source_text(page, quote, section='管理层讨论与分析' if page in preferred else '财务附注/其他原文',
                                disclosure_status='quantitative' if quantified else 'qualitative',
                                evidence_role='management_explanation_candidate')
            if quantified: ref['quantified_cause_excerpt'] = quantified
            candidates.append((page not in preferred, not strong_cause, page, ref))
    # Repeated identical explanations need only one quote; different causes and
    # different business scopes remain available, with no arbitrary top-one cut.
    found = {}; result = []
    for _, _, page, ref in sorted(candidates, key=lambda x: x[:3]):
        signature = re.sub(r'^\(\d+\)', '', compact(ref['quote'])).lower()
        if signature in found:
            found[signature].setdefault('corroborating_pages', []).append(page)
        else:
            found[signature] = ref; result.append(ref)
    return result


def driver_evidence(a, key, label, quantity_ref=None, period=None, query_keys=None):
    period = period or a.ps[0]
    refs = []
    for topic in query_keys or [key]:
        for ref in find_explanations(a, topic, label, period):
            if not any((r['page'], r['quote']) == (ref['page'], ref['quote']) for r in refs):
                refs.append({**ref, 'matched_topic': topic,
                             'relation': 'direct_driver' if topic == key else 'related_driver'})
    state = 'quantitative' if any(r['disclosure_status'] == 'quantitative' for r in refs) else 'qualitative' if refs else 'not_stated'
    pages = sorted(a.d.pages); preferred = sorted(mdna_pages(a))
    return {'key': key, 'driver': label, 'period': period, 'quantity_ref': quantity_ref,
            'disclosure_status': state, 'status': STATUS[state], 'evidence': refs,
            'quantitative_limit': ('仅原句中的局部原因得到量化，不代表完整解释全部变化；算术桥不证明经济因果' if state == 'quantitative' else
                                   '原因已披露，但未披露该原因的独立贡献金额；算术桥不等于原因的定量归因' if refs else
                                   '在本报告已解析、适用期间的原文中未检出明确原因；不据此认定所有材料均未披露'),
            'alignment_note': '关联驱动的解释不等于原文已直接解释该信号或阈值；保留原句的业务范围，不把全年原因自动归给单季',
            'search': {'searched_pages': pages, 'preferred_pages': preferred,
                       'missing_pages': [p for p in range(1, max(pages, default=0) + 1) if p not in a.d.pages or not a.d.pages[p].strip()],
                       'note': '优先管理层讨论，再检索明确说明期间变动的附注；候选原句需按范围理解，未命中不证明其他材料未披露'}}


def evidence_table(items):
    columns = {k: col(v) for k, v in [('key', '行键'), ('driver', '变动项/信号'), ('period', '解释适用期间'),
        ('status', '披露状态'), ('disclosure_status', '披露状态代码'), ('quote', '管理层原句（候选）'),
        ('pages', 'PDF页'), ('quantitative_limit', '量化边界'), ('source', '结构化来源'), ('quantity_ref', '对应数值位置')]}
    return table(columns, [{'key': r['key'], 'driver': r['driver'], 'period': r['period'], 'status': r['status'],
                           'disclosure_status': r['disclosure_status'], 'quote': '\n\n'.join(x['quote'] for x in r['evidence']) or '原文未说明',
                           'pages': ', '.join(str(p) for p in sorted({x['page'] for x in r['evidence']})),
                           'quantitative_limit': r['quantitative_limit'], 'source': json.dumps(r['evidence'], ensure_ascii=False),
                           'quantity_ref': json.dumps(r['quantity_ref'], ensure_ascii=False)} for r in items], '管理层解释对齐')

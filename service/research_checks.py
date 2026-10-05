"""Non-blocking financial consistency checks over source-derived observations."""
from decimal import Decimal, InvalidOperation
import re


def valuation_warnings(facts):
    """A reported forward PE should be reconcilable to its price and EPS.

    This is a review prompt, not an instruction to replace any reported value:
    dates, adjustments and EPS definitions may legitimately differ.
    """
    prices={};earnings={};multiples={};warnings=[]
    for fact in facts:
        meta=fact['source']['normalization'];kind=meta.get('data_kind')
        if kind in {None,'disclosed_actual','unclassified'}:continue
        if re.search(r'\b\d{3,6}\s*\.\s*HK\b',fact['source'].get('text',''),re.I) and fact['currency'].startswith('CNY') and not re.search(r'人民币|CNY|RMB',fact['raw_unit'],re.I):
            ref=fact['source'];reason='cross_market_currency_requires_confirmation'
            warnings.append({'table':int(ref['table_id'].rsplit(':t',1)[1]),'row':ref['row'],'column':ref['column'],'reason':reason,'severity':'review',
                             'instruction':'港股行的元未明确是哪种货币。核对股价、EPS与市值各自的币种，不能整行一概套人民币；无明确证据时设 currency=unknown 并保留原值。'})
            meta.setdefault('review_warnings',[]).append(reason)
        metric=fact['metric'].removesuffix('_forecast')
        base=(fact['company'],fact['scope'],meta.get('scenario','unspecified'))
        if metric in {'close_price','last_close_price','stock_price','share_price','closing_price'} and kind=='quoted_actual' and fact['currency'].endswith('/share'):
            prices.setdefault(base,[]).append(fact)
        elif metric in {'eps','eps_basic','basic_eps','earnings_per_share'} and fact['currency'].endswith('/share'):
            earnings.setdefault(base+(fact['period'],kind),[]).append(fact)
        elif metric in {'pe','pe_ratio','price_earnings'} and fact['currency'] in {'倍','ratio','times'}:
            multiples.setdefault(base+(fact['period'],kind),[]).append(fact)
    for key,ratios in multiples.items():
        candidates=prices.get(key[:3],[]);eps=earnings.get(key,[])
        if len(candidates)!=1 or len(eps)!=1 or len(ratios)!=1:continue
        price,profit,multiple=candidates[0],eps[0],ratios[0]
        if price['currency']!=profit['currency']:continue
        try:
            p,e,pe=map(Decimal,(price['value'],profit['value'],multiple['value']))
            if min(p,e,pe)<=0:continue
            implied=p/e
            # Leave normal displayed rounding alone. A large difference is
            # useful to surface even when it originated in the published PDF.
            if abs(implied-pe)<=max(Decimal('0.2'),abs(pe)*Decimal('0.02')):continue
        except (InvalidOperation,ZeroDivisionError):continue
        ref=multiple['source'];reason='price_eps_pe_requires_reconciliation'
        warning={'table':int(ref['table_id'].rsplit(':t',1)[1]),'row':ref['row'],'column':ref['column'],
                 'reason':reason,'severity':'review','company':multiple['company'],'period':multiple['period'],
                 'reported_pe':str(pe),'price_div_eps':format(implied,'.2f'),
                 'source_cells':[f['source']['cell'] for f in (price,profit,multiple)],
                 'instruction':'原文股价÷EPS与所列PE差异较大。保留原值，核对估值基准日、复权、EPS口径及原报告可能错位；不要用计算值覆盖原文。'}
        warnings.append(warning)
        for f in (price,profit,multiple):
            f['source']['normalization'].setdefault('review_warnings',[]).append(reason)
    return warnings

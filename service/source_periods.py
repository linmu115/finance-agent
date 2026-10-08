"""Resolve periods from report/column evidence, never an annual default."""
import calendar
import re
from .normalization import compact


def report_month(parsed):
    for page in parsed['pages']:
        text=compact(page['text'])
        match=re.search(r'(?:19|20)\d{2}年((?:第?[一三13]季度|半年度|中期|年度)报告)|INTERIMREPORT|ANNUALREPORT',text,re.I)
        if match:
            title=match.group().casefold()
            if re.search(r'[一1]季度',title):return 3
            if re.search(r'[三3]季度',title):return 9
            if re.search(r'半年度|中期|interim',title):return 6
            return 12
    return None


def flow_period(year, start_month, end_month):
    suffix={(1,3):'Q1',(4,6):'Q2',(7,9):'Q3',(10,12):'Q4',
            (1,6):'H1',(7,12):'H2',(1,9):'9M',(1,12):'FY'}.get((start_month,end_month))
    if not suffix:return {'period':'unknown'}
    return {'period':f'{year}-{suffix}','start':f'{year}-{start_month:02d}-01',
            'end':f'{year}-{end_month:02d}-{calendar.monthrange(year,end_month)[1]}'}


def column_period(text, context, statement, report_end, report_year):
    text=compact(text);local=compact(context)
    years=re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)',text)
    previous=bool(re.search(r'上年同期|上年报告期|上年年初|上期|上年度|上年金额',text))
    opening=bool(re.search(r'期初|上年年末|年初(?!至)',text)) and not bool(re.search(r'年初至',text))
    current=bool(re.search(r'本期|本年|本报告期|期末|年末|年初至报告期末',text))
    year=int(years[0]) if len(set(years))==1 else int(report_year)-int(previous or opening) if report_year and (previous or opening or current) else None
    if not year:return {'period':'unknown'}
    balance=statement=='balance' or opening or bool(re.search(r'余额|期末|年末',text)) and not bool(re.search(r'年初至',text))
    date=re.search(r'(\d{1,2})月(\d{1,2})日',text)
    english=re.search(r'(\d{1,2})(January|February|March|April|May|June|July|August|September|October|November|December)',text,re.I)
    month_first=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)(\d{1,2})',text,re.I)
    iso=re.search(r'\d{4}-(\d{2})-(\d{2})',text)
    if english:
        month=list(calendar.month_name).index(english[2].capitalize());day=int(english[1])
    elif month_first:
        month=list(calendar.month_name).index(month_first[1].capitalize());day=int(month_first[2])
    elif date or iso:month,day=map(int,(date or iso).groups())
    else:month=day=None
    flow=statement in {'income','cashflow','equity'} or bool(re.search(r'monthsended|发生|年度|年初至|季度|[1１][-—–至~～]9月',text,re.I))
    if month and (balance or not flow):return {'period':f'{year}-{month:02d}-{day:02d}'}
    if balance:
        end=12 if opening else report_end
        if not end:return {'period':'unknown'}
        return {'period':f'{year}-{end:02d}-{calendar.monthrange(year,end)[1]}'}
    # Column evidence wins over the report: Q3 vs January-September can
    # appear side by side on the same quarterly headline table.
    span=re.search(r'(\d{1,2})\s*[-—–至~～]\s*(\d{1,2})月',text)
    if span:return flow_period(year,*map(int,span.groups()))
    quarter=re.search(r'第?([一二三四1234])季度',text)
    cumulative=bool(re.search(r'年初至|前三季度',text))
    if cumulative:
        end=9 if '前三季度' in text else report_end
        return flow_period(year,1,end) if end else {'period':'unknown'}
    if quarter:
        q='一二三四'.find(quarter[1])+1 if quarter[1] in '一二三四' else int(quarter[1])
        return flow_period(year,q*3-2,q*3)
    evidence=text+' '+local
    span=re.search(r'(?:19|20)\d{2}年(\d{1,2})[-—–至~～](\d{1,2})月',local)
    if span:return flow_period(year,*map(int,span.groups()))
    dated_span=re.search(r'(\d{1,2})月\d{1,2}日[-—–至~～]+(?:\d{4}年)?(\d{1,2})月\d{1,2}日',evidence)
    if dated_span:return flow_period(year,*map(int,dated_span.groups()))
    if re.search(r'本报告期|上年同期',text) and report_end in {3,9}:
        return flow_period(year,report_end-2,report_end)
    if re.search(r'sixmonthsended|六个月|半年度|中期',evidence,re.I):end=6
    elif re.search(r'ninemonthsended|九个月|前三季度',evidence,re.I):end=9
    elif re.search(r'twelvemonthsended|yearended|年度',text,re.I):end=12
    elif month:end=month
    else:end=report_end
    return flow_period(year,1,end) if end else {'period':'unknown'}

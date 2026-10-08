"""Shared workpaper period input: spelling is flexible, chronology is not.

Flow windows from source metadata distinguish a quarter from year-to-date.
Explicit unavailable periods are input errors; an absent automatic comparator
stays a missing comparison, so the current period remains usable.
"""
from calendar import monthrange
from datetime import date
import re
import unicodedata


class WorkpaperInputError(ValueError):
    def __init__(self, message, selection=None):
        super().__init__(message)
        self.selection = selection


def canonical_period(value, start=None, end=None):
    text=re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value))).upper()
    text=re.sub(r'\((?:经?重述|调整[前后]|RESTATED|ADJUSTED|UNADJUSTED)\)', '', text)
    interval=re.fullmatch(r'(\d{4})[年/.-](\d{1,2})[月/.-](\d{1,2})日?(?:至|到|~|—|–|--)(\d{4})[年/.-](\d{1,2})[月/.-](\d{1,2})日?',text)
    if interval and not (start and end):
        y,m,d,Y,M,D=map(int,interval.groups())
        start,end=str(date(y,m,d)),str(date(Y,M,D))
    if start and end and start != end:
        a,b=date.fromisoformat(start),date.fromisoformat(end)
        if a.year==b.year and b.day==monthrange(b.year,b.month)[1]:
            if a.month==1 and a.day==1 and b.month in (3,6,9,12):
                return f'{b.year}-'+{3:'Q1',6:'H1',9:'9M',12:'FY'}[b.month]
            if a.day==1 and a.month==b.month-2 and b.month in (3,6,9,12):return f'{b.year}-Q{b.month//3}'
    match=re.search(r'(?:19|20)\d{2}',text)
    if not match:raise WorkpaperInputError(f'无法识别期间 {value!r}')
    year=match[0]
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):
        d=date.fromisoformat(text)
        if d.month in (3,6,9,12) and d.day==monthrange(d.year,d.month)[1]:
            return year+'-'+{3:'Q1',6:'H1',9:'9M',12:'FY'}[d.month]
        raise WorkpaperInputError(f'{value!r} 不是完整流量期间的期末日')
    suffix=(text[:match.start()]+text[match.end():]).strip('-')
    if suffix not in ('年度','年报','年度报告'):suffix=suffix.removeprefix('年')
    span=re.fullmatch(r'1[-至~—–](3|6|9|12)月',suffix)
    if span:return year+'-'+{'3':'Q1','6':'H1','9':'9M','12':'FY'}[span[1]]
    if suffix.endswith('年') and suffix not in ('全年','上半年','下半年','半年','财年'):suffix=suffix[:-1]
    aliases={'':'FY','FY':'FY','全年':'FY','年报':'FY','年度':'FY','年度报告':'FY','财年':'FY','12M':'FY','YTD4':'FY',
             'H1':'H1','6M':'H1','YTD2':'H1','上半年':'H1','半年度':'H1','半年':'H1','中报':'H1','半年报':'H1','半年度报告':'H1','中期':'H1','中期报告':'H1',
             'H2':'H2','下半年':'H2','9M':'9M','YTD3':'9M','前三季度':'9M','前三季':'9M','前九个月':'9M',
             '3M':'Q1','YTD1':'Q1'}
    if suffix in aliases:return year+'-'+aliases[suffix]
    m=re.fullmatch(r'Q([1-4])|第?([一二三四1234])季(?:度)?',suffix)
    if m:
        q=m[1] or (str('一二三四'.index(m[2])+1) if m[2] in '一二三四' else m[2])
        return year+'-Q'+q
    raise WorkpaperInputError(f'无法识别期间 {value!r}')


def period_window(period):
    year,kind=period.split('-',1);year=int(year)
    if kind=='FY':return f'{year}-01-01',f'{year}-12-31'
    if kind=='H1':return f'{year}-01-01',f'{year}-06-30'
    if kind=='H2':return f'{year}-07-01',f'{year}-12-31'
    if kind=='9M':return f'{year}-01-01',f'{year}-09-30'
    q=int(kind[1]);month=q*3
    return f'{year}-{month-2:02d}-01',f'{year}-{month:02d}-{monthrange(year,month)[1]}'


def normalize_period_records(records):
    result=[]
    for r in records:
        n=r.get('source_ref',{}).get('normalization',{})
        if n.get('statement') in ('income','cashflow'):
            # Cash-flow statements also contain point-in-time opening/closing cash.
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',r['period']) and (not n.get('period_start') or n.get('period_start')==n.get('period_end')):
                from .standard_metrics import workpaper_concepts
                if not set(workpaper_concepts(r['metric'])) & {'cash_begin','cash_end'}:
                    r={**r,'source_ref':{**r['source_ref'],'normalization':{**n,'period_error':'流量行只有时点，缺少期间起点；需从原表列头定位'}}}
                result.append(r);continue
            try:
                p=canonical_period(r['period'],n.get('period_start'),n.get('period_end'))
            except WorkpaperInputError as exc:
                result.append({**r,'source_ref':{**r['source_ref'],'normalization':{**n,'period_error':str(exc)}}})
                continue
            if p!=r['period']:
                r={**r,'period':p,'source_ref':{**r['source_ref'],'normalization':{**n,'record_period':r['period']}}}
        result.append(r)
    return result


def normalize_periods(periods, available, windows=None):
    """Return current, comparable and other requested periods, order-independent.

    `available` describes the selected issuer/scope only. A date selects the
    longest flow window ending that day, never a balance-sheet observation.
    """
    windows=windows or {}
    choices=sorted({canonical_period(p) for p in available})
    def window(p):return windows.get(p) or period_window(p)
    def chronology(p):
        a,b=window(p)
        return b,(date.fromisoformat(b)-date.fromisoformat(a)).days,p
    def invalid(message):raise WorkpaperInputError(message+'；可用期间：'+', '.join(sorted(choices,key=chronology,reverse=True)))
    if not choices:invalid('没有可用的流量期间')
    requested=[periods] if isinstance(periods,str) else list(periods or [])
    selected=[]
    for value in requested:
        try:
            raw=re.sub(r'\s+','',str(value))
            at_end=[p for p in choices if window(p)[1]==raw] if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw) else []
            p=max(at_end,key=chronology) if at_end else canonical_period(value)
        except (WorkpaperInputError,ValueError) as exc:invalid(str(exc))
        if p not in choices:invalid(f'期间 {value!r}（{p}）不在当前数据中')
        selected.append(p)
    selected=sorted(set(selected or [max(choices,key=chronology)]),key=chronology,reverse=True)
    current=selected[0];start,end=window(current)
    # Same month/day window, not the caller's second array element.
    comparable=[p for p in selected[1:] if tuple(x[5:] for x in window(p))==(start[5:],end[5:])]
    prior=comparable[0] if comparable else selected[1] if len(selected)>1 else str(int(current[:4])-1)+current[4:]
    return [current,prior,*[p for p in selected[1:] if p!=prior]]

"""Shared source-preserving arithmetic and statement context for analyst papers."""
from datetime import date, timedelta
from decimal import Decimal
import json
import re
import unicodedata

from .analysis_report import convert, record_quantity
from .financial_workpapers import Statement, cell, meta, dimensions_ok, source, ALIASES
from .workpaper_annual import Disclosure, compact


def unknown(reason, unit='元'):
    return cell(None, unit, reason=reason)


def value(q):
    return None if q['value'] is None else Decimal(convert(q['value'], q['unit'], '元' if q.get('currency') else q['unit']))


def calc(qs, fn, unit='元', formula='', positive=()):
    missing = [q['source'].get('missing_reason') or '缺少计算输入' for q in qs if q['value'] is None]
    vs = [value(q) for q in qs]
    if not missing:
        missing = [f'第{i+1}个分母输入非正，无法计算有意义的比例' for i in positive if vs[i] <= 0]
    currencies = {q['currency'] for q in qs if q.get('currency')}
    if len(currencies) > 1:
        missing.append('币种不同，未隐含换汇')
    return cell(None if missing else fn(*vs), unit, next(iter(currencies)) if unit == '元' and currencies else None,
                [q['source'] for q in qs], formula, '；'.join(dict.fromkeys(missing)) or None)


def ratio(a, b, formula='分子/分母*100', unit='%'):
    return calc([a,b], lambda x,y:x/y*(100 if unit=='%' else 1), unit, formula, (1,))


def delta(a, b, unit='元'):
    return calc([a,b], lambda x,y:x-y, unit, '本期-比较期')


def growth(a,b):
    return calc([a,b], lambda x,y:(x-y)/y*100, '%', '(本期-比较期)/比较期*100；比较期须为正', (1,))


def locators(q):
    found = {}
    def visit(x):
        if isinstance(x,dict):
            if x.get('page'):
                r={k:x[k] for k in ('document_id','report','page','table_id','row','column','column_label','text') if k in x}
                found[json.dumps(r,sort_keys=True,ensure_ascii=False)]=r
            for v in x.values():visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
    visit(q)
    return list(found.values())


EXTRA = {
    'cash_balance': ('cash_and_cash_equivalents','cash_and_bank_balances','cash'),
    'other_receivables': ('other_receivables',), 'prepayments': ('prepayments','prepaid_expenses'),
    'other_noncurrent': ('other_non_current_assets','other_noncurrent_assets'), 'goodwill': ('goodwill',),
}


class AnalystData:
    def __init__(self,service,project,document_id=None,company=None,scope='consolidated',periods=None,focus=None):
        from .financial_workpapers import statement_analysis
        self.base,self.records=statement_analysis(service,project,document_id,company,scope,periods,focus)
        self.st=Statement(service,project,self.records,scope,periods)
        self.d=Disclosure(self.st)
        self.ps=self.st.periods
        self.currency=self.st.currency
        self._period_series=None

    def pick(self,key,period,statement):
        if statement!='balance' and key not in EXTRA:
            r=self.st.pick(key,period,statement)
            return record_quantity(r) if r else unknown(f'缺少 {period} {key} 唯一同口径披露')
        aliases=EXTRA.get(key,ALIASES.get(key,(key,)))
        matches=[r for r in self.records if r['period']==period and r['metric'] in aliases
                 and meta(r).get('statement')==statement and dimensions_ok(r) and r['currency']==self.currency]
        if statement=='balance':
            # Main balance sheets have explicit current/noncurrent sections;
            # this excludes rounded liquidity-summary duplicates.
            ids={t['table_id'] for t in self.d.tabs if re.search(r'流动(?:资产|负债)(?:合计|：|:)|(?:current assets|current liabilities)',
                                                               ' '.join(row[0] for row in t['rows'] if row), re.I)}
            primary=[r for r in matches if r['source_ref'].get('table_id') in ids]
            if primary:matches=primary
        if matches:
            best=min(aliases.index(r['metric']) for r in matches)
            matches=[r for r in matches if aliases.index(r['metric'])==best]
            if len({r['value'] for r in matches})==1 and all(r.get('quality')!='conflict' for r in matches):
                return record_quantity(matches[0])
            return cell(None, currency=self.currency, sources=[source(r) for r in matches], reason=f'{key} 同口径来源存在冲突')
        r=self.st.pick(key,period,statement) if key not in EXTRA else None
        return record_quantity(r) if r else unknown(f'缺少 {period} {key} 同口径披露')

    def window(self,p):
        r=self.st.pick('revenue',p,'income')
        return (meta(r).get('period_start'),meta(r).get('period_end')) if r else (None,None)

    def balance(self,key,p,begin=False,year_ago=False):
        start,end=self.window(p)
        if not start or not end:return unknown(f'{p} 缺少期间起止日期')
        when=date.fromisoformat(start)-timedelta(days=1) if begin else date.fromisoformat(end)
        if year_ago:when=when.replace(year=when.year-1)
        return self.pick(key,str(when),'balance')

    def annual_row(self,table_name,key):
        return next((r for r in self.base['tables'].get(table_name,{}).get('rows',[]) if r['key']==key),{})

    def quarters(self,metric):
        """N2 public period adapter: disclosed quarters or sourced YTD differences."""
        year=self.ps[0][:4]
        if self.window(self.ps[0])!=(year+'-01-01',year+'-12-31'):
            return [unknown('当前不是完整全年；中报/季报不外推第四季度或冒充全年分母') for _ in range(4)]
        series=self.period_series()
        result=[]
        for i in range(1,5):
            period=f'{year}-Q{i}'
            row=next((r for r in series['quarters'] if r['metric']==metric and r['period']==period),None)
            missing=next((r for r in series['missing'] if r['metric']==metric and r['period']==period),{})
            result.append(row['quantity'] if row else unknown(missing.get('reason','缺少同口径单季或可推导累计来源')))
        return result

    def first_three_quarters(self,metric):
        year=self.ps[0][:4]
        if self.window(self.ps[0])!=(year+'-01-01',year+'-12-31'):
            return unknown('当前不是完整全年，不进行Q4与前三季方向比较')
        row=next((r for r in self.period_series()['cumulatives'] if r['metric']==metric and r['period']==year+'-YTD3'),None)
        return row['quantity'] if row else unknown('缺少同口径前三季累计或三个可加单季')

    def period_series(self):
        if self._period_series is None:
            from .financial_workpapers import load_facts
            from .workpaper_periods import period_inputs
            from .period_algebra import derive_period_series
            others=[r for r in load_facts(self.st.service,self.st.project,company=self.st.company) if r['document_id']!=self.d.doc]
            inputs,unrecognized=period_inputs(self.st,self.d,others)
            years={p[:4] for p in self.ps}
            inputs=[r for r in inputs if not r['start'] or r['start'][:4] in years]
            self._period_series=derive_period_series(inputs,self.d.doc)
            self._period_series['unknown_rows']=unrecognized
            self.records=[*self.records,*others]
        return self._period_series

    def source_text(self,page,quote,**extra):
        text=self.d.pages.get(int(page),'')
        if quote not in text:
            chars=[];positions=[]
            for i,c in enumerate(text):
                for n in unicodedata.normalize('NFKC',c):
                    if not n.isspace():chars.append(n);positions.append(i)
            normalized=''.join(chars);needle=compact(quote);offset=normalized.find(needle)
            if offset>=0 and needle:quote=text[positions[offset]:positions[offset+len(needle)-1]+1]
        return {'document_id':self.d.doc,'report':self.d.document.get('original_name'),'page':int(page),'quote':quote,**extra}

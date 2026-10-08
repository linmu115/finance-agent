"""Unit-aware extraction shared by the observation scanner. No historical case rules."""

import re

from decimal import Decimal as D

NUM=re.compile(r'(?<![0-9_.])[-+−–]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|(?<![0-9_.])[-+−]?\.\d+')

UNIT=re.compile(r"(?:RMB|CNY|HKD|HK\$|人民币|港币|港元|美元|USD)\s*(?:[/／_]\s*(?:RMB|CNY|人民币|share|股))|(?:RMB|CNY|HKD|HK\$|人民币|港币|港元|USD)\s*(?:[’'`]?000|thousand|million|billion|mn|bn|m\b|十亿元|百万元|千元|万元|亿元|元)(?:\s*[/／]\s*(?:share|股))?|(?:人民币|港币|港元|CNY|RMB|HKD|HK\$)?\s*(?:十亿元|百万元|千元|万元|亿元|元)(?:\s*[/／]\s*股)?|(?:million\s+shares?|shares?\s*(?:million|\(m\))|百万股|亿股|万股|股)|percentage\s+points|个百分点|百分点|\bpp\b|\bratio\b|比例|百分比|%|％|倍|\b[xX]\b|(?:RMB|CNY|HKD|港元|港币|HK\$)(?:/股)?",re.I)

def unit(text,default='CNY',metric=''):
    t=text.strip().lower().replace('_',' ').replace('／','/'); t=re.sub(r'\s+',' ',t)
    currency='HKD' if re.search(r'hkd|hk\$|港币|港元',t) else 'USD' if 'usd' in t or '美元' in t else 'CNY' if re.search(r'rmb|cny|人民币',t) else default
    if re.search(r'(hkd|港币|港元)\s*/\s*(rmb|cny|人民币)',t):return ('fx','HKD/CNY','1')
    if re.search(r'percentage points|个百分点|百分点|\bpp\b',t):return ('percentage_points','', '1')
    if '%' in t or '％' in t or '百分比' in t:return ('ratio','', '0.01')
    if re.search(r'\bratio\b',t) or '比例' in t:return ('ratio','', '1')
    if '倍' in t or t in ['x','multiple']:return ('multiple','', '1')
    if ('股' in t or 'share' in t) and '/' not in t and not re.search('元|rmb|hkd|cny',t):
        scale='100000000' if '亿' in t else '1000000' if '百万' in t or 'million' in t or '(m)' in t else '10000' if '万' in t else '1'
        return ('shares','',scale)
    if re.search(r'元|rmb|cny|hkd|hk\$|港币|usd',t):
        scale='1000000000' if '十亿' in t or re.search(r'billion|\bbn\b',t) else '100000000' if '亿' in t else '1000000' if '百万' in t or re.search(r'million|\bmn\b|\bm\b|rmbmn',t) else '10000' if '万元' in t else '1000' if '千' in t or '000' in t or 'thousand' in t else '1'
        dim='per_share' if re.search(r'/\s*(股|share)|eps|每股|value/share|per.share',t+' '+metric,re.I) else 'money'
        return (dim,currency,scale)
    return None

def unit_hits(t,default='CNY',metric=''):
    return [(m.start(),m.end(),unit(m.group(),default,metric),m.group()) for m in UNIT.finditer(t) if unit(m.group(),default,metric)]

def val(s):return D(s.replace(',','').replace('−','-').replace('–','-'))

def text_quantities(text,where,default_unit=None,source=False):
    found=[];omitted=[];table_header=None;global_money=default_unit;section_unit=None;declared_metrics={};section=''
    lines=text.splitlines()
    for ln,original in enumerate(lines,1):
        line=re.sub(r'`[^`]+\.(?:png|csv|json|py|md|zip)`','',original).replace('\\%','%').replace('**','').replace('`','').replace('HK\\$','HK$')
        line=re.sub(r'\{[^{}]*\}',lambda m:' '*len(m[0]),line)  # Unrendered template format specs are not financial numbers.
        line=re.sub(r'20\d{2}-\d{2}-\d{2}|\[(?:[^\]]*第[^\]]*页|同上[^\]]*|报告[^\]]*)\]','',line)
        # URLs, identifiers, inline images and code paths carry no financial quantities.
        line=re.sub(r'!?\[[^\]]*\]\([^)]*\)','',line)
        line=re.sub(r'[a-fA-F0-9]{20,}|(?:https?://|analysis/|/input/|/output/|sandbox:)[^\s，。；]+','',line)
        # Mask non-financial references and pure formula constants before unit inference.
        line=re.sub(r'第[\d、,–—至及\- ]+页', '', line)
        line=re.sub(r'(?:物理页|页码|页|[Pp]\.|Figure\s*|图|表\s*)[\d、,–—至及\- ]+', '', line)
        line=re.sub(r'(?:期数为?|按期数|按|t\s*=)\s*1\s*[–—至…-]\s*5', '', line)
        line=re.sub(r'\b[A-Z]\d+(?=[/（、])|(?<=/)B\d+', '', line)
        if re.search(r'\\sum|\\frac',line) and not re.search(r'\d+\.\d+',line):continue
        if not line.strip():continue
        if line.lstrip().startswith('#'):
            section=line.strip('# ').strip()
            uh=unit_hits(line);section_unit=uh[-1][2] if uh else None
            if section_unit and section_unit[0]=='money':global_money=section_unit
        if re.search(r'金额.{0,40}(?:统一|均|单位|人民币)|FCF.{0,12}为人民币|单位[：:]|RMB[’\']000|人民币千元',line,re.I):
            monies=[h[2] for h in unit_hits(line) if h[2][0]=='money']
            if monies: global_money=monies[0]
        for clause in re.split('[；，。]',line):
            if re.search('为|单位|均|采用|以',clause) and re.search('收入|利润|EPS|每股',clause,re.I):
                units=unit_hits(clause)
                if units and not any(abs(val(n.group()))<1900 and not re.match('页',clause[n.end():]) for n in NUM.finditer(clause)):
                    for metric in ['收入','净利润','利润','EPS','每股']:
                        if metric.lower() in clause.lower():declared_metrics[metric]=units[-1][2]
                    monies=[h[2] for h in units if h[2][0]=='money']
                    if monies:global_money=monies[-1]
        cells=line.strip().strip('|').split('|') if line.strip().startswith('|') else None
        next_nonempty=next((v for v in lines[ln:] if v.strip()),'')
        if cells and re.match(r'^\s*\|?\s*:?-{2,}',next_nonempty):
            table_header=cells;firstunits=unit_hits(cells[0])
            if firstunits and firstunits[-1][2][0] in ['money','per_share']:global_money=firstunits[-1][2]
        if cells and re.match(r'^\s*\|?\s*:?-{2,}',line):continue
        if not cells:table_header=None
        # Statement/source tables exported as fixed-width plain text retain row labels and units.
        rowlabel=(cells[0] if cells else re.split(r'\s{2,}',line.strip())[0] if re.search(r'\S\s{2,}\S',line) else '')
        row_unit=unit_hits(rowlabel,metric=rowlabel)
        column_units=[unit_hits(h,metric=h) for h in (table_header or [])]
        hits=unit_hits(line)
        nums=list(NUM.finditer(line))
        for m in nums:
            raw=m.group();n=val(raw);start,end=m.span()
            if source and start and line[start-1]=='(' and line[end:end+1]==')':n=-abs(n)
            if any(a<=start<b for a,b,u,rawu in hits):continue
            if re.match(r'(?:E|A|H[12]|年|月|日|页|\s*[:：])',line[end:]) and abs(n)>=1900:continue
            if re.search(r'(?:FY|H[12]|FY\d{2}[EA]?[–至-])$',line[:start],re.I) or re.match(r'[EA](?![A-Za-z])',line[end:]):continue
            if re.search(r'(?:FY|H|FY\d{2}[EA]?[–至-])$',line[:start],re.I):continue
            if D(1900)<=n<=D(2100) and '.' not in raw and ',' not in raw:continue
            if re.match(r'\s*[- ]?(?:mth|month|day|year|yr)\b',line[end:],re.I):continue
            if re.match(r'\)\s*[A-Za-z]',line[end:]):continue
            if re.search(r'(?:第|page\s*|p\.?\s*|表\s*|figure\s*|t)$',line[:start],re.I) or re.match(r'\s*(?:页|天|次|项|张|年|月|日|期)',line[end:]):continue
            if re.match(r'\s*\d+[.、)]\s',line) and m.start()==len(line)-len(line.lstrip()):continue
            col=line[:start].count('|')-1 if cells else None
            selected=None;basis=None
            after=[h for h in hits if '=' not in line[end:h[0]] and h[0]>=end and not NUM.search(line[end:h[0]]) and not re.search('[A-Za-z\u4e00-\u9fff；，。|]',line[end:h[0]]) and len(line[end:h[0]].strip(' *()（）$\\,:：='))<=1]
            before=[h for h in hits if h[1]<=start and not NUM.search(line[h[1]:start]) and not re.search('[A-Za-z\u4e00-\u9fff；，。|]',line[h[1]:start]) and len(line[h[1]:start].strip(' *()（）$\\,:：='))<=1]
            if after:selected=after[0][2];basis='explicit_suffix'
            elif before:selected=before[-1][2];basis='explicit_prefix'
            elif table_header and col is not None and 0<=col<len(column_units) and column_units[col]:selected=column_units[col][-1][2];basis='table_column_header'
            elif table_header and col is not None and 0<=col<len(table_header) and any(k.lower() in table_header[col].lower() for k in declared_metrics):
                selected=next(v for k,v in declared_metrics.items() if k.lower() in table_header[col].lower());basis='declared_metric_unit'
            elif table_header and col is not None and 0<=col<len(table_header) and re.search('变化|差额|贡献',table_header[col]) and any(u[2][0]=='per_share' for hs in column_units for u in hs):
                per=[u[2] for hs in column_units for u in hs if u[2][0]=='per_share']
                if per:selected=per[0];basis='difference_of_same_unit_columns'
            elif row_unit:selected=row_unit[-1][2];basis='table_row_label'
            elif cells and any(h.strip() in ['单位','unit'] for h in (table_header or [])):
                ix=next(i for i,h in enumerate(table_header) if h.strip() in ['单位','unit']);uh=unit_hits(cells[ix]) if ix<len(cells) else []
                if uh:selected=uh[-1][2];basis='table_unit_cell'
            if selected is None and not cells:
                # In “由 A 降至 B 百万元（同比…%）”, the amount pair shares
                # B's immediate unit; a later percentage is a separate claim.
                pair=re.match(r'\s*(?:降至|升至|增至|减至|下降至|上升至|增加至|减少至|变为|到|至)\s*',line[end:])
                if pair:
                    following=NUM.match(line,end+pair.end())
                    if following:
                        attached=[h for h in hits if h[0]>=following.end() and not line[following.end():h[0]].strip()]
                        if attached:selected=attached[0][2];basis='paired_value_unit'
            if selected is None:
                # Repeated bare values in a sentence/table inherit one unambiguous dimension.
                bounds=[0,*[x.end() for x in re.finditer('[；。]|(?<!\\d)，',line)],len(line)]
                lo=max(x for x in bounds if x<=start);hi=min(x for x in bounds if x>=end)
                distinct=list(dict.fromkeys(h[2] for h in hits if lo<=h[0]<hi))
                if len(distinct)==1 and not cells:selected=distinct[0];basis='shared_clause_unit'
                elif section_unit and cells:selected=section_unit;basis='section_header'
                elif global_money and (cells or re.search(r'收入|利润|毛利|现金|净值|净利|估值|股权|企业价值|FCF|EBIT|revenue|profit|cash|tax|cost|sales|EV|equity|=',line,re.I)):
                    selected=global_money;basis='declared_amount_unit'
            currency_prefix=re.search(r'(RMB|CNY|HKD|HK\$)\s*$',line[:start],re.I)
            scale_suffix=re.match(r'\s*(mn|bn|million|billion)(?![A-Za-z])',line[end:],re.I)
            if currency_prefix and scale_suffix:selected=unit(currency_prefix[1]+' '+scale_suffix[1]);basis='split_currency_and_scale'
            elif re.search(r'股数\s*$',line[:start]) and scale_suffix:selected=('shares','','1000000' if scale_suffix[1].lower() in ['mn','million'] else '1000000000');basis='share_count_scale_suffix'
            elif scale_suffix and selected and selected[0]=='money':selected=(selected[0],selected[1],'1000000' if scale_suffix[1].lower() in ['mn','million'] else '1000000000');basis='scale_suffix'
            if not (scale_suffix or after) and selected and selected[0]=='money' and selected[2]=='1':
                tail=line[end:re.search('[；。，]',line[end:]).start()+end if re.search('[；。，]',line[end:]) else len(line)]
                if re.search(r'\d(?:mn|million)\b',tail):selected=(selected[0],selected[1],'1000000');basis='shared_list_scale'
            if selected and selected[0]=='shares' and before and before[-1][2][0]=='money' and '/' in line[end:after[0][0]]:
                selected=('per_share',before[-1][2][1],'1');basis='currency_prefix_and_per_share_suffix'
            if selected and selected[0]=='money' and re.match(r'\s*/\s*股',line[end:]):selected=('per_share',selected[1],selected[2])
            if re.search(r'(?:汇率|HKD/RMB|人民币兑港元)[^\d；。]{0,8}$',line[:start]):selected=('fx','HKD/CNY','1');basis='explicit_fx_label'
            if re.search(r'[-−](?:HK\$|HKD|RMB|人民币|港元)\s*$',line[:start],re.I):n=-abs(n);raw='−'+raw
            if selected and re.search(r'毛利率|利润率|growth|margin|WACC|\bg\b',rowlabel,re.I) and selected[0]=='money' and (not cells or col==0):
                selected=None # Never infer a rate from a monetary default.
            if cells and table_header and table_header!=cells and col and not (after or before) and re.search('WACC',table_header[0],re.I) and re.search(r'增长|\\\\|\bg\b',table_header[0],re.I):
                previous=' '.join(lines[max(0,ln-12):ln-1]);units=[h[2] for h in unit_hits(previous) if h[2][0]=='per_share']
                if units:selected=units[-1];basis='sensitivity_table_caption'
            if not (after or before) and cells and table_header and col is not None and 0<=col<len(table_header) and re.search('FCF.*(?:因子|系数|倍率|倍数|缩放|乘数|比例)|(?:因子|系数|乘数|factor|multiplier)',table_header[col],re.I):selected=None
            if not (after or before) and (re.search(r'除以|乘以|各年乘|[÷×*]|按(?=\d)',line[max(0,start-5):start]) or (n in [0,1] and re.search(r'[+*/×]',line[max(0,start-1):end+1]))):
                selected=None
            if cells and re.search('FCF.*乘数|FCF.*factor',rowlabel,re.I) and not (after or before):selected=None
            if abs(n)==1000 and re.search(r'换算|折算|除以|÷',line) and not re.search(r'1000(?:百万元|亿元)',line):selected=None
            if source and basis in ['shared_clause_unit','declared_amount_unit'] and not cells and not rowlabel:selected=None
            if not selected:
                omitted.append({'line':ln,'normalizedColumn':start+1,'raw':raw,'context':original[:240],'reason':'no unambiguous unit from token, row, column or declared scope'});continue
            if selected[0]=='money' and re.search(r'EPS|每股|value/share|per.share',rowlabel or re.split('[；。，、]',line[:start])[-1],re.I):selected=('per_share',selected[1],selected[2])
            if selected[0]=='money' and selected[1]=='HKD' and re.search(r'每股|value/share|per.share',re.split('[；。，]',line[:start])[-1],re.I):selected=('per_share',selected[1],selected[2])
            found.append({'value':str(n),'unit':list(selected),'raw':raw,'unitBasis':basis,'where':where,'section':section,'table_header':table_header,'table_column':col,'row_label':rowlabel,'line':ln,'normalizedColumn':start+1,'prefix':line[:start],'suffix':line[end:],'context':line[max(0,start-120):min(len(line),end+240)]})
    return found,omitted

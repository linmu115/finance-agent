"""Source-backed basis changes, adjustment pairs and repeated nonrecurring items.

A policy description or an unchecked template is not a restatement. Recognition
and arithmetic are deterministic; economic reclassification is left to analysis.
"""
from decimal import Decimal,localcontext
import json
import re

from .analysis_report import convert,record_quantity
from .financial_workpapers import ALIASES,Statement,cell,col,dimensions_ok,load_facts,meta,table
from .workpaper_annual import Disclosure,compact,literal,row_kind
from .workpaper_periods import column_context

MARKERS={
    'accounting_policy':r'会计政策(?:的)?变更|會計政策(?:的)?變更|会计政策(?=、会计估计变更)|执行[^。；;]*?准则|執行[^。；;]*?準則|解释第\s*[0-9一二三四五六七八九十]+\s*号|解釋第\s*[0-9一二三四五六七八九十]+\s*號|重分类|重分類|changes? (?:in|to) (?:the .{0,25})?accounting policies|reclassifi(?:ed|cation)',
    'accounting_estimate':r'会计估计(?:的)?变更|會計估計(?:的)?變更|changes? in accounting estimates',
    'prior_error':r'(?:前期|重大)?会计差错更正|前期差错更正|前期差錯更正|prior.period errors?',
    'common_control':r'(?<!非)同一控制下(?:的)?企业(?:吸收)?合并|同一控制下(?:的)?企業合併|business combinations? under common control',
    'restatement':r'追溯(?:调整|重述)|追溯(?:調整|重列)|(?<!追溯)重述|\brestat(?:ed|ement)\b|retrospective(?:ly)? (?:adjust|restat)\w*',
}


def _marker_sentences(text):
    # PDF line wraps belong to the sentence; numbered headings and checkbox
    # blocks do not. In particular a combined policy/estimate heading must not
    # lend its type or checkbox to the following policy implementation sentence.
    text=re.sub(r'(?m)^(?=\s*(?:[一二三四五六七八九十]+、|[（(](?:[一二三四五六七八九十]+|\d+)[）)]|\d+、))','\0',text)
    text=re.sub(r'(?:[√✓☑□]\s*(?:不适用|不適用|适用|適用)\s*)+',lambda m:m[0]+'\0',text)
    clean=re.sub(r'\s+',' ',text)
    clean=re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',clean)
    return [s.strip() for s in re.split(r'\x00|(?<=。)|(?<=\.)\s+',clean) if s.strip()]


def _completion_evidence(sentence):
    """Explicit implementation language, not conditional accounting mechanics."""
    # These are actual policy-template constructions, not absence of evidence.
    if re.search(r'若|如为|如為|如果|倘|视同|視同|应当|應當|应按|應按|拟|擬|将于|將於|将会|將會|\b(?:if|would|will|shall|should)\b',sentence,re.I):return None
    subject=r'(?:报告期(?:内|间)?|報告期(?:內|間)?|本期|本年度|本年|本公司|本集团|本集團|the group|the company)'
    action=r'(?:已(?:经|經)?(?:对|對|按|根据|根據|发生|發生|完成|进行|進行|采用|採用|执行|執行|实施|實施|纳入|納入|并表|併表|收购|收購|追溯|重述|重列|变更|變更|更正|调整|調整)|完成|进行了|進行了|have (?:adopted|completed|restated)|has (?:adopted|completed|restated))'
    # Present-tense implementation disclosures also explicitly describe an
    # action: "本公司根据…规定，将…计入…" / "本公司采用…对…进行调整".
    for pattern in (
        subject+r'[^。；;]*?'+action,
        r'(?:报告期(?:内|间)?|報告期(?:內|間)?|本期|本年度)[^。；;]*?(?:纳入|納入|并表|併表|收购完成|收購完成)',
        subject+r'[^。；;]*?(?:根据|根據|按照)[^。；;]*?(?:准则|準則|解释|解釋)[^。；;]*?将[^。；;]*?(?:计入|計入|重分类|重分類)',
        subject+r'[^。；;]*?采用追溯(?:调整|重述)法对[^。；;]*?进行(?:相应)?调整',
    ):
        match=re.search(pattern,sentence,re.I)
        if match and not re.search(r'(?:未|尚未|未曾|没有|沒有|不曾)(?:发生|發生|完成|进行|進行|执行|執行|纳入|納入|收购|收購|将|將)|\b(?:has|have) not\b',match[0],re.I):return match[0]
    return None


def scan_basis_markers(pages,document_id):
    """Return every textual hit with a status, including negated/template hits."""
    found=[]
    for page,text in pages.items():
        for sentence in _marker_sentences(text):
            hits=[(kind,m) for kind,pattern in MARKERS.items() for m in re.finditer(pattern,sentence,re.I)]
            kinds={kind for kind,_ in hits}
            completion=_completion_evidence(sentence)
            for kind,m in hits:
                first_check=re.search(r'[√✓☑]\s*(?:不适用|不適用|适用|適用)|\bnot applicable\b',sentence[m.end():],re.I)
                status='unclassified';reason='未自动判定是否本期发生，需对照原文核对'
                if first_check:
                    active=not re.search(r'不|not',first_check[0],re.I)
                    if not active:
                        status='not_applicable';reason='原文明示不适用，保留原文标记'
                    elif len(kinds)==1:
                        status='change_disclosed';reason='原文该项勾选适用；发生时间与具体执行需对照正文'
                impact=re.search(r'影响.{0,20}(?:为|是)?\s*0(?:\.0+)?\s*元|did not result in significant changes|无(?:重大|实质)?影响|無(?:重大|重大性)?影響|未(?:发生|發生|进行|進行)|无需|毋須',sentence,re.I)
                if impact:
                    status='no_impact_or_no_change';reason='原文明示“'+impact[0]+'”，保留其限定范围'
                negated=re.search(r'(?:无需|无须|毋須|未|尚未|没有|沒有|未曾)[^，,；;。]*$',sentence[:m.start()])
                if completion and status!='not_applicable' and not negated:
                    status='restatement_disclosed' if kind=='restatement' else 'change_disclosed'
                    reason='原文明确执行/完成：“'+completion+'”；保留原句'
                found.append({'kind':kind,'status':status,'reason':reason,'quote':sentence,
                    'source':{'document_id':document_id,'page':page,'text':sentence,'match':m[0]}})
    return found


def basis_metric(label):
    text=compact(label)
    # "扣非" alone does not turn an EPS/ROE row into a profit amount.
    if re.search('净资产收益率|ROE',text,re.I):return 'deducted_weighted_roe' if '扣除' in text else 'weighted_roe' if '加权' in text else None
    if '每股收益' in text:return 'deducted_eps' if '扣除' in text else 'diluted_eps' if '稀释' in text else 'eps'
    k=row_kind(text)
    if k:return k
    patterns=[('deducted_weighted_roe',r'扣除.*非经常.*(?:净资产收益率|ROE)'),
        ('weighted_roe',r'加权平均(?:净资产收益率|ROE)'),
        ('parent_equity',r'归属.*(?:股东|所有者).*(?:净资产|权益)'),
        ('assets',r'^(?:资产总计|总资产)$'),('equity',r'^(?:所有者权益|股东权益)(?:合计|总计)$'),
        ('net_profit',r'^(?:净利润|净亏损)(?:\(.*\))?$'),('cogs',r'^(?:营业成本|销售成本)$'),
        ('gross_profit',r'^毛利(?:润)?$'),('eps',r'^基本每股收益'),('diluted_eps',r'^稀释每股收益')]
    return next((k for k,p in patterns if re.search(p,text,re.I)),None)


def _header_period(value,year,report_period):
    value=compact(value or '')
    m=re.fullmatch(r'(20\d{2})年(?:(\d{1,2})月(\d{1,2})日|度|末)?',value)
    if m:
        if m[2]:return f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}'
        return m[1]+('-12-31' if value.endswith('末') else '-'+report_period)
    if re.fullmatch(r'上年(?:同期|年末|末|度)?(?:\(.*\))?',value):return str(year-1)+('-12-31' if '末' in value else '-'+report_period)
    return None


def extract_adjustment_pairs(tables,pages,document_id,report_year,currency,scope,report_period='FY'):
    """Pure source-table adapter, also usable before ingestion for preview.

    tables contain table_id/page/rows. Preserve unknown metrics and ambiguous
    dates. Multirow headers carry the year across merged cells, not numbers.
    """
    pairs=[];unrecognized=[];previous_header=None
    for t in tables:
        periods={};versions={};header_refs={};rows=t['rows']
        for i,row in enumerate(rows):
            values=[str(x or '') for x in row]
            dates={c:_header_period(x,int(report_year),report_period) for c,x in enumerate(values)}
            dates={c:v for c,v in dates.items() if v}
            if dates:
                carried=None
                for c,value in enumerate(values):
                    if c in dates:carried=dates[c]
                    elif value.strip() and re.search('增减|同期|本期比|附注',value):carried=None
                    if carried:
                        periods[c]=carried;header_refs[c]={'document_id':document_id,'page':t['page'],'table_id':t['table_id'],'row':i+1,'column':c+1,'text':value or '合并表头同期间'}
                # A page may end with only the next table's year heading; its
                # before/after subheading and values continue on the next page.
                if previous_header and t['page']<=previous_header['page']+1:
                    if not versions:
                        # PDF merged headings can have more physical cells than
                        # the next page. Rebind the known comparison year by its
                        # explicit year label, never by shifted column index.
                        mapped={};refs={}
                        for c,old_period in previous_header['periods'].items():
                            if c not in previous_header['versions']:continue
                            candidates={v for v in dates.values() if v[:4]==old_period[:4]}
                            if len(candidates)==1:
                                mapped[c]=next(iter(candidates))
                                source_column=next(k for k,v in dates.items() if v==mapped[c])
                                refs[c]=header_refs[source_column]
                        previous_header={'page':t['page'],'periods':mapped,'versions':previous_header['versions'],'refs':refs}
                    else:previous_header={'page':t['page'],'periods':periods.copy(),'versions':versions.copy(),'refs':header_refs.copy()}
            marks={c:('original' if re.search('调整前|調整前|重述前|重列前|before adjustment|as previously reported',x,re.I) else 'restated') for c,x in enumerate(values) if re.search('调整[前后]|調整[前後]|重述[前后]|重列[前後]|before adjustment|as previously reported|as restated',x,re.I)}
            if marks:
                versions=marks
                if not periods and previous_header and t['page']<=previous_header['page']+1 and set(marks)==set(previous_header['versions']):
                    periods=previous_header['periods'].copy();header_refs=previous_header['refs'].copy()
                if periods:previous_header={'page':t['page'],'periods':periods.copy(),'versions':versions.copy(),'refs':header_refs.copy()}
                continue
            if not values or not values[0].strip() or not versions or dates:continue
            label=values[0];metric=basis_metric(label)
            cols={}
            for c,version in versions.items():
                if c>=len(values):continue
                p=periods.get(c)
                if p:cols.setdefault(p,{})[version]=c
            if not any(set(mapping)=={'original','restated'} for mapping in cols.values()) and any(literal(values[c]) is not None for c in versions if c<len(values)):
                unrecognized.append({'item':label,'reason':'调整列缺少可确定的期间表头','source':{'document_id':document_id,'page':t['page'],'table_id':t['table_id'],'row':i+1,'raw_row':values}})
            for period,mapping in cols.items():
                if set(mapping)!={'original','restated'}:continue
                # Blank template rows still have provenance but do not establish
                # that a numerical adjustment occurred.
                if all(not values[c].strip() for c in mapping.values()):continue
                unit='%' if 'roe' in (metric or '') or '%' in label or '％' in label else '元/股' if '每股' in compact(label) else None
                if unit is None:
                    marks_on_page=re.findall(r'单位\s*[:：]\s*(百万元|千元|万元|亿元|元)',pages.get(t['page'],''))
                    if len(set(marks_on_page))==1:unit=marks_on_page[0]
                quantities={}
                for version,c in mapping.items():
                    value=literal(values[c]);reason=None if value is not None and unit else '数值或单位未识别，保留原格'
                    quantities[version]={'value':str(value) if reason is None else None,'unit':unit or '元','currency':None if unit=='%' else currency,
                        'source':{'document_id':document_id,'page':t['page'],'table_id':t['table_id'],'row':i+1,'column':c+1,
                            'column_label':period+' '+version,'text':label,'raw_value':values[c],'header_source':header_refs.get(c),'missing_reason':reason}}
                pairs.append({'metric':metric or 'unrecognized:'+compact(label),'label':label,'period':period,'scope':scope,**quantities})
                if metric is None:unrecognized.append({'item':label,'reason':'调整前后数保留，指标未匹配，不参与关键比率','source':quantities['original']['source']})
    return pairs,unrecognized


def _math(qs,fn,unit='元',formula='',reason=None):
    reason=reason or ('缺少原报/重述的同口径输入' if any(q['value'] is None for q in qs) else None)
    with localcontext() as ctx:
        ctx.prec=40
        values=[Decimal(convert(q['value'],q['unit'],unit)) for q in qs] if not reason else []
        v=fn(values) if not reason else None
    return cell(v,unit,qs[0].get('currency') if qs else None,[q['source'] for q in qs],formula,reason)


def quantify_restatement(pairs):
    """Public pure core: original/restated typed quantities -> deltas and ratios."""
    changes=[];ratios=[]
    for i,p in enumerate(pairs):
        a,b=p['original'],p['restated'];unit=a['unit']
        delta=_math([b,a],lambda v:v[0]-v[1],unit,'重述数-原报数',
            '调整前后币种不一致，未换汇' if a.get('currency')!=b.get('currency') else None)
        if unit=='%':delta['unit']='个百分点';delta['currency']=None
        changes.append({'key':str(i),**p,'delta':delta,'changed':None if delta['value'] is None else Decimal(delta['value'])!=0})
    for period,scope in sorted({(p['period'],p['scope']) for p in pairs if '-FY' in p['period'] or re.search(r'-H[12]|-Q[1-4]',p['period'])}):
        group=[p for p in pairs if p['period']==period and p['scope']==scope]
        def q(metric,version,when=period):
            candidates=[p[version] for p in pairs if p['metric']==metric and p['period']==when and p['scope']==scope]
            if candidates and len({(x['value'],x['unit'],x.get('currency')) for x in candidates})==1:return candidates[0]
            return cell(None,'%' if metric=='weighted_roe' else '元',reason='缺少唯一 '+when+' '+version+' '+metric)
        for name in ('gross_margin','net_margin','parent_margin','roe_average_parent','weighted_roe'):
            values={}
            for version in ('original','restated'):
                if name=='weighted_roe':values[version]=q('weighted_roe',version);continue
                if name=='gross_margin':inputs=[q('revenue',version),q('cogs',version)];fn=lambda v:(v[0]-abs(v[1]))/v[0]*100;denominator=0;formula='(收入-成本绝对额)/收入*100'
                elif name=='roe_average_parent':
                    year=int(period[:4]);inputs=[q('parent_profit',version),q('parent_equity',version,f'{year-1}-12-31'),q('parent_equity',version,f'{year}-12-31')]
                    fn=lambda v:v[0]/((v[1]+v[2])/2)*100;denominator=None;formula='归母净利润/期初期末平均归母权益*100'
                else:
                    inputs=[q('revenue',version),q('net_profit' if name=='net_margin' else 'parent_profit',version)];fn=lambda v:v[1]/v[0]*100;denominator=0;formula='同口径净利润/收入*100'
                reason=None
                if all(x['value'] is not None for x in inputs):
                    raw=[Decimal(convert(x['value'],x['unit'],'元')) for x in inputs]
                    if (raw[denominator] if denominator is not None else raw[1]+raw[2])<=0:reason='比率分母非正'
                    if len({x.get('currency') for x in inputs})!=1:reason='比率输入币种不一致'
                money=_math(inputs,fn,'元',formula,reason)
                values[version]={**money,'unit':'%','currency':None}
            gap=_math([values['restated'],values['original']],lambda v:v[0]-v[1],'%','重述比率-原报比率')
            gap['unit']='个百分点';gap['currency']=None
            ratios.append({'key':f'{period}_{scope}_{name}','period':period,'scope':scope,'ratio':name,**values,'impact_pp':gap})
    return changes,ratios


def repeated_nonrecurring(d):
    """At least two nonzero, separately disclosed annual periods; no reclassify."""
    blocks=d.blocks('nonrec');rows=[]
    if len(blocks)!=1:return rows
    columns=d.columns(blocks[0]['header'])
    for t,i in blocks[0]['rows']:
        label=t['rows'][i][0]
        if not re.search('政府补助|政府補助|投资|投資|公允价值|公允價值|资产处置|資產處置|处置损益',compact(label)):continue
        values={p:d.quantity(t,i,*column) for p,column in columns.items()}
        occurrences=[p for p,q in values.items() if q['value'] is not None and Decimal(q['value'])!=0]
        if len(occurrences)>=2:
            rows.append({'key':t['table_id']+'_'+str(i+1),'item':label,'occurrences':len(occurrences),'periods':occurrences,'values':values,
                'interpretation':'该非经常项目在至少两个独立披露年度非零出现；提示关注扣非口径的解释力，不自动改判为经常性；不拆分合并披露项目'})
    return rows


def basis_changes(service,project,document_id=None,company=None,scope='consolidated',periods=None,focus=None):
    st=Statement(service,project,load_facts(service,project,document_id,company),scope,periods,document_id,company);d=Disclosure(st)
    tabs=[t for t in d.tabs if d.applies(t)]
    actual_scope=next(r['scope'] for r in st.facts if r['metric'] in ALIASES['revenue'])
    pairs,unknown=extract_adjustment_pairs(tabs,d.pages,d.doc,int(d.year),st.currency,actual_scope,st.periods[0].split('-',1)[1])
    # Use normalized restated facts as an additional path when there is only an
    # adjusted-after column; original figures must actually be in this project.
    allfacts=load_facts(service,project,company=st.company)
    by_id={t['table_id']:t for t in tabs}
    def version(r):
        ref=r['source_ref'];t=by_id.get(ref.get('table_id'))
        label=column_context(t,ref.get('row',1),ref.get('column')) if t else meta(r).get('column_label','')
        if re.search('调整后|調整後|重述后|重列後',label):return 'restated'
        if re.search('调整前|調整前|重述前|重列前',label):return 'original'
        return meta(r).get('restatement','original')
    for r in st.facts:
        if version(r)!='restated' or not dimensions_ok(r):continue
        metric=next((k for k,v in ALIASES.items() if r['metric'] in v),None) or basis_metric(meta(r).get('label','')) or r['metric']
        if any((p['metric'],p['period'],p['scope'])==(metric,r['period'],r['scope']) for p in pairs):continue
        before=[f for f in allfacts if f['company']==r['company'] and f['scope']==r['scope'] and f['metric']==r['metric'] and f['period']==r['period'] and f['currency']==r['currency'] and dimensions_ok(f) and version(f)=='original']
        current=[f for f in before if f['document_id']==d.doc];before=current or before
        original=record_quantity(before[0]) if before and len({x['value'] for x in before})==1 else cell(None,reason='缺少唯一原报数；未由差额或同比反推',sources=[x['source_ref'] for x in before])
        pairs.append({'metric':metric,'label':meta(r).get('label',metric),'period':r['period'],'scope':r['scope'],'original':original,'restated':record_quantity(r)})
    changes,ratios=quantify_restatement(pairs);markers=scan_basis_markers(d.pages,d.doc);repeated=repeated_nonrecurring(d)
    observations=[]
    for r in changes:
        if r['changed']:observations.append({'key':'change_'+r['key'],'finding':f'{r["period"]} {r["label"]} 重述减原报 {r["delta"]["value"]} {r["delta"]["unit"]}','basis':'adjustments.'+r['key']})
    for r in repeated:observations.append({'key':'repeat_'+r['key'],'finding':f'{compact(r["item"])}在 {", ".join(r["periods"])} 均非零，仍按披露非经常性列示','basis':'repeated_nonrecurring.'+r['key']})
    report_tables={}
    report_tables['markers']=table({k:col(v) for k,v in [('key','行键'),('kind','标记类型'),('status','原文状态'),('reason','识别依据'),('quote','原句'),('source','来源')]},[{'key':str(i),**r,'source':json.dumps(r['source'],ensure_ascii=False)} for i,r in enumerate(markers)])
    # Different dimensions must not share an amount column (EPS / ROE / money).
    amount_rows=[]
    for r in changes:
        dimension='percent' if r['original']['unit']=='%' else 'per_share' if r['original']['unit']=='元/股' else 'money'
        amount_rows.append({'key':r['key'],'metric':r['metric'],'label':r['label'],'period':r['period'],'scope':r['scope'],'changed':r['changed'],**{k+'_'+dimension:r[k] for k in ('original','restated','delta')}})
    cols={k:col(v) for k,v in [('key','行键'),('metric','指标'),('label','原披露项目'),('period','期间'),('scope','口径'),('changed','数值有变化')]}
    for dim,unit in [('money','百万元'),('percent','%'),('per_share','元/股')]:
        for k,label in [('original','调整前'),('restated','调整后'),('delta','调整后减前')]:cols[k+'_'+dim]=col(label,'个百分点' if k=='delta' and dim=='percent' else unit,st.currency if dim!='percent' else None)
    report_tables['adjustments']=table(cols,amount_rows)
    report_tables['ratio_impacts']=table({**{k:col(v) for k,v in [('key','行键'),('period','期间'),('scope','口径'),('ratio','比率')]},'original':col('原报比率','%'),'restated':col('重述比率','%'),'impact_pp':col('影响','个百分点')},ratios)
    periods=sorted({p for r in repeated for p in r['periods']},reverse=True)
    report_tables['repeated_nonrecurring']=table({'key':col('行键'),'item':col('原非经常项目'),'occurrences':col('非零年度数','个'),**{p:col(p,'百万元',st.currency) for p in periods},'interpretation':col('解释边界')},[{**{k:r[k] for k in ('key','item','interpretation')},
        'occurrences':cell(r['occurrences'],'个',sources=[q['source'] for q in r['values'].values()],formula='独立披露年度中非零金额的个数'),**r['values']} for r in repeated])
    report_tables['unrecognized']=table({k:col(v) for k,v in [('key','行键'),('item','原文项目'),('reason','原因'),('source','原格和来源')]},[{'key':str(i),**r,'source':json.dumps(r['source'],ensure_ascii=False)} for i,r in enumerate([*unknown,*d.unknown])])
    confirmed=any(not p['metric'].startswith('unrecognized:') for p in pairs) or any(x['status']=='restatement_disclosed' for x in markers)
    report_tables['summary']=table({'key':col('行键'),'restatement_detected':col('识别到重述依据'),'paired_rows':col('已识别调整数值行数','个',decimals=0),'note':col('识别边界')},[{'key':'basis','restatement_detected':confirmed,'paired_rows':len(pairs),'note':'原文标记不等于结论；未发现调整列/明确追溯声明时不报重述，调整行数不是调整金额。政策变更适用与数值影响分开。'}])
    report_tables['observations']=table({'key':col('行键'),'finding':col('确定性关系'),'basis':col('底稿')},observations)
    return {'title':st.company+' 口径变化与特殊损益底稿','periods':st.periods,'body':'保留政策、估计、差错、同控合并和重述原文标记及否定证据；量化原报与重述的同口径差额。多期非经常项目只提示，不重新分类。加权披露ROE与平均权益ROE分开。','tables':report_tables},allfacts

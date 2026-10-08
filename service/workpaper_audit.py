"""On-demand report arithmetic and label audit; source data is never changed."""
import itertools
import json
import re
from functools import reduce
from collections import defaultdict
from decimal import Decimal, localcontext

from .financial_workpapers import WorkpaperInputError, cell, col, table

EPS = ('eps','eps_reported','eps_basic','earnings_per_share')
PARENT = ('net_profit_parent','net_profit_attributable','profit_attributable_to_owners')
PE = ('pe','p_e','p_e_diluted')
MARGIN = ('gross_profit_margin','gross_margin','gp_margin')
SHARES = ('weighted_average_number_of_shares','weighted_average_shares','issued_shares','shares_outstanding','fully_diluted_no_of_shares_m','total_shares')
LOCATOR_DIMS = {'source_table','table_id','section','source_label','ordinal','source_coordinate'}


def load_research(service, project, document_id=None):
    service.store.project(project)
    with service.store.connect() as db:
        if not document_id:
            docs=[dict(r) for r in db.execute('SELECT DISTINCT d.document_id,d.original_name FROM research_records r JOIN documents d USING(document_id) WHERE r.project_id=? AND r.is_current=1',(project,))]
            if len(docs)!=1:raise WorkpaperInputError(f'请选择一份研报 document_id：{docs}')
            document_id=docs[0]['document_id']
        service.store.document(project,document_id)
        rows=[dict(r) for r in db.execute('SELECT * FROM research_records WHERE project_id=? AND document_id=? AND is_current=1',(project,document_id))]
        pages={r['page']:r['text'] for r in db.execute('SELECT page,text FROM pages WHERE document_id=?',(document_id,))}
        record=db.execute('SELECT profile_json FROM document_profiles WHERE project_id=? AND document_id=?',(project,document_id)).fetchone()
    for r in rows:
        r.update(json.loads(r.pop('record_json')))
        r['source_ref']=json.loads(r.pop('source_json'))
    return rows,pages,json.loads(record[0]) if record else {}


def ref(r):
    return {'record_id':r.get('record_id'), **{k:v for k,v in r['source_ref'].items() if k in ('document_id','page','table_id','row','column','cell','text')}}


def dims(r):
    dimensions={k:v for k,v in r.get('dimensions',{}).items() if k not in LOCATOR_DIMS}
    label=r.get('dimensions',{}).get('source_label','')
    # These fields sometimes carry the only segment identity. Strip a label only
    # when it is a known financial item, never simply because its key says "source".
    simple=re.sub(r'[^a-z\u4e00-\u9fff]','',re.sub(r'\([^)]*\)','',label).lower())
    generic={'revenue','sales','totalrevenue','netsales','yoygrowth','yoy','growth','netprofit','netprofitattributable','netprofitatt',
             'grossprofit','grossmargin','gpmargin','grossprofitmargin','eps','epsreported','pe','pediluted','netprofitgrowth',
             'revenuegrowth','operatingprofit','ebitda','epsgrowth','营业收入','营业收入增长率','归母净利润','净利润','净利润增长率','毛利率','每股收益'}
    if label and simple not in generic:dimensions['source_label']=label
    section=r.get('dimensions',{}).get('section','')
    if re.search(r'\bby\b|segment|分部|分地区|分产品',section,re.I):dimensions['section']=section
    return dimensions


def currency_in_source(r):
    text=str(r.get('raw_value',''))
    for marker,currency in [('HK$','HKD'),('US$','USD'),('RMB','CNY')]:
        if re.search(re.escape(marker)+r'\s*[-+]?\d',text):return currency+'/share' if r['metric'] in EPS+('target_price','market_price','current_price') else currency
    return r['currency']


def report_fx(records,anchor,pages):
    matches=[r for r in records if r['metric']=='exchange_rate' and r.get('entity_id')==anchor.get('entity_id')]
    if matches and len({r['value'] for r in matches})==1:
        context=pages.get(matches[0]['source_ref'].get('page'),'')
        if 'RMB mn' in context and 'value/share (HK$)' in context:return matches[0]
    return None


def identity(r):
    return (r.get('entity_id'),r.get('scope'),r.get('scenario','unspecified'),r['source_ref'].get('normalization',{}).get('statement'),json.dumps(dims(r),sort_keys=True,ensure_ascii=False))


def literal(r):
    norm=r['source_ref'].get('normalization',{})
    text=norm.get('numeric_span',{}).get('text')
    if not text:
        text=str(r.get('raw_value',''))
        if len(re.findall(r'\d[\d,]*(?:\.\d+)?',text))>1:
            label=r.get('dimensions',{}).get('source_label') or norm.get('column_label') or norm.get('label','')
            matches=re.findall(re.escape(label)+r'\s*([()\-+\d,.]+)\s*(?:%|$)',text,re.M|re.I) if label else []
            text=matches[0] if len(matches)==1 else ''
    match=re.search(r'[-+]?\d[\d,]*(?:\.\d+)?',text)
    return match.group(0).replace(',','') if match else None


def bounds(r):
    value=Decimal(r['value']);raw=literal(r)
    if r.get('exact_parameter'):return value,value
    if raw is None:return None
    scale=r['source_ref'].get('normalization',{}).get('scale')
    if scale is None:return None
    half=Decimal('0.5')*Decimal(10)**Decimal(Decimal(raw).as_tuple().exponent)*Decimal(str(scale))
    return value-half,value+half


def candidates(records, anchor, metrics, period=None, allow_global=False):
    matched=[r for r in records if r.get('value') is not None and r.get('metric') in metrics
             and r.get('entity_id')==anchor.get('entity_id') and r.get('scope')==anchor.get('scope')
             and r.get('scenario','unspecified')==anchor.get('scenario','unspecified')
             and (r.get('period')==(period or anchor.get('period')) or allow_global and r.get('period')=='unknown')
             and dims(r)==dims(anchor)]
    same_table=[r for r in matched if r['source_ref'].get('table_id')==anchor['source_ref'].get('table_id')]
    if same_table:matched=same_table
    elif not allow_global:
        same_page=[r for r in matched if r['source_ref'].get('page')==anchor['source_ref'].get('page')]
        if same_page:matched=same_page
    if len({(r['value'],r['currency']) for r in matched})==1:return matched[0]
    return None


class Audit:
    def __init__(self):self.groups=defaultdict(list);self.labels=[];self.sequence=0

    def check(self, kind, anchor, inputs, formula, unit, currency=None, reason=None, note=''):
        self.sequence+=1
        disclosed=Decimal(anchor['value']) if anchor.get('value') is not None else None
        calculated=low=high=delta=None
        status='无法复算' if reason or not all(inputs) else '精度未知'
        input_bounds=[bounds(r) if r else None for r in inputs]
        if not reason and all(inputs):
            vals=[Decimal(r['value']) for r in inputs]
            if any(r.get('currency')=='unknown' for r in inputs):reason='输入规范单位未知';status='无法复算'
            else:
                try:
                    calculated=formula(*vals)
                    delta=calculated-disclosed if disclosed is not None else None
                    if all(input_bounds):
                        values=[formula(*v) for v in itertools.product(*input_bounds)]
                        low,high=min(values),max(values)
                        disclosed_bounds=bounds(anchor)
                        if disclosed_bounds:
                            status='超出披露精度' if high<disclosed_bounds[0] or low>disclosed_bounds[1] else '舍入范围内'
                except (ZeroDivisionError,ArithmeticError):
                    reason='分母为零或区间跨越零，无法确定有效复算范围';status='无法复算'
        refs=[ref(r) for r in [anchor,*inputs] if r]
        key=f'{kind}_{anchor.get("period","unknown")}_{self.sequence}'
        self.groups[(unit,currency)].append({'key':key,'check':kind,'period':anchor.get('period'),
            'disclosed':cell(disclosed,unit,currency,[ref(anchor)]),'recomputed':cell(calculated,unit,currency,refs,kind,reason),
            'difference':cell(delta,unit,currency,refs),'rounding_low':cell(low,unit,currency,refs),'rounding_high':cell(high,unit,currency,refs),
            'status':status,'note':reason or note,'records':', '.join(r.get('record_id','source-text') for r in [anchor,*inputs] if r),
            'pages':', '.join(str(p) for p in sorted({r['page'] for r in refs if r.get('page')}))})

    def label(self,kind,records,detail,status='标注差异'):
        self.labels.append({'key':f'label_{len(self.labels)}','check':kind,'status':status,'detail':detail,
                            'records':', '.join(r.get('record_id','source-text') for r in records),
                            'pages':', '.join(str(p) for p in sorted({r['source_ref']['page'] for r in records}))})

    def report(self,title):
        tables={}
        for index,((unit,currency),rows) in enumerate(self.groups.items()):
            name='audit_'+str(index+1)
            columns={'key':col('行键'),'check':col('核对项目'),'period':col('期间')}
            columns.update({key:col(label,unit,currency) for key,label in [('disclosed','披露值'),('recomputed','复算值'),('difference','复算减披露'),('rounding_low','输入舍入下界'),('rounding_high','输入舍入上界')]})
            columns.update({'status':col('披露精度判断'),'note':col('依据或缺项'),'records':col('涉及记录'),'pages':col('原页码')})
            tables[name]=table(columns,rows)
        tables['labels']=table({'key':col('行键'),'check':col('核对项目'),'status':col('状态'),'detail':col('差异'),'records':col('涉及记录'),'pages':col('原页码')},self.labels)
        findings=[]
        for name,t in tables.items():
            for row in t['rows']:
                if row['status'] in ('超出披露精度','标注差异'):
                    magnitude=abs(Decimal(row['difference']['value'])) if row.get('difference',{}).get('value') is not None else Decimal('Infinity')
                    findings.append((magnitude,{'key':row['key'],'finding':row.get('detail') or f'{row["check"]} {row.get("period","")}：{row["status"]}，差额见底稿','basis':name+'.'+row['key']}))
        tables['observations']=table({'key':col('行键'),'finding':col('确定性发现；按各原单位差额幅度排列，不比较经济重要性'),'basis':col('对应底稿')},[r for _,r in sorted(findings,key=lambda x:x[0],reverse=True)])
        return {'title':title+' 内部勾稽审计','body':'按披露末位的半单位传播舍入区间；舍入范围内不证明金融口径相同。无法复算项保留原记录与缺项。审计不改写来源，不自动进入入库流程。','tables':tables}


def audit_records(records,pages,profile):
    audit=Audit()
    numeric=[r for r in records if r.get('value') is not None and r.get('metric')]
    # Currency/period labels are checked against the literal source; no normalization write-back.
    for r in numeric:
        raw=str(r.get('raw_value',''))
        if r['metric'] in ('market_price','target_price'):
            match=re.search(r'(HK\$|US\$|RMB)\s*'+re.escape(str(Decimal(r['value']))),raw,re.I)
            if match:
                stated={'HK$':'HKD','US$':'USD','RMB':'CNY'}[match.group(1).upper()]
                if r['currency']!=stated+'/share':audit.label('币种标注',[r],f'原文 {match.group(1)}，记录币种 {r["currency"]}；本审计不改写原记录')
        if r['metric'] in EPS:
            profit=candidates(numeric,r,PARENT)
            shares=candidates(numeric,r,SHARES)
            audit.check('EPS与归母利润/同年度披露股数',r,[profit,shares],lambda a,b:a/b,'元/股',r['currency'].split('/')[0],
                        reason=None if profit and shares else '缺少同口径归母利润或同年度加权股数；报告日总股本不替代历史加权股数')
            if profit and shares and 'weighted_average' not in shares['metric']:
                latest=audit.groups[('元/股',r['currency'].split('/')[0])][-1]
                latest['status']='股数口径待核实'
                latest['note']='机械复算使用报告披露总股数；不是加权平均股数，不能据此认定EPS错误'
        if r['metric'] in ('dcf_value_per_share','fully_diluted_equity_value_share_hk'):
            equity=candidates(numeric,r,('dcf_equity_value','fully_diluted_equity_value_end_23e'),allow_global=True)
            shares=candidates(numeric,r,('fully_diluted_no_of_shares_m','issued_shares'),allow_global=True)
            fx=report_fx(numeric,r,pages)
            audit.check('DCF每股值=股权价值/股数×汇率',r,[equity,shares,fx],lambda a,b,c:a/b*c,'元/股','HKD',
                        reason=None if equity and shares and fx else '缺少同估值口径股权价值、股数或定向汇率')
        if r['metric'] in PE and not any(k in dims(r) for k in ('valuation_method','method')):
            eps=candidates(numeric,r,EPS)
            price=candidates(numeric,r,('market_price','current_price','share_price'),allow_global=True)
            compatible=eps and price and eps['currency']==currency_in_source(price)
            fx=report_fx(numeric,r,pages) if eps and price and eps['currency']=='CNY/share' and currency_in_source(price)=='HKD/share' else None
            audit.check('P/E=价格/EPS'+('（报告汇率换算）' if fx else ''),r,[price,eps]+([fx] if fx else []),lambda a,b,c=Decimal(1):a/(b*c),'倍',
                        reason=None if compatible or fx else '缺同口径股价/EPS或两者币种不同；不隐含换汇',note='股价币种按原文识别；记录标注冲突另列，计算不写回')
        if r['metric'] in MARGIN:
            rev=candidates(numeric,r,('revenue',));cost=candidates(numeric,r,('cost_of_goods_sold','cost_of_sales','cost_of_revenue','operating_cost'))
            audit.check('毛利率=(收入-|成本|)/收入',r,[rev,cost],lambda a,b:(a-abs(b))/a*100,'%',
                        reason=None if rev and cost and rev['currency']==cost['currency'] else '缺少同范围收入与成本，或币种不一致')
        growth={'revenue_growth':('revenue',),'revenue_yoy':('revenue',),'net_profit_growth':('net_profit',),'net_profit_parent_growth':PARENT,'net_profit_parent_yoy':PARENT,'eps_growth':EPS,'np_growth':('net_profit',)}
        if r['metric'] in growth and re.fullmatch(r'\d{4}-FY',r.get('period','')):
            current=candidates(numeric,r,growth[r['metric']]);previous=candidates(numeric,r,growth[r['metric']],str(int(r['period'][:4])-1)+'-FY')
            audit.check('相邻年度增速',r,[current,previous],lambda a,b:(a-b)/b*100,'%',reason=None if current and previous and current['currency']==previous['currency'] else '缺少同范围相邻年取值或币种不一致')
    # Same metric and financial scope, different source pages. Distinct scenarios/segments stay separate.
    groups=defaultdict(list)
    for r in numeric:groups[(identity(r),r['metric'],r.get('period'),r.get('data_kind'))].append(r)
    for rs in groups.values():
        if any(str(v).lower() in ('others','other','其他','其它') for v in dims(rs[0]).values()) and len({r['source_ref'].get('table_id') for r in rs})>1:
            audit.label('剩余分类维度未明',rs,f'{rs[0]["metric"]} 的“其他”来自不同分类表；地域、渠道与产品的剩余项不能相互比较','无法复算')
            continue
        if rs[0].get('period') in (None,'','unknown') and len({r['source_ref'].get('page') for r in rs})>1:
            audit.label('跨页期间未明',rs,f'{rs[0]["metric"]} 有多个无确定期间的来源，不能判断为同一时点的数值矛盾','无法复算')
            continue
        for a,b in itertools.combinations(rs,2):
            if a['source_ref'].get('page')==b['source_ref'].get('page'):continue
            if a['currency']!=b['currency']:
                audit.label('同指标单位/币种',[a,b],f'{a["metric"]} {a["period"]}：{a["currency"]} 对 {b["currency"]}')
            elif a['value']!=b['value']:
                currency=a['currency']
                if currency in ('percent','倍','multiple','股','shares'):
                    unit={'percent':'%','倍':'倍','multiple':'倍','股':'股','shares':'股'}[currency];money=None
                elif re.fullmatch(r'[A-Z]{3}(?:/share)?',currency):unit='元/股' if currency.endswith('/share') else '元';money=currency.split('/')[0]
                else:
                    audit.label('同指标取值（单位未明）',[a,b],f'{a["metric"]} {a["period"]}：{a["value"]} 对 {b["value"]}');continue
                audit.check('跨页同指标 '+a['metric'],a,[b],lambda v:v,unit,money,note='先核验原页口径；差额为另一页减本页')
    for r in numeric:
        label=r.get('dimensions',{}).get('source_label') or r['source_ref'].get('normalization',{}).get('label','')
        match=re.search(r'DCF\s*\(?\s*(\d{2,4})E\s*[-–]\s*(\d{2,4})E',label,re.I)
        if match:
            stated=[int(y)+(2000 if len(y)==2 else 0) for y in match.groups()]
            forecast=[q for q in numeric if q['metric'] in ('unleveraged_fcf','fcf','free_cash_flow') and q.get('data_kind')=='analyst_forecast' and q.get('entity_id')==r.get('entity_id') and q['source_ref'].get('page')==r['source_ref'].get('page') and re.fullmatch(r'\d{4}-FY',q.get('period',''))]
            years=sorted({int(q['period'][:4]) for q in forecast})
            if years and stated!=[years[0],years[-1]]:audit.label('DCF标题预测年份',[r,*forecast],f'DCF 标题为 {stated[0]}–{stated[1]}，同页预测现金流列为 {years[0]}–{years[-1]}；标题与预测列不一致')
    audit_targets(audit,numeric,pages)
    audit_chinese_valuation(audit,numeric,pages,profile)
    return audit.report(profile.get('title','研报'))


def audit_chinese_valuation(audit,records,pages,profile):
    names={e['name'] for e in profile.get('entities',[]) if e.get('kind')=='company'}
    subjects={r['entity_id'] for r in records if r.get('entity',{}).get('name') in names}
    for page,text in pages.items():
        pattern=r'给予其?(\d{4})年(\d+(?:\.\d+)?)[-–](\d+(?:\.\d+)?)x?PE[，,]合理价格区间为(\d+(?:\.\d+)?)[-–](\d+(?:\.\d+)?)元'
        match=re.search(pattern,re.sub(r'\s+','',text),re.I)
        if not match or len(subjects)!=1:continue
        period=match[1]+'-FY'
        eps_records=[r for r in records if r['metric'] in EPS and r['entity_id'] in subjects and r['period']==period and r['currency']=='CNY/share' and r.get('scenario','unspecified') in ('unspecified','base','baseline')]
        eps=eps_records[0] if eps_records and len({r['value'] for r in eps_records})==1 else None
        if not eps:continue
        for bound,multiple,target in [('下限',match[2],match[4]),('上限',match[3],match[5])]:
            src={'document_id':eps['document_id'],'page':page,'text':text,'normalization':{'scale':'1'}}
            target_record={**eps,'record_id':f'source-text-{page}-{bound}','value':target,'raw_value':target,'source_ref':src}
            pe={**target_record,'record_id':f'source-text-{page}-pe-{bound}','value':multiple,'raw_value':multiple,'currency':'倍','exact_parameter':True}
            audit.check('目标价区间'+bound+'=EPS×目标PE',target_record,[eps,pe],lambda a,b:a*b,'元/股','CNY',note='按原页明确的PE区间端点复算；EPS保留披露舍入精度')
    for r in records:
        if r['metric'].startswith('dcf_value_per_share_'):
            fcf=[q for q in records if q['metric']=='free_cash_flow_firm' and q['entity_id']==r['entity_id'] and q.get('data_kind')=='analyst_forecast']
            audit.check('DCF敏感性单元复算',r,[],lambda:Decimal(0),'元/股',r['currency'].split('/')[0],
                        reason='已披露FCFF期间：'+', '.join(sorted({q['period'] for q in fcf}))+'；缺完整过渡期现金流和折现时点约定，不能仅凭WACC/g倒推')


def audit_targets(audit,records,pages):
    targets=[r for r in records if r['metric']=='target_price']
    for target in targets:
        if not re.fullmatch(r'[A-Z]{3}/share',target['currency']):
            audit.label('目标价单位',[target],f'原记录值 {target["value"]}，单位 {target["currency"]}；缺少可确定的每股币种，无法复算','无法复算')
            continue
        p=target['source_ref'].get('page');text=pages.get(p,'')
        method=re.search(r'(?:based on|apply a)\s*(\d+(?:\.\d+)?)\s*x\s*FY(\d{2,4})E\s*P/E',text,re.I)
        if not method:
            audit.check('目标价估值复算',target,[],lambda:Decimal(0),'元/股',target['currency'].split('/')[0] if '/share' in target['currency'] else None,reason='原页未提供可确定解析的估值方法和完整参数')
            continue
        year=int(method[2])+(2000 if len(method[2])==2 else 0)
        eps=candidates(records,{**target,'dimensions':{}},EPS,f'{year}-FY',allow_global=True)
        multiple={'record_id':'source-text-pe','value':method[1],'currency':'倍','raw_value':method[1],'exact_parameter':True,
                  'source_ref':{'document_id':target['document_id'],'page':p,'text':method[0],'normalization':{'scale':'1'}}}
        money='HKD' if re.search(r'TP of HK\$',text) else target['currency'].split('/')[0]
        # FX direction is evidenced by the DCF table's RMB equity and HK$ per-share labels.
        fx=None
        if eps and eps['currency']!=money+'/share':
            matches=[r for r in records if r['metric']=='exchange_rate' and r.get('entity_id')==target.get('entity_id')]
            if len({r['value'] for r in matches})==1 and matches:
                candidate=matches[0];context=pages.get(candidate['source_ref'].get('page'),'')
                if money=='HKD' and eps['currency']=='CNY/share' and 'RMB mn' in context and 'value/share (HK$)' in context:fx=candidate
            reason=None if fx else 'EPS与目标价币种不同，缺有来源的定向汇率'
        else:reason=None if eps else '缺少估值年度 EPS'
        audit.check('目标价=EPS×目标PE'+('×报告汇率' if fx else ''),target,[eps,multiple]+([fx] if fx else []),lambda *v:reduce(lambda a,b:a*b,v,Decimal(1)),
                    '元/股',money,reason=reason,note='目标PE是方法参数，EPS及汇率按披露精度传播区间；使用原文币种，保留入库标注差异')


def report_audit(service,project,document_id=None,periods=None,**_):
    records,pages,profile=load_research(service,project,document_id)
    from .workpaper_period_selection import normalize_periods
    available={r['period'] for r in records if r.get('period')}
    selected=normalize_periods(periods,available) if periods or available else []
    with localcontext() as ctx:
        ctx.prec=40
        report=audit_records(records,pages,profile);report['periods']=selected
        return report,records

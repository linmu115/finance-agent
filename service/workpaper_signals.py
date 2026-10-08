"""Nine families of deterministic screening signals, never causal conclusions."""
from .standard_metrics import WORKPAPER_ALIASES as ALIASES
import json
import re
from datetime import date
from decimal import Decimal

from .financial_workpapers import cell, col, table, meta, dimensions_ok
from .analysis_report import record_quantity
from .workpaper_annual import compact
from .workpaper_analyst import AnalystData, calc, delta, growth, ratio, value, unknown, locators

DEBT_CONCEPTS=('short_term_borrowings','long_term_borrowings','bonds_payable','lease_liabilities',
               'bank_and_other_borrowings_current','bank_and_other_borrowings_non_current','lease_liabilities_current','lease_liabilities_non_current')

CFA = 'https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/evaluating-quality-financial-reports'
POLICY = ('本项目经验阈值 v1（2026-10-08），用于初筛，未经行业校准；不是文献给定的通用警戒线。'
          '方法参考 CFA Institute Evaluating Quality of Financial Reports：跨期变化、财务比率与利润/现金流差异；'+CFA)


def note_ratios(a):
    """Only uniquely identified, same-scope aging/provision tables; no blank=0."""
    aging=[];provisions=[]
    for t in a.d.tabs:
        if not t['rows'] or not a.d.applies(t):continue
        rows=t['rows'];head=' '.join(compact(c) for row in rows[:2] for c in row)
        if '账龄' in compact(rows[0][0]) and '期末账面余额' in head and '期初账面余额' in head:
            # Distinguish trade receivables from other receivables / prepayments
            # by the last note heading preceding the physical aging heading.
            page=compact(a.d.pages.get(t['page'],''));before=page.split('按账龄披露')[0]
            headings=list(re.finditer(r'\d+[、.](应收账款|其他应收款|预付款项)',before))
            if not headings or headings[-1][1]!='应收账款':continue
            totals=[i for i,r in enumerate(rows) if compact(r[0]) in ('合计','合計')]
            old=[i for i,r in enumerate(rows) if re.fullmatch(r'(?:[1-9一二三四五六七八九]至[2-9二三四五六七八九]年|[1-9一二三四五六七八九]年以上)',compact(r[0]))]
            if len(totals)!=1 or not old:continue
            qs=[]
            for c in (1,2):
                numerator=calc([a.d.quantity(t,i,c,rows[0][c]) for i in old],lambda *v:sum(v),formula='一年以上账龄各互斥区间金额合计')
                qs.append(ratio(numerator,a.d.quantity(t,totals[0],c,rows[0][c]),'一年以上应收账面余额/应收账面余额合计*100'))
            aging.append(qs)
        if re.search('存货跌价准备|存貨跌價',head) and all(s in head for s in ('期末余额','期初余额','账面余额')):
            totals=[i for i,r in enumerate(rows) if compact(r[0])=='合计']
            if len(totals)!=1:continue
            positions=[];current=None
            for c in range(1,len(rows[0])):
                h=compact(rows[0][c])
                if '期末' in h:current=0
                if '期初' in h:current=1
                if c<len(rows[1]):positions.append((current,c,compact(rows[1][c])))
            qs=[]
            for side in (0,1):
                gross=[c for s,c,h in positions if s==side and h=='账面余额']
                reserve=[c for s,c,h in positions if s==side and '跌价准备' in h]
                if len(gross)==len(reserve)==1:
                    qs.append(ratio(a.d.quantity(t,totals[0],reserve[0],'期末' if side==0 else '期初'),a.d.quantity(t,totals[0],gross[0],'期末' if side==0 else '期初'),'期末跌价准备余额/存货账面余额*100；是余额覆盖率，不是本期费用计提率'))
            if len(qs)==2:provisions.append(qs)
    return ((aging[0] if len(aging)==1 else [unknown('未找到唯一同口径一年以上应收账龄表','%')]*2),
            (provisions[0] if len(provisions)==1 else [unknown('未找到唯一同口径存货原值与跌价准备两期表','%')]*2))


def audit_signals(a):
    results={}
    pages=a.d.pages
    for p,text in pages.items():
        # Explicit opinion statements, not generic descriptions of auditors' duties.
        for pattern,label,trigger in [(r'(?:出具了?|發表了?).{0,35}?(?:标准|標準)?无保留意见.{0,12}?审计报告','无保留意见',False),
                                      (r'(?:出具了?|發表了?).{0,35}?(?:保留意见|否定意见|无法表示意见).{0,12}?审计报告','非无保留意见',True)]:
            m=re.search(pattern,compact(text))
            if m and not ('无保留意见' in m[0] and trigger):results['opinion']=(label,trigger,[a.source_text(p,m[0])],'')
        m=re.search(r'(?:是否改聘会计师事务所|会计师事务所.{0,12}变更情况).{0,70}',compact(text))
        if m:
            if re.search(r'√是|√适用',m[0]):results['auditor_change']=('披露改聘',True,[a.source_text(p,m[0])],'')
            elif re.search(r'√否|√不适用',m[0]):results['auditor_change']=('披露未改聘',False,[a.source_text(p,m[0])],'')
        m=re.search(r'(?:审议并通过|審議並通過).{0,30}(?:变更会计师事务所|改聘会计师事务所).{0,150}',compact(text))
        if m:results['auditor_change']=('披露改聘',True,[a.source_text(p,m[0])],'')
        # A heading is evidence of an actual emphasis paragraph. A mention in a
        # template/question or key audit matter is not.
        m=re.search(r'(?:^|\n)\s*(?:[一二三四五六七八九]+[、. ]\s*)?(强调事项|強調事項|Emphasis of Matter)\s*(?:\n|$)',text,re.I)
        if m:results['emphasis']=('强调事项段',True,[a.source_text(p,text[m.start():m.end()+600])],'')
    if 'opinion' not in results:
        for p,text in pages.items():
            if re.search(r'unaudited|未经审计|未經審核',text,re.I):
                results['opinion']=('未经审计中期财务信息',None,[a.source_text(p,next(line for line in text.splitlines() if re.search(r'unaudited|未经审计|未經審核',line,re.I)))],'未披露本期审计意见；未经审计不等于非无保留意见');break
    # Negative evidence only when the complete audit report section is present.
    starts=[p for p,text in pages.items() if re.search('一、审计意见',compact(text))]
    ends=[p for p,text in pages.items() if re.search('合并资产负债表',compact(text)) and any(p>s for s in starts)]
    if 'emphasis' not in results and len(starts)==1 and ends:
        end=min(p for p in ends if p>starts[0]);refs=[a.source_text(p,text,search='完整审计报告章节检索强调事项标题') for p,text in pages.items() if starts[0]<=p<end]
        results['emphasis']=('完整审计报告未检出强调事项标题',False,refs,'')
    return results


def inventory_charge_rates(a):
    """Period expense additions are distinct from an allowance balance.

    Ratio denominator is average gross inventory over the same period. Opening
    balance dated on period start is allowed only when explicitly labelled as
    opening, never as a substitute for a prior-year period expense.
    """
    def total(r):
        dims=r.get('dimensions') or {}
        return all(k in ('source_table','financial_item') or str(v).lower() in ('total','合计','合計') for k,v in dims.items())
    def unique(rs,reason):
        if rs and len({r['value'] for r in rs})==1 and all(r.get('quality')!='conflict' for r in rs):return record_quantity(rs[0])
        return cell(None,'元',a.currency,sources=[record_quantity(r)['source'] for r in rs],reason=reason if not rs else '同口径存货披露存在冲突')
    rows=[]
    for p in a.ps:
        start,end=a.window(p)
        rs=[r for r in a.records if total(r) and r['currency']==a.currency]
        charges=unique([r for r in rs if r['period']==p and r['metric'] in ALIASES['inventory_charge']],f'{p} 缺少同口径存货跌价本期计提合计；净减值损失或准备余额不能替代')
        opening=unique([r for r in rs if r['period']==start and r['metric'] in ALIASES['inventory_gross_opening']],f'{p} 缺少期初存货账面原值')
        closing=unique([r for r in rs if r['period']==end and r['metric'] in ALIASES['inventory_gross_closing']],f'{p} 缺少期末存货账面原值')
        avg=calc([opening,closing],lambda x,y:(x+y)/2,formula='同期间期初期末存货账面原值平均')
        rate=ratio(charges,avg,'当期存货跌价准备计提发生额/平均存货账面原值*100；不是期末准备余额覆盖率，未年化')
        rows.append({'key':p,'period':p,'charge':charges,'average_gross_inventory':avg,'value':rate,'missing':rate['source'].get('missing_reason') or ''})
    return rows


def overdue_ratios(a,p):
    """Invoice age and days past due are different bases; never combine them."""
    qs=[]
    for begin in (False,True):
        start,end=a.window(p)
        when=end
        if begin:
            from datetime import timedelta
            when=str(date.fromisoformat(start)-timedelta(days=1)) if start else None
        rs=[r for r in a.records if r['period']==when and r['metric'] in ALIASES['receivables_gross']
            and 'aging_bucket' in (r.get('dimensions') or {})
            and re.search('trade receivables',a.d.pages.get(r['source_ref'].get('page'),''),re.I)]
        buckets={}
        for r in rs:buckets.setdefault(compact(r['dimensions']['aging_bucket']).lower(),[]).append(r)
        over=[r for k,vs in buckets.items() if re.fullmatch(r'over_?12_?months_?past_?due',k) for r in vs]
        totals=[r for k,vs in buckets.items() if k=='total' for r in vs]
        if len(over)==len(totals)==1:qs.append(ratio(record_quantity(over[0]),record_quantity(totals[0]),'逾期超过12个月应收账面原值/合计*100；不是发票账龄'))
        else:qs.append(unknown('缺少唯一同口径逾期超过12个月应收及总额','%'))
    return qs


def anomaly_signals(service,project,document_id=None,company=None,scope='consolidated',periods=None,focus=None,_analysis=None):
    a=_analysis or AnalystData(service,project,document_id,company,scope,periods,focus)
    ps=a.ps;current=ps[0];previous=ps[1] if len(ps)>1 else None
    rows=[]
    def add(key,family,label,q,threshold,trigger,basis,source_policy=POLICY,extra=''):
        known=q['value'] is not None
        refs=locators(q)
        rows.append({'key':key,'family':family,'signal':label,'value':q,'baseline':basis,'threshold':threshold,
                     'threshold_source':source_policy,'triggered':'是' if known and trigger(value(q)) else '否' if known else '未知',
                     'evidence':json.dumps(refs,ensure_ascii=False),'missing':q['source'].get('missing_reason') or extra})
    inc=lambda k,p:a.pick(k,p,'income') if p else unknown('未指定可比期间')
    series=[]
    for p in ps:
        np=inc('net_profit',p);cfo=a.pick('cfo',p,'cashflow')
        conversion=ratio(cfo,np,'CFO/合并净利润；只对正利润计算','ratio')
        add(p+'_cash_conversion','利润与现金流','CFO/合并净利润',conversion,'< 1',lambda v:v<1,p+'；同期间合并利润与现金流')
        avg=calc([a.balance('assets',p,True),a.balance('assets',p)],lambda x,y:(x+y)/2,formula='(期初总资产+期末总资产)/2')
        accrual=ratio(delta(np,cfo),avg,'(合并净利润-CFO)/平均总资产*100')
        add(p+'_accrual','利润与现金流','应计比率',accrual,'> 10%',lambda v:v>10,p+'；未年化')
        sign=calc([np,cfo],lambda x,y:int(x>0 and y<0),'个','净利润>0 且 CFO<0；1=方向背离')
        add(p+'_profit_cash_sign','利润与现金流','净利润为正而CFO为负',sign,'= 1',lambda v:v==1,p,'数学符号关系，不是经验阈值')
        series.append(conversion)
    count=0;missing=False
    # Count consecutive same-window years from the newest period. A gap is not a
    # continuing sequence; an unavailable intervening ratio remains unknown.
    for i,q in enumerate(series):
        if i and (int(ps[i-1][:4])-int(ps[i][:4])!=1 or ps[i-1][4:]!=ps[i][4:]):missing=True;break
        if q['value'] is None:missing=True;break
        if value(q)>=1:break
        count+=1
    run=cell(None if missing else count,'个',sources=[q['source'] for q in series],formula='从最新期开始按相邻可比年度观察 CFO/正合并净利润<1 的期数',reason='期间不相邻或序列中存在缺值，期数未知' if missing else None)
    add('cash_divergence_run','利润与现金流','利润现金转化不足观察期数',run,'>= 2 个可比期间',lambda v:v>=2,'同报告可用比较列；不足三期不判断持续性，观察窗之外未知')
    for key,family,flow,days in [('receivables','应收','revenue','dso'),('inventory','存货','cogs','dio')]:
        # For interim reports year-end balance growth is NOT YoY. Require the
        # same date one year earlier for comparison with income growth.
        bg=growth(a.balance(key,current),a.balance(key,current,year_ago=True))
        fg=growth(calc([inc(flow,current)],abs,formula='费用取绝对金额'),calc([inc(flow,previous)],abs,formula='费用取绝对金额'))
        gap=delta(bg,fg,'个百分点')
        add(key+'_growth_gap',family,family+'同比增速减'+('收入' if flow=='revenue' else '成本')+'同比增速',gap,'> 20 个百分点',lambda v:v>20,f'{current} 对 {previous}；余额须为同日同比，不能用年初替代去年同期')
        cq=a.annual_row('cash_quality',current).get(days,unknown('缺本期周转天数','天'))
        pq=a.annual_row('cash_quality',previous).get(days,unknown('缺比较期周转天数','天'))
        add(key+'_days_change',family,family+'周转天数变化',delta(cq,pq,'天'),'> 10 天',lambda v:v>10,f'{current} 对 {previous}；期初期末平均余额，实际期间天数；收入/成本代理')
    aging,provision=note_ratios(a)
    add('receivables_aging_change','应收','一年以上应收账龄占比变化',delta(*aging,'个百分点'),'> 5 个百分点',lambda v:v>5,'期末对期初；账面原值口径')
    overdue=overdue_ratios(a,current)
    add('receivables_overdue_change','应收','逾期超过一年应收占比变化',delta(*overdue,'个百分点'),'> 5 个百分点',lambda v:v>5,'期末对期初；逾期账龄，不与发票账龄混用')
    add('inventory_provision_change','存货','存货跌价准备余额覆盖率变化',delta(*provision,'个百分点'),'绝对变化 > 2 个百分点',lambda v:abs(v)>2,'期末对期初；准备余额/账面原值，不等于本期费用计提率')
    inventory_rates=inventory_charge_rates(a)
    current_rate=inventory_rates[0]['value'];prior_rate=inventory_rates[1]['value'] if len(inventory_rates)>1 else unknown('缺少比较期存货计提率','%')
    add('inventory_charge_rate_change','存货','存货跌价准备本期计提率变化',delta(current_rate,prior_rate,'个百分点'),'绝对变化 > 2 个百分点',lambda v:abs(v)>2,
        f'{current} 对 {previous}；计提发生额/同期间平均存货原值；与余额覆盖率分别列示')
    for key,label in [('other_receivables','其他应收款'),('prepayments','预付款项'),('other_noncurrent','其他非流动资产')]:
        q=a.balance(key,current)
        add(key+'_asset_share','其他资产异动',label+'占总资产比例',ratio(q,a.balance('assets',current)),'> 10%',lambda v:v>10,current+'期末')
        add(key+'_growth','其他资产异动',label+'较期初增速',growth(q,a.balance(key,current,True)),'绝对变化 > 50%',lambda v:abs(v)>50,current+'期末对期初（不是中报同比）')
    cash=a.balance('cash_balance',current);assets=a.balance('assets',current)
    debt_q=[a.balance(k,current) for k in DEBT_CONCEPTS]
    disclosed=[q for q in debt_q if q['value'] is not None]
    debt=calc(disclosed,lambda *v:sum(v),formula='已披露借款、应付债券、租赁负债之和；没有把一年内到期非流动负债整体视为有息') if disclosed else unknown('没有可定位有息负债披露项目')
    cash_share=ratio(cash,assets);debt_share=ratio(debt,assets)
    minimum=calc([cash_share,debt_share],min,'%', 'min(货币资金或现金等价物/总资产,已识别融资负债/总资产)*100')
    debt_note='负债为已识别借款/债券/租赁负债下限，未计无法拆分的一年内到期非流动负债及未识别融资；现金使用主表货币资金或现金及等价物。'
    add('cash_debt_high','存贷双高','现金与融资负债占资产比例的较小值',minimum,'两者均 > 20%',lambda v:v>20,current+'期末；'+debt_note)
    if value(cash_share) is not None and value(cash_share)>20 and value(debt_share) is not None and value(debt_share)<=20:
        rows[-1].update(triggered='未知',missing='现金比例达到阈值，但仅有融资负债下限，不能据此判定完整有息负债未达阈值')
    add('cash_asset_share','存贷双高','现金占资产比例',cash_share,'> 20%',lambda v:v>20,current+'期末；单项达到阈值不等于存贷双高')
    add('debt_asset_share','存贷双高','已识别融资负债占资产比例',debt_share,'> 20%',lambda v:v>20,current+'期末；'+debt_note)
    interest=[r for r in a.records if r['period']==current and r['metric'] in ALIASES['interest_income'] and meta(r).get('statement')=='income'
              and ('财务费用' in str(r.get('dimensions')) or dimensions_ok(r))]
    if not interest:
        interest=[r for r in a.records if r['period']==current and meta(r).get('statement')=='notes' and dimensions_ok(r)
                  and re.fullmatch(r'Interest income on (?:bank deposits|cash at banks)',meta(r).get('label',''),re.I)]
    iq=record_quantity(interest[0]) if interest and len({r['value'] for r in interest})==1 else unknown('缺少唯一应计利息收入；不以现金收息或财务净收益替代')
    average=calc([a.balance('cash_balance',current,True),cash],lambda x,y:(x+y)/2,formula='(期初现金余额+期末现金余额)/2')
    start,end=a.window(current)
    days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1 if start and end else None
    yr=calc([iq,average],lambda x,y:x/y*Decimal(365)/days*100,'%', '应计利息收入/平均主表现金余额*365/期间天数*100（代理，未含其他科目定期存款）',(1,)) if days else unknown('缺少期间天数','%')
    add('interest_yield','存贷双高','隐含年化利息收益率',yr,'< 1%',lambda v:v<1,'平均余额代理；利息收入可能对应其他科目存款，须核对资产范围')
    qs={k:a.quarters(k) for k in ('revenue','parent_profit','cfo')}
    for key,label in [('revenue','收入'),('parent_profit','归母净利润')]:
        annual=inc(key,current)
        add('q4_'+key+'_share','季度集中','Q4'+label+'占全年比例',ratio(qs[key][3],annual),'绝对比例 > 40%',lambda v:abs(v)>40,current+'全年；全年须为正，非正时比例未知')
    for key,label in [('parent_profit','归母净利润'),('cfo','CFO')]:
        total=a.first_three_quarters(key)
        sign=calc([qs[key][3],total],lambda x,y:int(x*y<0),'个','Q4×前三季合计<0；1=符号相反')
        add('q4_'+key+'_direction','季度集中','Q4'+label+'与前三季合计方向相反',sign,'= 1',lambda v:v==1,current+'；N2期间函数：单季披露或同口径累计差额','数学符号关系，不是经验阈值')
    sign=calc([qs['parent_profit'][3],qs['cfo'][3]],lambda x,y:int(x*y<0),'个','Q4归母净利润×Q4CFO<0；仅比较方向，归母与合并不算转化率')
    add('q4_profit_cash_sign','季度集中','Q4归母利润与合并CFO方向相反',sign,'= 1',lambda v:v==1,current+'；归母利润/合并现金仅比较方向','数学符号关系，不是经验阈值')
    for key,label in [('asset_impairment','资产减值'),('credit_impairment','信用减值')]:
        amounts=[inc(key,p) for p in (current,previous)]
        if key=='credit_impairment' and all(q['value'] is None for q in amounts):
            amounts=[inc('impairment',p) for p in (current,previous)]
            label='金融/合同资产信用减值'
        change=calc(amounts,lambda x,y:(x-y)/abs(y)*100,'%', '(本期有符号损益-比较期有符号损益)/abs(比较期)*100') if value(amounts[1]) not in (None,0) else unknown('缺少非零可比减值损益','%')
        add(key+'_change','减值与商誉',label+'损益波动',change,'绝对变化 > 50%',lambda v:abs(v)>50,f'{current} 对 {previous}；损益原符号')
    add('goodwill_equity_share','减值与商誉','商誉净值占合并净资产',ratio(a.balance('goodwill',current),a.balance('equity',current)),'> 30%',lambda v:v>30,current+'期末；合并净资产须为正')
    for p in ps:
        nr=a.annual_row('deducted_profit',p).get('share',unknown('缺同口径非经常损益与归母利润','%'))
        if value(inc('parent_profit',p)) is not None and value(inc('parent_profit',p))<=0:nr=unknown('归母利润非正，依赖比例不可解释；原值保留于K1','%')
        add(p+'_nonrecurring_share','非经常性损益依赖','非经常性损益占归母净利润',nr,'> 20%',lambda v:v>20,p+'；各可比期间独立列示')
    if previous:
        q=delta(a.annual_row('deducted_profit',current).get('share',unknown('缺本期比例','%')),a.annual_row('deducted_profit',previous).get('share',unknown('缺上期比例','%')),'个百分点')
        add('nonrecurring_share_change','非经常性损益依赖','非经常性损益依赖比例变化',q,'上升 > 10 个百分点',lambda v:v>10,f'{current} 对 {previous}')
    audit=audit_signals(a)
    for key,label in [('opinion','审计意见类型'),('emphasis','强调事项段'),('auditor_change','会计师事务所变更')]:
        description,trigger,refs,reason=audit.get(key,('未知',None,[],'原文未找到可确定的本期披露；未检出不当作没有'))
        q=cell(None if trigger is None else int(trigger),'个',sources=refs,formula=description,reason=reason or None)
        add('audit_'+key,'审计与治理',label,q,'明确披露非无保留/强调事项/变更则标记；不推断原因',lambda v:v==1,description,'披露事实分类；强调事项不等于非无保留意见，未经审计不是审计异常。')
        rows[-1]['evidence']=json.dumps(refs,ensure_ascii=False)
    observations=[{'key':r['key'],'finding':r['signal']+'：'+str(r['value']['value'])+' '+r['value']['unit']+'；达到筛选条件 '+r['threshold'],
                   'basis':'signals.'+r['key']} for r in rows if r['triggered']=='是']
    observations.sort(key=lambda r:abs(value(next(x['value'] for x in rows if x['key']==r['key']))),reverse=True)
    columns={k:col(v) for k,v in [('key','行键'),('family','信号类别'),('signal','现象'),('value','计算值'),('baseline','比较基准/口径'),('threshold','触发条件'),('threshold_source','阈值来源'),('triggered','是否触发'),('evidence','文档/页/表/行列'),('missing','缺失或局限')]}
    columns['value']['per_cell_unit']=True
    from .workpaper_signal_followups import signal_followups
    from .workpaper_explanations import evidence_table
    followups,evidence,followup_table=signal_followups(a,rows)
    return {'title':a.st.company+' 异常信号雷达','periods':a.ps,'body':'信号只陈述数值现象，不是风险结论。模型应结合引用原文分别说明可能业务解释与需警惕情形，区分事实与推论。经验阈值没有行业校准。',
            'drivers_evidence':evidence,'signal_followups':followups,
            'tables':{'signals':table(columns,rows),'drivers_evidence':evidence_table(evidence),'signal_followups':followup_table,
                      'inventory_charge_rates':table({'key':col('行键'),'period':col('期间'),'charge':col('当期计提发生额','百万元',a.currency),
                          'average_gross_inventory':col('平均存货账面原值','百万元',a.currency),'value':col('当期计提率','%'),'missing':col('缺失说明')},inventory_rates),
                      'observations':table({k:col(v) for k,v in [('key','行键'),('finding','已触发现象（按绝对数值幅度，跨单位不代表严重度）'),('basis','底稿位置')]},observations)}},a.records

"""Deterministic profit and segment bridges, paired with verbatim explanations."""
from collections import defaultdict
from decimal import Decimal
import json
import re

from .analysis_report import record_quantity
from .financial_workpapers import ALIASES, cell, col, table, meta, source
from .workpaper_annual import compact, literal
from .workpaper_analyst import AnalystData, calc, delta, ratio, value, unknown, locators


def gross_profit_effects(revenue_now,revenue_before,gross_now,gross_before):
    scale=calc([revenue_now,revenue_before,gross_before],lambda r,b,g:(r-b)*g/b,
               formula='收入变化效应=(R1-R0)×(GP0/R0)',positive=(1,))
    margin=calc([gross_now,gross_before,scale],lambda g,b,s:g-b-s,
                formula='毛利率变化效应=ΔGP-收入变化效应=R1×(GP1/R1-GP0/R0)；交叉项归毛利率')
    return scale,margin


def price_volume_mix(items):
    """Same physical volume units: Q change, product mix, realized unit price.

    items: [{revenue_now, revenue_before, volume_now, volume_before}]. Volume
    source quantities keep their original physical unit; cannot mix tons/items.
    Price is realized average revenue/volume, not an independently quoted price.
    """
    units={q['unit'] for item in items for q in (item['volume_now'],item['volume_before'])}
    if len(units)!=1:return [{'volume':unknown('销量单位不同，无法做跨产品结构拆分'),'mix':unknown('销量单位不同，无法做跨产品结构拆分'),'price':unknown('销量单位不同，无法做跨产品结构拆分')} for _ in items]
    totals=[calc([x[key] for x in items],lambda *vs:sum(vs),next(iter(units)),'同单位产品销量合计') for key in ('volume_now','volume_before')]
    result=[]
    for r in items:
        qs=[r['revenue_now'],r['revenue_before'],r['volume_now'],r['volume_before'],*totals]
        ve=calc(qs,lambda r1,r0,q1,q0,t1,t0:(t1-t0)*r0/t0,formula='总销量效应=(Q1-Q0)×s0×P0，P0=R0/q0',positive=(3,5))
        me=calc(qs,lambda r1,r0,q1,q0,t1,t0:q1*r0/q0-t1*r0/t0,formula='结构效应=Q1×(s1-s0)×P0',positive=(3,4,5))
        pe=calc([r['revenue_now'],r['revenue_before'],ve,me],lambda r1,r0,v,m:r1-r0-v-m,
                formula='平均实现价格效应=ΔR-销量效应-结构效应=q1×(P1-P0)；价格可能含产品内组合变化')
        result.append({'volume':ve,'mix':me,'price':pe})
    return result


def disclosed_income(a,key,period):
    q=a.pick(key,period,'income')
    if q['value'] is not None:return q
    # Some normalized imports omitted explicitly printed nil marks. Recover
    # only a dash in the same two-column statement row, anchored by the other
    # period's exact amount. Empty cells and absent rows remain unknown.
    other=next((p for p in a.ps[:2] if p!=period),None)
    record=a.st.pick(key,other,'income') if other else None
    if not record:return q
    label=meta(record).get('label','');words=label.split()
    if len(words)<2 or not re.match('[A-Za-z]',label):return q
    prefix=r'\s+'.join(re.escape(w) for w in words[:5])
    page=record['source_ref'].get('page');text=a.d.pages.get(page,'')
    token=r'(?:\(?-?\d[\d,]*(?:\.\d+)?\)?|[–—-])'
    pair=re.compile(r'('+token+r')\s+('+token+r')\s*$',re.M)
    expected=Decimal(record['value'])/Decimal(str(meta(record).get('scale',1)))
    candidates=[]
    for match in re.finditer(prefix,text,re.I):
        amounts=pair.search(text,match.end())
        if not amounts:continue
        # The first numeric pair belongs to this printed row. Do not keep
        # searching later financial rows if it does not match the known amount.
        index=0 if period==a.ps[0] else 1
        parts=[amounts[1],amounts[2]]
        if parts[index] not in ('–','—','-') or literal(parts[1-index])!=expected:continue
        quote=text[match.start():amounts.end()].strip()
        ref={**a.source_text(page,quote),'table_id':record['source_ref'].get('table_id'),'row_label':label,
             'column_label':period,'raw_value':parts[index],'data_kind':'disclosed_actual',
             'interpretation':'金额列显式破折号为无发生额；不是空白补零；另一期间精确金额用于定位'}
        candidates.append({'value':'0','unit':'元','currency':a.currency,'source':ref})
    return candidates[0] if len(candidates)==1 else q


def profit_bridge(a):
    now=a.ps[0];before=a.ps[1] if len(a.ps)>1 else None
    get=lambda key,p:disclosed_income(a,key,p) if p else unknown('没有可比期')
    cas=any(r['scope'].endswith('_CAS') for r in a.records)
    rows=[];steps=[]
    def add(key,label,role,qs=None,contribution=None,basis=''):
        qs=qs or [unknown('此行为计算效应'),unknown('此行为计算效应')]
        q=contribution if contribution is not None else delta(qs[0],qs[1])
        if role=='step':steps.append(q)
        running=calc([x for x in steps if x['value'] is not None],lambda *vs:sum(vs),formula='已知贡献累计；缺项另列') if steps else cell(0,'元',a.currency,formula='尚无贡献行')
        rows.append({'key':key,'item':label,'role':role,'current':qs[0],'previous':qs[1],'change':delta(qs[0],qs[1]),
                     'contribution':q,'running':running,'basis':basis or q['source'].get('formula',''),
                     'missing':q['source'].get('missing_reason') or ''})
        return q
    revenues=[get('revenue',p) for p in (now,before)];gross=[get('gross_profit',p) for p in (now,before)]
    add('revenue_change','营业收入变化（参考，不重复加到利润桥）','reference',revenues)
    ve,me=gross_profit_effects(*revenues,*gross)
    add('revenue_effect','收入变化对毛利的贡献','step',contribution=ve)
    add('margin_effect','毛利率变化对毛利的贡献','step',contribution=me)
    add('gross_change','披露/推导毛利变化','subtotal',gross)
    if cas:
        total=[get('total_operating_revenue',p) for p in (now,before)]
        if any(q['value'] is not None for q in total):
            other=[delta(t,r) for t,r in zip(total,revenues)]
            add('other_operating_revenue','营业总收入中营业收入以外项目','step',other,basis='营业总收入-营业收入；如金融子公司利息收入，未与财务费用中利息收入重复')
    entries=[('surcharges','税金及附加',-1),('selling','销售费用',-1),('administrative','管理费用',-1),('research','研发费用',-1)] if cas else [('selling','销售费用',1),('administrative','管理费用',1),('research','研发费用',1)]
    entries += ([('finance_costs','财务费用',-1),('other_income','其他收益',1),('investment_income','投资收益',1),('fair_value_gains','公允价值变动',1),
                  ('credit_impairment','信用减值损益',1),('asset_impairment','资产减值损益',1),('asset_disposal','资产处置损益',1)] if cas else
                [('other_income','其他收入',1),('other_gains_net','其他净收益',1),('impairment','金融及合同资产减值/转回',1)])
    for key,label,sign in entries:
        qs=[get(key,p) for p in (now,before)]
        q=calc(qs,lambda x,y:(x-y)*sign,formula=f'有符号项目变化×{sign}；'+('CAS费用扣减，财务费用负值仍按原符号扣减' if cas else 'HKFRS费用已带负号，直接取变化'))
        add(key,label,'step',qs,q)
    # Subtotals are checks, not contributions. The unallocated residual is
    # shown and does not get relabelled as an explained economic driver.
    def checkpoint(key,label):
        qs=[get(key,p) for p in (now,before)];target=delta(*qs)
        known=[q for q in steps if q['value'] is not None]
        subtotal=calc(known,lambda *vs:sum(vs),formula='已列已知贡献之和') if known else unknown('没有已知贡献')
        add(key+'_change',label+'变化','subtotal',qs)
        residual=delta(target,subtotal)
        add(key+'_residual',label+'变化减累计已知贡献','residual',contribution=residual,
            basis='未解释差额；可能包含缺失项目；不作为已解释驱动，不强制配平')
    checkpoint('operating_profit','营业利润')
    below=([('nonoperating_income','营业外收入',1),('nonoperating_expenses','营业外支出',-1)] if cas else
           [('finance_net','财务净收益/费用',1),('fair_value_gains','营业利润后公允价值变动',1),('associates','联营及合营损益',1)])
    for key,label,sign in below:
        qs=[get(key,p) for p in (now,before)]
        if all(q['value'] is None for q in qs) and not cas:continue
        add(key,label,'step',qs,calc(qs,lambda x,y:(x-y)*sign,formula=f'有符号项目变化×{sign}'))
    checkpoint('profit_before_tax','税前利润')
    for key,label,sign in [('tax','所得税',-1 if cas else 1),('minority_profit','少数股东损益',-1)]:
        qs=[get(key,p) for p in (now,before)]
        add(key,label,'step',qs,calc(qs,lambda x,y:(x-y)*sign,formula=f'有符号项目变化×{sign}'))
        if key=='tax':checkpoint('net_profit','合并净利润')
    checkpoint('parent_profit','归母净利润')
    return rows


def mdna_pages(a):
    """Named report sections; no issuer-specific page boundaries."""
    result=set();active=False
    for page,text in sorted(a.d.pages.items()):
        if re.search(r'(?im)^\s*Management Discussion and Analysis\s*$',text):result.add(page)
        for m in re.finditer(r'第[一二三四五六七八九十]+节\s*([^\n]+)',text):
            title=compact(m[1])
            if re.search(r'\.{3}|…{2}|[.．·]{3}',title):continue
            active=bool(re.search('管理层讨论|经营情况讨论|董事会报告',title))
        if active:result.add(page)
    return result


def parent_note_start(a):
    found=[p for p,text in a.d.pages.items() if re.search(r'(?m)^\s*(?:[一二三四五六七八九十]+[、.])?\s*母公司财务报表.{0,8}注释',text)]
    return min(found) if found else None


def sentences(text):
    # Keep original whitespace and offsets. Decimal points do not end sentences.
    return [m.group().strip() for m in re.finditer(r'.+?(?:[。；]|\.(?=\s+[A-Z(]|\s*$)|$)',text,re.S) if m.group().strip()]


DRIVER_TERMS={
    'revenue_effect':r'营业收入|revenue', 'margin_effect':r'营业成本|毛利率|gross profit|cost of sales',
    'selling':r'销售费用|selling expenses', 'administrative':r'管理费用|administrative expenses',
    'research':r'研发费用|research and development', 'finance_costs':r'财务费用|finance costs|financing costs',
    'finance_net':r'财务费用|finance costs|finance income|financing costs',
    'other_income':r'其他收益|其他收入|other income|government grants',
    'other_gains_net':r'其他.*收益|other gains', 'investment_income':r'投资收益|investment income',
    'asset_impairment':r'资产减值|商誉|goodwill|asset impairment', 'credit_impairment':r'信用减值|保理风险准备|credit losses',
    'impairment':r'减值|credit losses|impairment', 'fair_value_gains':r'公允价值|fair\s+value',
    'tax':r'所得税|income tax', 'minority_profit':r'少数股东|non.controlling',
    'nonoperating_income':r'营业外收入', 'nonoperating_expenses':r'营业外支出',
    'asset_disposal':r'资产处置|disposal', 'surcharges':r'税金及附加', 'other_operating_revenue':r'利息收入|interest income',
}
CAUSE=r'原因|所致|由于|主要是|导致|因.{0,25}(?:增加|减少)|due to|because|attribut|result|driven|reason|recogni[sz]ed'


def find_explanations(a,key,label):
    terms=DRIVER_TERMS.get(key,re.escape(label).replace('_',r'\s+'))
    preferred=mdna_pages(a);candidates=[];parent=parent_note_start(a)
    for page,text in sorted(a.d.pages.items()):
        if parent and page>=parent and a.st.scope=='consolidated':continue
        snippets=sentences(text)
        for index,quote in enumerate(snippets):
            if re.search(r'main reason for this change',quote,re.I) and index:
                quote=snippets[index-1]+'\n'+quote
            normalized=re.sub(r'\s+',' ',quote)
            # Keep spaces for English; remove wrapped whitespace for CJK.
            searchable=normalized if re.search(terms,normalized,re.I) else compact(quote)
            matches=list(re.finditer(terms,searchable,re.I));cause=re.search(CAUSE,searchable,re.I)
            if not matches or not cause:continue
            if key.startswith('contribution_'):
                topic=re.escape(label).replace('_',r'\s+')
                if not re.search(r'(?:'+topic+r').{0,65}(?:收入|revenue)|(?:收入|revenue).{0,65}(?:'+topic+r')',searchable,re.I):continue
            if page not in preferred and not re.search(r'(?:本期|本年|报告期).*(?:所致|导致)|变动原因|减少原因|增加主要原因',compact(quote)):
                continue # Accounting policy and recognition boilerplate is not a period-change cause.
            # A table and its first explanatory sentence may be one extracted
            # paragraph. Start from the final subject occurrence before cause.
            if re.search('[\u4e00-\u9fff]',searchable):
                # The subject must belong to the causal clause itself. A
                # keyword in a preceding numeric table is not aligned evidence.
                local=re.search('(?:'+terms+r')[^。；:：\d]{0,35}(?:变动原因|减少(?:主要)?原因|增加(?:主要)?原因|主要原因|主要是|主要因|所致|导致)',compact(quote),re.I)
                if not local:continue
                clean=compact(quote);start=local.start()
                enumerators=list(re.finditer(r'[（(]\d+[）)]',clean[:start]))
                if enumerators and start-enumerators[-1].start()<80:start=enumerators[-1].start()
                quote=clean[start:]
            if re.search(r'□适用\s*√不适用|不适用。?$',quote):continue
            section='管理层讨论与分析' if page in preferred else '财务附注/其他原文'
            # Prefer a statement about a change, then named causal wording.
            score=(page in preferred,bool(re.search('变动原因|减少原因|增加主要原因|main reason|mainly due',searchable,re.I)), -len(quote))
            candidates.append((score,a.source_text(page,quote,section=section)))
    # One best relevant cause avoids padding an exact match with an unrelated
    # second hit. The full original document remains available for judgment.
    return [x[1] for x in sorted(candidates,key=lambda x:x[0],reverse=True)[:1]]


AXES={'product':'product','business_line':'product','region':'region','geography':'region','industry':'industry','segment':'segment','business_type':'business_type'}
TOTAL=re.compile(r'^(?:total|合计|合計|小计|小計|subtotal|全部)$',re.I)
REVENUE={'revenue','main_business_revenue','segment_revenue'}
COST={'cost_of_revenue','cost_of_sales','main_business_cost','segment_cost'}
COST_PARTS={'direct_materials_cost','direct_labor_cost','manufacturing_overhead','loading_and_transportation_cost','transportation_expenses'}


def unique_quantity(records,reason):
    if records and len({r['value'] for r in records})==1 and all(r.get('quality')!='conflict' for r in records):return record_quantity(records[0])
    return cell(None,sources=[source(r) for r in records],reason=reason if not records else '同一维度披露数值冲突')


def product_disclosed_change(a,label):
    """Use explicit disclosed delta/PVM, never invert rounded growth rates."""
    results={};preferred=mdna_pages(a)
    for p in sorted(preferred):
        text=compact(a.d.pages[p])
        pattern=re.escape(compact(label))+r'(?:产品)?本期实现.*?(?=(?:[。]|$))'
        m=re.search(pattern,text)
        if not m:continue
        quote=m[0]
        def q(match,sign,kind):
            return {'value':str(Decimal(match[1].replace(',',''))*sign),'unit':match[2],'currency':a.currency,
                    'source':{**a.source_text(p,quote),'data_kind':'disclosed_actual','precision_note':'原文直接披露的变动额；保留原披露单位/精度，不由同比倒算','component':kind}}
        for metric,word in [('revenue','收入'),('cost','成本')]:
            found=re.search(word+r'[^。；]*?较上期(增加|减少)([\d,.]+)(亿元|万元|百万元|元)',quote)
            if found:results[metric]=q((None,found[2],found[3]),1 if found[1]=='增加' else -1,metric)
        for found in re.finditer(r'因([^，。]{1,35}?)(增加|减少)收入([\d,.]+)(亿元|万元|百万元|元)',quote):
            cause=found[1];kind='volume' if re.search('销量|销售量',cause) else 'mix' if '结构' in cause else 'price' if '价格' in cause else None
            if kind:results[kind]=q((None,found[3],found[4]),1 if found[2]=='增加' else -1,kind)
    return results


def structural_contributions(a):
    ps=a.ps[:2];now=ps[0];before=ps[1] if len(ps)>1 else None
    parent=parent_note_start(a);facts=[r for r in a.records if r['period'] in ps and r['currency']==a.currency
                                      and not (parent and r['source_ref'].get('page',0)>=parent and a.st.scope=='consolidated')]
    views=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for r in facts:
        if r['metric'] not in REVENUE|COST:continue
        dims=r.get('dimensions') or {};active=[(AXES[k],v) for k,v in dims.items() if k in AXES and not TOTAL.fullmatch(str(v))]
        if len(active)!=1:continue # crossed dimensions are not additive one-axis rows
        axis,label=active[0];views[(axis,r['source_ref']['table_id'])][label][(r['period'],'revenue' if r['metric'] in REVENUE else 'cost')].append(r)
    selected={};alternatives=[]
    # A whole view is selected, never a subset summing to an answer. Prefer
    # paired periods, then the fuller dimensional view. Exact table totals
    # distinguish explicit child rows from a view mixing children/subtotals.
    for (axis,tid),cats in views.items():
        totals=[r for r in facts if r['source_ref'].get('table_id')==tid and r['metric'] in REVENUE and r['period']==now
                and (any(TOTAL.fullmatch(str(v)) for k,v in (r.get('dimensions') or {}).items() if k in AXES or k=='aggregation')
                     or not any(k in AXES for k in (r.get('dimensions') or {})))]
        current=[unique_quantity(vals.get((now,'revenue'),[]),'缺本期分项收入') for vals in cats.values()]
        amount=sum(value(q) for q in current if q['value'] is not None)
        reconciles=any(Decimal(r['value'])==amount for r in totals)
        paired=sum(bool(v.get((now,'revenue'))) and bool(v.get((before,'revenue'))) for v in cats.values())
        score=(reconciles,paired,len(cats))
        # Different sets of categories may be different scopes (e.g. all
        # businesses vs the geographic split of branded business). Keep both.
        overlaps=[view for view,old in selected.items() if old[3]==axis and set(old[2])&set(cats)]
        view=overlaps[0] if overlaps else axis+'_'+str(sum(v[3]==axis for v in selected.values()))
        if view not in selected or score>selected[view][0]:
            if view in selected:alternatives.append({'axis':axis,'table_id':selected[view][1],'reason':'保留重叠分类备选表；优先采用可勾稽、双期完整的整张维度视图'})
            selected[view]=(score,tid,cats,axis)
        else:alternatives.append({'axis':axis,'table_id':tid,'reason':'保留重叠分类备选表；避免同一分类视图重复加总'})
    rows=[]
    for view,(_,tid,cats,axis) in selected.items():
        group=[]
        for label,vals in cats.items():
            qs={(p,k):unique_quantity(vals.get((p,k),[]),f'缺少 {p} {label} {k} 原值；不由舍入同比倒算') for p in (now,before) for k in ('revenue','cost')}
            # Cost-detail tables can supply exact prior costs when their
            # current component sum equals the selected disclosed total.
            components={p:[] for p in (now,before)}
            for p in components:
                for metric in COST_PARTS:
                    rs=[r for r in facts if r['period']==p and r['metric']==metric and any(AXES.get(k)==axis and v==label for k,v in (r.get('dimensions') or {}).items())]
                    if rs:components[p].append(unique_quantity(rs,'成本明细缺失'))
            if all(components.values()):
                sums={p:calc(v,lambda *xs:sum(xs),formula='原文互斥成本组成合计') for p,v in components.items()}
                if sums[now]['value'] is not None and qs[now,'cost']['value'] is not None and value(sums[now])==value(qs[now,'cost']):
                    if qs[before,'cost']['value'] is None:qs[before,'cost']=sums[before]
            rev=delta(qs[now,'revenue'],qs[before,'revenue']);cost=delta(qs[now,'cost'],qs[before,'cost'])
            disclosed=product_disclosed_change(a,label) if axis=='product' else {}
            used_disclosed=False
            if rev['value'] is None and 'revenue' in disclosed:rev=disclosed['revenue'];used_disclosed=True
            if cost['value'] is None and 'cost' in disclosed:cost=disclosed['cost'];used_disclosed=True
            gp=delta(rev,cost)
            ident='contribution_'+str(len(rows))
            pvm={k:disclosed.get(k,unknown('没有两期精确销量/实现价格或原文直接披露的该项贡献；不由舍入增速倒算')) for k in ('volume','price','mix')}
            decomp=calc([rev,*pvm.values()],lambda r,v,p,m:r-v-p-m,formula='收入变动-披露销量/价格/结构效应')
            missing='；'.join(dict.fromkeys(q['source'].get('missing_reason') or '' for q in [rev,gp] if q['value'] is None))
            row={'key':ident,'axis':axis,'view':view,'item':label,'role':'component','current_revenue':qs[now,'revenue'],'previous_revenue':qs[before,'revenue'],
                 'current_cost':qs[now,'cost'],'previous_cost':qs[before,'cost'],'revenue_change':rev,'gross_change':gp,
                 **{k+'_effect':q for k,q in pvm.items()},'decomposition_residual':decomp,
                 'basis':('变动额含原文直接披露的舍入金额，精度见来源；未反推上期精确值。' if used_disclosed else '同一维度、同口径两期原值相减。')+'每个维度单独加总，产品/地区/分部不可互加。',
                 'missing':missing}
            rows.append(row);group.append(row)
        # Recompute volume/price/mix when both exact period quantities exist.
        # Source-native physical units are preserved; unlike a percentage
        # inverse, this does not invent an undisclosed prior quantity.
        volume_inputs=[]
        for r in group:
            pair={}
            for p,name in ((now,'volume_now'),(before,'volume_before')):
                candidates=[x for x in a.records if x['period']==p and x['metric'] in ('sales_volume','sales_quantity','quantity_sold','volume_sold')
                            and any(AXES.get(k)==axis and v==r['item'] for k,v in (x.get('dimensions') or {}).items())]
                pair[name]=unique_quantity(candidates,'缺少两期同单位销量')
            volume_inputs.append({'revenue_now':r['current_revenue'],'revenue_before':r['previous_revenue'],**pair})
        if group and all(all(q['value'] is not None for q in x.values()) for x in volume_inputs):
            computed=price_volume_mix(volume_inputs)
            for r,effects in zip(group,computed):
                for k,q in effects.items():r[k+'_effect']=q
                r['decomposition_residual']=calc([r['revenue_change'],*effects.values()],lambda d,*v:d-sum(v),formula='收入变化-量价结构效应之和')
                r['basis']+=' 量价结构使用两期精确销量与平均实现价格；先总销量，再产品占比，最后单价，交叉项归后项。'
        # Reference totals: full income statement, then an explicitly disclosed
        # main-business total. Match current scope, never infer a prior split.
        currsum=calc([r['current_revenue'] for r in group],lambda *xs:sum(xs),formula='维度当前分项收入之和')
        refs=[({p:a.pick('revenue',p,'income') if p else unknown('缺可比期') for p in (now,before)},
               {p:a.pick('cogs',p,'income') if p else unknown('缺可比期') for p in (now,before)})]
        main={p:unique_quantity([r for r in facts if r['period']==p and r['metric'] in REVENUE and (r.get('dimensions') or {}).get('business_type') in ('主营业务','main business') and not (r.get('dimensions') or {}).get('aggregation')],'缺同口径主营业务合计') for p in (now,before)}
        main_cost={p:unique_quantity([r for r in facts if r['period']==p and r['metric'] in COST and (r.get('dimensions') or {}).get('business_type') in ('主营业务','main business') and not (r.get('dimensions') or {}).get('aggregation')],'缺同口径主营业务成本合计') for p in (now,before)}
        refs.append((main,main_cost))
        matched=next(((rev,cost) for rev,cost in refs if currsum['value'] is not None and rev[now]['value'] is not None and value(currsum)==value(rev[now])),None)
        target=matched[0] if matched else None
        # When no independent total exists, show the sum and explicitly keep
        # its comparison-to-company residual unknown.
        total_change=delta(target[now],target[before]) if target else unknown('分项未匹配唯一同口径总额（或披露有舍入），不能认定覆盖全部收入')
        known=[r['revenue_change'] for r in group if r['revenue_change']['value'] is not None]
        explained=calc(known,lambda *v:sum(v),formula='已知分项收入变动之和') if known else cell(0,'元',a.currency,formula='无已知分项贡献；全部总额仍未分配')
        rest=delta(total_change,explained)
        target_gp=delta(*[calc([matched[0][p],matched[1][p]],lambda r,c:r-abs(c),formula='同口径收入-成本绝对额') for p in (now,before)]) if matched else unknown('缺少唯一同口径两期总毛利')
        known_gp=[r['gross_change'] for r in group if r['gross_change']['value'] is not None]
        gp_explained=calc(known_gp,lambda *vs:sum(vs),formula='已知分项毛利变化合计') if known_gp else cell(0,'元',a.currency,formula='无已知分项毛利贡献；总额全部未分配')
        gp_rest=delta(target_gp,gp_explained)
        rows.append({'key':view+'_unallocated','axis':axis,'view':view,'item':'未分配差额（缺项/披露精度/口径）','role':'residual',
                     'revenue_change':rest,'gross_change':gp_rest,
                     'basis':'同口径总变化减已知分项；包含未知分项，不宣称是某一产品贡献。'+('总额范围：与分项当前合计一致的主表/主营业务。' if target else ''),
                     'missing':rest['source'].get('missing_reason') or ('部分分项变动缺失，残差包含该缺失' if len(known)<len(group) else '')})
        rows.append({'key':view+'_total','axis':axis,'view':view,'item':'同口径收入/毛利总变化','role':'total','revenue_change':total_change,'gross_change':target_gp,
                     'basis':'已知分项贡献+未分配差额=同口径总变化；维度之间不加总','missing':total_change['source'].get('missing_reason') or ''})
    for axis in ('product','region','industry','segment'):
        if not any(v[3]==axis for v in selected.values()):rows.append({'key':axis+'_missing','axis':axis,'view':axis,'item':'未识别该维度可计算披露','role':'missing','missing':'缺少可定位的同口径维度金额；原始表与记录仍保留','basis':'未将其他维度替代该维度'})
    return rows,alternatives


def variance_attribution(service,project,document_id=None,company=None,scope='consolidated',periods=None,focus=None):
    a=AnalystData(service,project,document_id,company,scope,periods,focus)
    bridge=profit_bridge(a);contributions,alternatives=structural_contributions(a)
    drivers=[r for r in bridge if r['role']=='step']
    structural_drivers=[{'key':r['key'],'item':r['item'],'contribution':r['revenue_change']} for r in contributions if r['role']=='component' and r['revenue_change']['value'] is not None]
    evidence=[]
    for r in sorted(drivers+structural_drivers,key=lambda x:abs(value(x['contribution']) or 0),reverse=True):
        direct=r['contribution']['source']
        refs=[direct] if r['key'].startswith('contribution_') and direct.get('quote') else find_explanations(a,r['key'],r['item'])
        evidence.append({'key':r['key'],'driver':r['item'],'contribution':r['contribution'],'status':'原文相关原因披露（不证明贡献公式的经济因果）' if refs else '原文未说明',
                         'quote':'\n\n'.join(x['quote'] for x in refs) if refs else '原文未说明',
                         'pages':', '.join(str(x['page']) for x in refs),'source':json.dumps(refs,ensure_ascii=False),
                         'search_scope':'先检索管理层讨论与分析，再检索同口径附注；未检出原因不补写推论'})
    observations=[{'key':r['key'],'finding':r['item']+'贡献 '+str(r['contribution']['value'])+' 元','basis':'bridge.'+r['key']} for r in sorted(drivers,key=lambda x:abs(value(x['contribution']) or 0),reverse=True) if r['contribution']['value'] is not None]
    observations += [{'key':r['key'],'finding':r['item']+'：'+str(r['contribution']['value'])+' 元','basis':'bridge.'+r['key']} for r in bridge if r['role']=='residual']
    money=lambda label:col(label,'百万元',a.currency)
    bc={k:col(label) for k,label in [('key','行键'),('item','利润桥项目'),('role','行作用'),('basis','拆法/口径'),('missing','缺失说明')]}
    bc.update({k:money(label) for k,label in [('current','本期原符号'),('previous','比较期原符号'),('change','原值变化'),('contribution','对归母变动的贡献/参考差额'),('running','已知贡献累计')]})
    cc={k:col(label) for k,label in [('key','行键'),('axis','维度'),('view','独立视图'),('item','项目'),('role','行作用'),('basis','口径'),('missing','缺失说明')]}
    cc.update({k:money(label) for k,label in [('current_revenue','本期收入'),('previous_revenue','比较期收入'),('current_cost','本期成本'),('previous_cost','比较期成本'),('revenue_change','收入变化贡献'),('gross_change','毛利变化贡献'),('volume_effect','销量效应（披露精度）'),('price_effect','价格效应（披露精度）'),('mix_effect','结构效应（披露精度）'),('decomposition_residual','量价结构残差')]})
    # Explicit unknown cells for inapplicable columns; no renderer-level zero.
    for r in contributions:
        for k,c in cc.items():
            if c.get('unit') and k not in r:r[k]=unknown('此行不适用或未披露该项')
    ec={k:col(label) for k,label in [('key','行键'),('driver','驱动项'),('status','证据状态'),('quote','原句'),('pages','PDF页'),('source','来源'),('search_scope','检索范围')]};ec['contribution']=money('计算贡献')
    tabs={'bridge':table(bc,bridge),'contributions':table(cc,contributions),'drivers_evidence':table(ec,evidence),
          'contribution_sources':table({k:col(k) for k in ('key','axis','table_id','reason')},[{'key':str(i),**r} for i,r in enumerate(alternatives)]),
          'observations':table({k:col(v) for k,v in [('key','行键'),('finding','确定性贡献（按绝对金额排序）'),('basis','对应底稿')]},observations)}
    return {'title':a.st.company+' 业绩变动归因底稿','body':'利润桥以两期金额变化计算；收入效应取上期毛利率，交叉项归本期毛利率效应。原文原因与确定性金额贡献分开，未解释差额显式列示。未披露的精确比较期不由舍入增速倒算。','tables':tabs},a.records

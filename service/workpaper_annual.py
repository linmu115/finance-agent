"""Annual disclosure tables: preserve physical rows and compare signed quantities.

Selection uses table structure and disclosed labels, never issuer names/pages.
An unrecognised adjustment still participates in the disclosed bridge, but has
no invented financial classification. Blank source cells remain unknown.
"""
import json
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from .analysis_report import record_quantity, convert
from .financial_workpapers import cell, col, table, meta, source, number


def compact(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(text)))


def literal(text):
    text=compact(text).replace(',','').replace('−','-').replace('－','-')
    if re.fullmatch(r'\([-+]?\d+(?:\.\d+)?\)',text):text='-'+text[1:-1]
    return Decimal(text.rstrip('%')) if re.fullmatch(r'[-+]?\d+(?:\.\d+)?%?',text) else None


def quarter(label):
    m=re.search(r'第?([一二三四1234])季度|Q([1-4])',compact(label),re.I)
    if not m:return None
    value=m[1] or m[2]
    return str('一二三四'.index(value)+1) if value in '一二三四' else value


def row_kind(label):
    label=compact(label)
    if re.search('扣除?非|非经常性损益.*净利润',label):return 'deducted_profit'
    if re.search('归属.*(?:股东|所有者).*净利润|归母净利',label):return 'parent_profit'
    if re.search('经营活动.*现金流量净额',label):return 'cfo'
    if re.fullmatch('营业(?:总)?收入',label):return 'revenue'
    return None


def bridge_category(label):
    label=compact(label)
    if re.search('存货.*(?:减少|增加)|经营性应[收付]',label):
        return '营运资本','按存货及经营性应收、应付变动列名归类'
    if re.search('减值|折旧|折耗|摊销|公允价值变动|递延所得税|股份支付',label):
        return '非现金项目','按减值、折旧摊销、公允价值、递延税或股份支付列名归类'
    if re.search('财务费用|投资(?:损失|收益)|处置.*(?:资产|损失)|报废|^其他$',label):
        return '其他','投资/筹资相关损益重分类及披露的其他调整；不把整项财务费用断言为非现金'
    return '未识别','未匹配分类规则；原行与有符号金额保留并参与总桥，不猜归类'


class Disclosure:
    def __init__(self,st):
        self.st=st
        self.doc=next(iter({r['document_id'] for r in st.facts}))
        with st.service.store.connect() as db:
            self.document=dict(db.execute('SELECT * FROM documents WHERE document_id=? AND project_id=?',(self.doc,st.project)).fetchone() or {})
            self.pages={r['page']:r['text'] for r in db.execute('SELECT page,text FROM pages WHERE document_id=?',(self.doc,))}
            self.tabs=[{**dict(r),'rows':json.loads(r['rows_json'])} for r in db.execute('SELECT * FROM source_tables WHERE document_id=? ORDER BY page,rowid',(self.doc,))]
            self.scopes={}
            for r in db.execute('SELECT scope,source_json FROM current_financial_facts WHERE project_id=? AND document_id=?',(st.project,self.doc)):
                self.scopes.setdefault(json.loads(r['source_json']).get('table_id'),set()).add(r['scope'])
        self.year=str(self.document.get('report_year') or st.periods[0][:4])
        self.unknown=[]

    def applies(self,t):
        scopes=self.scopes.get(t['table_id'],set())
        return any(s==self.st.scope or s.startswith(self.st.scope+'_') for s in scopes) if scopes else not self.st.scope.startswith('parent')

    def quantity(self,t,row,column,header,unit=None):
        raw=t['rows'][row][column] if column<len(t['rows'][row]) else ''
        value=literal(raw)
        ref={'document_id':self.doc,'report':self.document.get('original_name'), 'page':t['page'],
             'table_id':t['table_id'],'row':row+1,'column':column+1,'column_label':header,
             'text':t['rows'][row][0], 'raw_value':raw,'data_kind':'disclosed_actual'}
        if unit is None:
            # Unit evidence comes from the same physical table; the page label
            # is used only when no normalized table fact carries the unit.
            units={r['raw_unit'] for r in self.st.facts if r['source_ref'].get('table_id')==t['table_id'] and r['currency']==self.st.currency}
            if len(units)==1:unit=next(iter(units))
            else:
                marks=re.findall(r'单位\s*[:：]\s*(百万元|千元|万元|亿元|元)',self.pages.get(t['page'],''))
                if len(set(marks))==1:unit=marks[0]
        if unit is None or value is None:
            ref['missing_reason']='原披露为空白' if not compact(raw) else '原文数值或单位未识别'
            if compact(raw):self.unknown.append({'item':t['rows'][row][0],'reason':ref['missing_reason'],'source':ref})
            return {'value':None,'unit':unit or '元','currency':self.st.currency,'source':ref}
        return {'value':str(value),'unit':unit,'currency':None if unit=='%' else self.st.currency,'source':ref}

    def blocks(self,kind):
        """Continue a headerless adjacent same-width table until the explicit end."""
        blocks=[];active=None
        for t in self.tabs:
            rows=t['rows']
            if not rows:continue
            joined=' '.join(compact(c) for row in rows for c in row)
            starts = ('非经常性损益项目' in compact(rows[0][0])) if kind=='nonrec' else bool(re.search(r'(?:将)?净利润(?:调节|调整)为经营活动(?:产生的)?现金流量',joined))
            if starts:
                # Reject a table explicitly mapped only to another statement scope.
                if not self.applies(t):continue
                active={'header':rows[0],'rows':[],'page':t['page'],'width':len(rows[0])};blocks.append(active)
            elif active and (t['page']>active['page']+1 or len(rows[0])!=active['width'] or any(re.search(r'本期金额|上期金额|20\d{2}年',compact(v)) for v in rows[0][1:])):
                active=None
            if active is None:continue
            active['page']=t['page']
            for i,row in enumerate(rows):
                label=compact(row[0])
                if label.startswith(('补充资料','非经常性损益项目')) or re.search(r'净利润(?:调节|调整)为',label):continue
                active['rows'].append((t,i))
                if (kind=='nonrec' and label=='合计') or (kind=='indirect' and row_kind(label)=='cfo'):
                    active=None;break
        return blocks

    def columns(self,header):
        result={}
        for c,h in enumerate(header[1:],1):
            h=compact(h);m=re.search(r'(20\d{2})年',h)
            if re.search('增减|同比',h):continue
            p=m[1]+'-FY' if m else self.year+'-FY' if re.search('本期|本年',h) else str(int(self.year)-1)+'-FY' if re.search('上期|上年',h) else None
            if p:result[p]=(c,header[c])
        return result


def compute(qs,fn,unit='元',formula=''):
    reason='；'.join(q.get('source',{}).get('missing_reason','缺少披露数值') for q in qs if q['value'] is None)
    values=[Decimal(convert(q['value'],q['unit'],unit)) for q in qs] if not reason else []
    return cell(None if reason else fn(values),unit,qs[0].get('currency') if unit=='元' and qs else None,
                [q['source'] for q in qs],formula,reason or None)


def missing(reason):return cell(None,reason=reason)


def annual_tables(st,tables,selected):
    d=Disclosure(st)
    if not d.document:return  # Pure-core fixtures need no source-table database.
    money=lambda label:col(label,'百万元',st.currency)
    amounts={p:money(p) for p in st.periods}
    nrrows=[];totals={};nrblocks=d.blocks('nonrec')
    if len(nrblocks)==1:
        block=nrblocks[0];cols=d.columns(block['header'])
        for t,i in block['rows']:
            label=t['rows'][i][0]
            r={'key':t['table_id']+'_'+str(i+1),'item':label}
            for p in st.periods:
                r[p]=d.quantity(t,i,*cols[p]) if p in cols else missing('表头无该期间')
                if compact(label)=='合计':totals[p]=r[p]
            nrrows.append(r)
    elif nrblocks:
        for b in nrblocks:
            for t,i in b['rows']:d.unknown.append({'item':t['rows'][i][0],'reason':'存在多份非经常损益表，未擅选','source':{'table_id':t['table_id'],'page':t['page'],'raw_row':t['rows'][i]}})
    if nrblocks:
        tables['nonrecurring_items']=table({'key':col('行键'),'item':col('非经常性损益原披露项目'),**amounts},nrrows)
    reconc=[];roe=[]
    for p in st.periods:
        parent=record_quantity(selected[p]['parent_profit']) if selected[p]['parent_profit'] else missing('缺归母净利润')
        deducted=st.pick('deducted_profit',p)
        dq=record_quantity(deducted) if deducted else missing('未披露扣非归母净利润')
        total=totals.get(p,missing('未找到唯一非经常性损益合计'))
        calculated=compute([parent,total],lambda v:v[0]-v[1],formula='归母净利润-非经常性损益合计')
        ratio=cell(None,'%',reason='缺少非经常损益合计或非零归母净利润')
        if parent['value'] is not None and total['value'] is not None and number(parent['value'])!=0:
            ratio=cell(number(convert(total['value'],total['unit'],'元'))/number(convert(parent['value'],parent['unit'],'元'))*100,'%',sources=[total['source'],parent['source']],formula='非经常性损益合计/归母净利润*100')
        reconc.append({'key':p,'parent':parent,'disclosed':dq,'nonrecurring':total,'calculated':calculated,
                       'residual':compute([dq,calculated],lambda v:v[0]-v[1],formula='披露扣非-计算扣非'),'share':ratio})
        begin=date(int(p[:4]),1,1);end=date(int(p[:4]),12,31)
        rev=selected[p]['revenue']
        if rev and meta(rev).get('period_start'):begin=date.fromisoformat(meta(rev)['period_start']);end=date.fromisoformat(meta(rev)['period_end'])
        eq=[st.pick('parent_equity',str(when),'balance') for when in (begin-timedelta(days=1),end)]
        eqs=[record_quantity(r) if r else missing('缺少同报告归母权益时点') for r in eq]
        avg=compute(eqs,lambda v:sum(v)/2,formula='(期初归母权益+期末归母权益)/2')
        calc=cell(None,'%',reason='缺利润或正平均归母权益')
        if parent['value'] is not None and avg['value'] is not None and number(avg['value'])>0:
            calc=cell(number(convert(parent['value'],parent['unit'],'元'))/number(avg['value'])*100,'%',sources=[parent['source'],avg['source']],formula='归母净利润/平均归母权益*100；未年化')
        candidates=[]
        for t in d.tabs:
            if not t['rows'] or not d.applies(t):continue
            cols=d.columns(t['rows'][0])
            if p not in cols:continue
            for i,row in enumerate(t['rows'][1:],1):
                if re.fullmatch(r'加权平均(?:净资产收益率|ROE)(?:\(%\))?',compact(row[0]),re.I):
                    candidates.append(d.quantity(t,i,*cols[p],unit='%'))
        disclosed=candidates[0] if candidates and len({q['value'] for q in candidates})==1 else cell(None,'%',reason='未找到唯一披露加权平均ROE')
        roe.append({'key':p,'weighted':disclosed,'begin':eqs[0],'end':eqs[1],'average':avg,'computed':calc,'basis':'披露加权平均ROE原样取用；对照为归母净利润/期初期末平均归母权益，未年化；权重口径不同，不强行对齐'})
    tables['deducted_profit']=table({'key':col('期间'),**{k:money(v) for k,v in [('parent','归母净利润'),('disclosed','披露扣非归母'),('nonrecurring','非经常损益合计'),('calculated','归母减非经常损益'),('residual','披露扣非减计算扣非')]},'share':col('非经常损益占归母','%')},reconc)
    tables['roe']=table({'key':col('期间'),'weighted':col('披露加权平均ROE','%'),**{k:money(v) for k,v in [('begin','期初归母权益'),('end','期末归母权益'),('average','平均归母权益')]},'computed':col('平均归母权益ROE','%'),'basis':col('口径差异')},roe)
    for r in reconc:
        if r['disclosed']['value'] is not None:
            gap=r['residual']['value'];share=r['share']['value']
            tables['observations']['rows'].append({'key':r['key']+'_deducted',
                'finding':f'{r["key"]} 披露扣非归母净利润 {r["disclosed"]["value"]} 元；披露扣非减（归母减非经常损益）为 {gap if gap is not None else "未知"} 元；非经常损益占归母 {format(number(share),".4f") if share is not None else "未知"}%',
                'basis':'deducted_profit.'+r['key']})
    for r in roe:
        if r['weighted']['value'] is not None:
            calc=r['computed']['value']
            tables['observations']['rows'].append({'key':r['key']+'_roe',
                'finding':f'{r["key"]} 披露加权平均ROE {r["weighted"]["value"]}%；平均归母权益ROE {format(number(calc),".4f") if calc is not None else "未知"}%；权重口径不同，未年化，不强行对齐',
                'basis':'roe.'+r['key']})
    if len(reconc)>=2:
        a,b=reconc[:2]
        change=st.calculate('yoy',{'current':a['disclosed']['value'],'previous':b['disclosed']['value']},'%', [a['disclosed']['source'],b['disclosed']['source']])
        tables['growth']['rows'].append({'key':'deducted_profit','metric':'扣非归母净利润','change':change,'basis':f'{a["key"]} 对 {b["key"]}；使用披露扣非'})
    indirect_tables(d,tables,selected)
    quarterly_tables(d,tables,selected,reconc)
    tables['unrecognized_rows']=table({k:col(v) for k,v in [('key','行键'),('item','原始项目'),('reason','未识别原因'),('source','原文及来源')]},
                                    [{'key':str(i),**r,'source':json.dumps(r['source'],ensure_ascii=False)} for i,r in enumerate(d.unknown)])


def indirect_tables(d,tables,selected):
    st=d.st;blocks=d.blocks('indirect');rows=[];groups=[]
    for bidx,b in enumerate(blocks):
        cols=d.columns(b['header'])
        for p in st.periods:
            quantities=[];categories={k:[] for k in ('非现金项目','营运资本','其他','未识别')};start=None;end=None
            for t,i in b['rows']:
                label=t['rows'][i][0];clean=compact(label)
                q=d.quantity(t,i,*cols[p]) if p in cols else missing('补充资料表头无该期间')
                category,basis=bridge_category(label)
                direction='加' if q['value'] is not None and number(q['value'])>=0 else '减' if q['value'] is not None else '未知'
                if clean=='净利润':start=q;direction='起点';category='净利润';basis='补充资料披露起点'
                elif row_kind(label)=='cfo':end=q;direction='终点';category='CFO';basis='补充资料披露终点'
                else:
                    quantities.append(q);categories[category].append(q)
                    if category=='未识别':d.unknown.append({'item':label,'reason':basis,'source':q['source']})
                rows.append({'key':f'{bidx}_{p}_{t["table_id"]}_{i+1}','period':p,'item':label,'direction':direction,'amount':q,'category':category,'basis':basis+'；方向取披露数值符号，不由“损失/减少”字面翻转'})
            start=start or missing('缺少净利润起点');end=end or missing('缺少CFO终点')
            explained=compute([start,*quantities],sum,formula='披露净利润+所有披露调整行（含未识别分类行）')
            residual=compute([end,explained],lambda v:v[0]-v[1],formula='披露CFO-净利润-全部调整')
            rows.append({'key':f'{bidx}_{p}_residual','period':p,'item':'未解释差额','direction':'残差','amount':residual,'category':'勾稽','basis':'保留未解释差额；空白值不按零处理'})
            tables['observations']['rows'].append({'key':f'indirect_{bidx}_{p}',
                'finding':f'{p} 净利润至CFO补充资料保留 {len(quantities)} 行调整；未解释差额 {residual["value"] if residual["value"] is not None else "未知"} 元',
                'basis':f'indirect_bridge.{bidx}_{p}_residual'})
            for k,qs in categories.items():
                if k=='未识别' and not qs:continue
                groups.append({'key':f'{bidx}_{p}_{k}','period':p,'category':k,'amount':compute(qs,sum,formula='该类别披露有符号调整之和') if qs else cell('0',currency=st.currency,formula='该类别没有披露行；空集贡献0'),'basis':'按各行归类依据汇总；这是净利润至CFO调节贡献，不是收入或现金收支归因'})
    if blocks:
        tables['indirect_bridge']=table({'key':col('行键'),'period':col('期间'),'item':col('完整原披露行'),'direction':col('方向'),'amount':col('有符号金额','百万元',st.currency),'category':col('贡献类别'),'basis':col('依据')},rows)
        tables['indirect_contributions']=table({'key':col('行键'),'period':col('期间'),'category':col('类别'),'amount':col('调节贡献','百万元',st.currency),'basis':col('归类与解释边界')},groups)
    else:
        st.missing.append({'metric':'indirect_bridge','period':','.join(st.periods),'reason':'未找到将净利润调节为经营活动现金流量的披露表；不以直接法替代','candidates':[]})


def quarterly_tables(d,tables,selected,reconc):
    rows=[];checks=[];st=d.st
    for t in d.tabs:
        if not t['rows'] or not d.applies(t):continue
        columns={quarter(h):(i,h) for i,h in enumerate(t['rows'][0]) if quarter(h)}
        if len(columns)!=4:continue
        for i,raw in enumerate(t['rows'][1:],1):
            kind=row_kind(raw[0]);r={'key':t['table_id']+'_'+str(i+1),'metric':raw[0],'recognized':kind or '未识别'}
            r.update({f'Q{q}':d.quantity(t,i,c,h) for q,(c,h) in columns.items()});rows.append(r)
            if kind is None:
                d.unknown.append({'item':raw[0],'reason':'季度指标未识别，四季原值保留','source':{'table_id':t['table_id'],'page':t['page'],'raw_row':raw}});continue
            p=d.year+'-FY';annual=missing('本次分析未包含季度表所属全年')
            if p in selected:
                fact=selected[p].get(kind)
                annual=next(x['disclosed'] for x in reconc if x['key']==p) if kind=='deducted_profit' else record_quantity(fact) if fact else missing('缺少同口径全年值')
            total=compute([r[f'Q{q}'] for q in ('1','2','3','4')],sum,formula='第一至第四季度披露金额合计')
            gap=compute([annual,total],lambda v:v[0]-v[1],formula='披露全年-四季度合计')
            checks.append({'key':r['key'],'metric':raw[0],'annual':annual,'quarters':total,'residual':gap})
            for q in ('1','2','3','4'):
                v=r['Q'+q]['value']
                if v is not None and number(v)<0:
                    tables['observations']['rows'].append({'key':r['key']+'_Q'+q,'finding':f'{d.year} Q{q} {compact(raw[0])}为负：{v} {r["Q"+q]["unit"]}','basis':'quarterly.'+r['key']})
            tables['observations']['rows'].append({'key':r['key']+'_annual','finding':f'{d.year} {compact(raw[0])}全年减四季合计：{gap["value"] if gap["value"] is not None else "未知"} 元','basis':'quarterly_reconciliation.'+r['key']})
    if rows:
        tables['quarterly']=table({'key':col('行键'),'metric':col('原披露指标'),'recognized':col('指标映射'),**{f'Q{q}':col(d.year+' Q'+q,'百万元',st.currency) for q in ('1','2','3','4')}},rows)
        tables['quarterly_reconciliation']=table({'key':col('行键'),'metric':col('指标'),**{k:col(v,'百万元',st.currency) for k,v in [('annual','披露全年'),('quarters','四季合计'),('residual','全年减四季合计')]}},checks)
    else:st.missing.append({'metric':'quarterly','period':d.year,'reason':'未找到四个单季度列的主要财务数据表','candidates':[]})

"""Project-scoped K4 retrieval and explicit, non-ranking reference comparisons."""
from collections import defaultdict
from datetime import date
import json
import re

from .financial_workpapers import WorkpaperInputError, cell, col, table, load_facts, meta, source
from .workpaper_expectations import expectations_report, identity, publisher_key, quantity
from .workpaper_period_selection import canonical_period, normalize_periods, normalize_period_records
from .workpaper_constraints import constraint, issue, record_issues, attach_constraints

METRICS = {'revenue':'revenue','营业收入':'revenue','收入':'revenue',
           'net_profit_parent':'net_profit_parent','归母净利润':'net_profit_parent',
           'eps':'eps','EPS':'eps','每股收益':'eps',
           'basic_eps':'eps','eps_basic':'eps','eps_diluted':'eps','diluted_eps':'eps',
           'net_profit':'net_profit'}


def label(r):
    return r.get('label') or meta(r).get('label') or r['metric']


def eps_basis(r, page=''):
    text=label(r)
    if re.search(r'最新摊薄|latest.*dilut',text,re.I):return 'latest_shares'
    if re.search(r'基本|basic',text,re.I):return 'basic'
    if re.search(r'稀释|diluted',text,re.I):return 'diluted'
    if re.search(r'总股本数为|按.*总股本.*计算',page):return 'forecast_total_shares'
    return r.get('basis') or 'unspecified'


def page_ranges(pages):
    groups=[]
    for p in sorted(set(pages)):
        if groups and p==groups[-1][-1]+1:groups[-1].append(p)
        else:groups.append([p])
    return ', '.join(str(g[0]) if len(g)==1 else f'{g[0]}–{g[-1]}' for g in groups)


def candidate_issue(r, rows):
    dims=r.get('dimensions') or {}
    if dims.get('summary_type') or re.search(r'平均值|中间值|中位数',r['source_ref'].get('text','').split('|')[0]):
        return '可比公司汇总行，不是该主体预测'
    s=r['source_ref'];row=s.get('row');column=s.get('column')
    if rows and row and column and row<=len(rows):
        cells=rows[row-1][:column-1]
        # In side-by-side statements the label is the closest text to the left.
        texts=[str(c) for c in cells if re.search(r'[\u4e00-\u9fffA-Za-z]',str(c))]
        row_label=texts[-1] if texts else ''
        patterns={'revenue':r'收入|revenue|sales','net_profit_parent':r'净利|利润|profit',
                  'net_profit':r'净利|利润|profit','eps':r'EPS|每股收益|earnings.per.share'}
        matrix=bool(dims.get('security_name')) or dims.get('financial_item')=='comparable_valuation'
        if row_label and not matrix and not re.search(patterns[r['metric']],row_label,re.I):
            return f'来源坐标行名与指标不符：原表为「{row_label}」，记录为「{label(r)}」；不修写数据'
    # These dimensions may be semantic or a normalization defect. Neither is
    # permission to erase them and manufacture a company-total comparison.
    if dims and set(dims)-{'source_table','security_name','financial_item'}:
        return '包含未对齐的经济维度，不能作为公司总额预测'
    if dims.get('financial_item') and dims['financial_item']!='earnings_forecast_matrix':
        return 'financial_item 维度未对齐，保留原记录待核对'
    if r['metric']=='net_profit':return '净利润归母身份未定，不能与归母预测或实际值混算'
    return None


def load_inputs(service, project, company, document_id, periods, metrics, scope):
    """Join aliases within one project; preserve original IDs and dimensions."""
    service.store.project(project)
    scope={'合并':'consolidated','母公司':'parent'}.get(scope,scope)
    if document_id:service.store.document(project,document_id)
    with service.store.connect() as db:
        entities=[dict(r) for r in db.execute('SELECT * FROM research_entities WHERE project_id=? AND kind=?',(project,'company'))]
        for e in entities:
            e['names']={e['name'],*json.loads(e['aliases_json'])}
            e['identifiers']=json.loads(e['identifiers_json'])
        profiles={r['document_id']:json.loads(r['profile_json']) for r in db.execute('SELECT document_id,profile_json FROM document_profiles WHERE project_id=?',(project,))}
        if document_id and not company:
            company=service.store.document(project,document_id)['company']
        if not company:raise WorkpaperInputError('expectations 请提供 company，或实际财报 document_id')
        selected=[e for e in entities if company in e['names']]
        if not selected:selected=[e for e in entities if any(company in n for n in e['names'])]
        names=set().union(*(e['names'] for e in selected)) if selected else {company}
        selected=[e for e in entities if names & e['names']]
        tickers={e['identifiers']['ticker'] for e in selected if e['identifiers'].get('ticker')}
        exchanges={e['identifiers']['exchange'] for e in selected if e['identifiers'].get('exchange')}
        if len(tickers)>1 or len(exchanges)>1:
            raise WorkpaperInputError('主体名称对应不同证券身份，请使用明确的主体名称或实际财报 document_id')
        if not selected:raise WorkpaperInputError('该项目没有匹配主体的研报实体：'+company)
        names=set().union(*(e['names'] for e in selected));ids={e['entity_id'] for e in selected}
        canonical=sorted(ids)[0]
        raw=[dict(r) for r in db.execute('SELECT * FROM research_records WHERE project_id=? AND is_current=1',(project,)) if r['entity_id'] in ids]
        docs={r['document_id'] for r in raw}
        source_tables={r['table_id']:json.loads(r['rows_json']) for d in docs for r in db.execute('SELECT table_id,rows_json FROM source_tables WHERE document_id=?',(d,))}
        pages={(d,r['page']):r['text'] for d in docs for r in db.execute('SELECT page,text FROM pages WHERE document_id=?',(d,))}
    facts=normalize_period_records([r for r in load_facts(service,project,document_id) if r['company'] in names and (r['scope']==scope or r['scope'].startswith(scope+'_'))])
    for r in raw:
        r.update(json.loads(r.pop('record_json')));r['source_ref']=json.loads(r.pop('source_json'))
        if r.get('period'):r['period']=canonical_period(r['period'])
    available={r['period'] for r in raw if r.get('period')}
    available.update(r['period'] for r in facts if meta(r).get('statement')=='income')
    if not periods:
        actual_periods={r['period'] for r in facts if r['metric']=='revenue' and meta(r).get('statement')=='income'
                        and not (r['period'].endswith('FY') and re.search(r'季度|半年度|中期|interim|quarter',profiles.get(r['document_id'],{}).get('title',''),re.I))}
        periods=normalize_periods(None,actual_periods or available)[:1]
    periods=normalize_periods(periods,available)
    if isinstance(metrics,str):metrics=[m for m in re.split(r'[,，、\s]+',metrics) if m]
    requested={METRICS.get(m,m) for m in (metrics or ['revenue','net_profit_parent','eps'])}
    unsupported=requested-{'revenue','net_profit_parent','eps','net_profit'}
    if unsupported:raise WorkpaperInputError('expectations 当前数据库入口支持收入、归母净利润、EPS：'+', '.join(sorted(unsupported)))
    wanted=requested|({'net_profit'} if 'net_profit_parent' in requested else set())
    records=[]
    for r in raw:
        metric=METRICS.get(r.get('metric'))
        if metric not in wanted or r.get('period') not in periods:continue
        r.update(source_entity_id=r['entity_id'],entity_id=canonical,company=company,source_metric=r['metric'],metric=metric)
        r['label']=label(r)
        r['restatement']=meta(r).get('restatement','unspecified')
        if metric=='eps':
            page=pages.get((r['document_id'],r['source_ref'].get('page')),'')
            r['basis']=eps_basis(r,page)
            footnote=re.search(r'.{0,25}(?:总股本数为|按.*总股本.*计算).{0,60}',page)
            r['basis_evidence']={'document_id':r['document_id'],'page':r['source_ref'].get('page'),
                                 'quote':footnote[0] if r['basis']=='forecast_total_shares' and footnote else label(r)}
        r['exclusion_reason']=candidate_issue(r,source_tables.get(r['source_ref'].get('table_id'),[]))
        records.append(r)
    actuals=[];actual_exclusions=[]
    for r in facts:
        metric=METRICS.get(r['metric'])
        if metric not in requested or r['period'] not in periods or meta(r).get('statement')!='income':continue
        if meta(r).get('dimensions'):continue
        title=profiles.get(r['document_id'],{}).get('title','')
        if r['period'].endswith('FY') and re.search(r'季度|半年度|中期|interim|quarter',title,re.I):
            actual_exclusions.append({'key':r['fact_id'],'label':label(r),'reason':'年额标签出现在季报/中报利润表，期间身份待核；未用作全年实际值','source':json.dumps(source(r),ensure_ascii=False)})
            continue
        r={**r,'entity_id':canonical,'scenario':'unspecified','published_at':profiles.get(r['document_id'],{}).get('published_at'),
           'label':label(r),'source_metric':r['metric'],'metric':metric}
        if metric=='eps':r['basis']=eps_basis(r)
        actuals.append(r)
    return records,actuals,{'company':company,'periods':periods,'entity_ids':sorted(ids),'names':sorted(names),'documents':sorted({r['document_id'] for r in records+actuals}), 'actual_exclusions':actual_exclusions}


def context_tables(records, actuals, cutoff):
    """Latest by institution/metric, plus cross-basis history without false joins."""
    eligible=[r for r in records if r['data_kind']=='analyst_forecast' and r.get('published_at') and (not cutoff or r['published_at']<=cutoff)
              and (not r.get('exclusion_reason') or r['metric']=='net_profit' and '归母身份' in r['exclusion_reason'])]
    groups=defaultdict(list)
    for r in eligible:
        family='profit_attribution' if r['metric'] in ('net_profit','net_profit_parent') else r['metric']
        # A scope/segment/scenario difference never supersedes an independent series.
        groups[(publisher_key(r['publisher']),r['entity_id'],r['period'],family,r.get('scope'),r.get('scenario'),r['currency'])].append(r)
    tabs={};latest=[]
    for items in groups.values():
        dates=sorted({r['published_at'] for r in items})
        for r in items:r['superseded_for_comparison']=r['published_at']!=dates[-1]
        latest.extend(r for r in items if r['published_at']==dates[-1] and not r.get('exclusion_reason'))
        for prev_date,current_date in zip(dates,dates[1:]):
            prev=[r for r in items if r['published_at']==prev_date];curr=[r for r in items if r['published_at']==current_date]
            if len(prev)!=1 or len(curr)!=1:continue  # Conflicts remain in the full ledger/core.
            a,b=prev[0],curr[0];qa,qb=quantity(a),quantity(b)
            aligned=identity(a,qa)==identity(b,qb)
            same_metric=a['metric']==b['metric'] and (qa['unit'],qa['currency'])==(qb['unit'],qb['currency'])
            refs=[qa['source'],qb['source']]
            reason='同口径修正' if aligned else '维度或每股口径未对齐，仅原数变化；不视为同口径修正'
            if not same_metric:reason='前值净利润归母身份未定；保留关联，不计算归母修正'
            name=f'version_links_{qb["currency"] or "unitless"}_{qb["dimension"]}';t=tabs.setdefault(name,table({
                'key':col('行键'),'institution':col('机构'),'period':col('年度'),'metric':col('当前指标'),
                'previous_date':col('前次日期'),'published_at':col('本次日期'),'previous':col('前值',qb['unit'],qb['currency']),
                'value':col('本次值',qb['unit'],qb['currency']),'change':col('原数变化（非必然同口径）',qb['unit'],qb['currency']),
                'previous_dimensions':col('前次维度'),'dimensions':col('本次维度'),'status':col('可比性')},[]))
            t['rows'].append({'key':b['record_id'],'institution':publisher_key(b['publisher']),'period':b['period'],'metric':b['metric'],
                'previous_date':prev_date,'published_at':current_date,'previous':cell(qa['value'],qa['unit'],qa['currency'],[qa['source']]),
                'value':cell(qb['value'],qb['unit'],qb['currency'],[qb['source']]),
                'change':cell(qb['value']-qa['value'] if same_metric and qa['value'] is not None and qb['value'] is not None else None,qb['unit'],qb['currency'],refs,'current_forecast-previous_forecast',None if same_metric else reason),
                'previous_dimensions':json.dumps(a.get('dimensions',{}),ensure_ascii=False),'dimensions':json.dumps(b.get('dimensions',{}),ensure_ascii=False),'status':reason})
            if not aligned:
                limits=t.setdefault('answer_constraints', [])
                pair=constraint(name, b['record_id'], ['previous','value','change'],
                    record_issues(b, [a]) + [issue('metric' if not same_metric else 'version_identity', reason)],
                    metric=b['metric'], period=b['period'], record_ids=[a['record_id'], b['record_id']], evidence=refs)
                pair['prohibited_uses'].append('same_basis_revision')
                if not same_metric and a['metric']=='net_profit':
                    pair['prohibited_uses'].append('parent_profit_comparison')
                    limits.append(constraint(name, b['record_id'], ['previous'],
                        [issue('profit_attribution','前值利润归属未明；本次归母标签不回填给前值')],
                        metric=a['metric'],period=a['period'],record_ids=[a['record_id']],evidence=[qa['source']],code='profit_attribution_unknown'))
                limits.append(pair)
    return tabs,latest


def reference_tables(latest, actuals):
    tabs={}
    for r in latest:
        q=quantity(r)
        candidates=[a for a in actuals if (a['entity_id'],a['period'],a['metric'])==(r['entity_id'],r['period'],r['metric'])
                    and (quantity(a)['unit'],quantity(a)['currency'])==(q['unit'],q['currency'])]
        if r['metric']=='eps':
            exact=[a for a in candidates if a.get('basis')==r.get('basis')]
            candidates=exact or [a for a in candidates if a.get('basis')=='basic']
        if not candidates:continue
        if r.get('scope')!='unspecified' and any(identity(a,quantity(a))[:4]+identity(a,quantity(a))[5:]==identity(r,q)[:4]+identity(r,q)[5:] for a in candidates):continue
        values={quantity(a)['value'] for a in candidates};v=next(iter(values)) if len(values)==1 else None
        issues=[]
        if r.get('scope') in (None,'unspecified'):issues.append('机构会计/合并范围未明确')
        elif {a['scope'] for a in candidates}!={r['scope']}:issues.append('报告口径不同')
        if r['metric']=='eps' and {a.get('basis') for a in candidates}!={r.get('basis')}:issues.append('EPS 分母口径不同或未明确，实际参照为基本 EPS')
        if r['metric']=='revenue':issues.append('按营业收入标签参照；需另核营业总收入边界，未自动改标')
        if r.get('dimensions'):issues.append('来源维度未对齐')
        if {a.get('restatement') for a in candidates}!={r.get('restatement')}:issues.append('重述口径不同或未明确')
        reason='；'.join(issues) or '每股或重述口径未对齐'
        # Same-day conflicting forecasts must not acquire definite gaps here.
        peers=[b for b in latest if identity(b,quantity(b))==identity(r,q) and publisher_key(b['publisher'])==publisher_key(r['publisher']) and b['published_at']==r['published_at']]
        conflict=len({quantity(b)['value'] for b in peers})>1
        blocked='同日同口径预测冲突' if conflict else ('同口径实际值冲突或缺值' if v is None else ('预测缺值' if q['value'] is None else None))
        diff=v-q['value'] if not blocked else None
        refs=[q['source'],*[quantity(a)['source'] for a in candidates]]
        name=f'reference_gaps_{q["currency"] or "unitless"}_{q["dimension"]}'
        t=tabs.setdefault(name,table({'key':col('行键'),'institution':col('机构'),'published_at':col('预测日期'),'period':col('年度'),'metric':col('指标'),
            'forecast':col('最近预测',q['unit'],q['currency']),'actual':col('年报参照',q['unit'],q['currency']),
            'difference':col('实际参照减预测',q['unit'],q['currency']),'difference_rate':col('参照差异率','%'),
            'forecast_basis':col('预测口径'),'actual_basis':col('实际口径'),'status':col('限制（不参与误差排名）')},[]))
        t['rows'].append({'key':r['record_id'],'institution':publisher_key(r['publisher']),'published_at':r['published_at'],'period':r['period'],'metric':r['metric'],
            'forecast':cell(q['value'],q['unit'],q['currency'],[q['source']]),'actual':cell(v,q['unit'],q['currency'],[quantity(a)['source'] for a in candidates]),
            'difference':cell(diff,q['unit'],q['currency'],refs,'actual_reference-forecast',blocked),
            'difference_rate':cell(diff/abs(q['value'])*100 if diff is not None and q['value']!=0 else None,'%',sources=refs,formula='(actual_reference-forecast)/abs(forecast)*100',reason=blocked or ('预测为零' if q['value']==0 else None)),
            'forecast_basis':str(r.get('scope'))+' / '+str(r.get('basis')),
            'actual_basis':', '.join(sorted({a['scope']+' / '+str(a.get('basis')) for a in candidates})),
            'status':(blocked+'；' if blocked else '')+'仅数值参照；'+reason})
        t.setdefault('answer_constraints', []).append(constraint(name, r['record_id'], ['forecast','actual','difference','difference_rate'],
            record_issues(r, candidates) + [issue('comparison_identity', reason)], metric=r['metric'], period=r['period'],
            record_ids=[r['record_id'], *[a.get('fact_id') for a in candidates]], evidence=refs))
    return tabs


def expectations(service, project, company=None, document_id=None, periods=None, scope='consolidated', focus=None, as_of=None, metrics=None):
    if as_of:date.fromisoformat(as_of)
    records,actuals,selection=load_inputs(service,project,company,document_id,periods,metrics,scope)
    links,latest=context_tables(records,actuals,as_of)
    report=expectations_report(records,actuals,as_of)
    report['periods']=selection['periods']
    report['tables'].update(links)
    report['tables'].update(reference_tables(latest,actuals))
    attach_constraints(report, [c for t in report['tables'].values() for c in t.get('answer_constraints', [])])
    for r in actuals:
        q=quantity(r);name=f'actuals_{q["currency"] or "unitless"}_{q["dimension"]}'
        t=report['tables'].setdefault(name,table({'key':col('行键'),'metric':col('指标'),'label':col('原行名'),'period':col('期间'),
            'value':col('年报实际值',q['unit'],q['currency']),'scope':col('合并及准则口径'),'basis':col('每股口径'),'published_at':col('实际披露日（未知留空）')},[]))
        t['rows'].append({'key':r['fact_id'],'metric':r['metric'],'label':r['label'],'period':r['period'],'value':cell(q['value'],q['unit'],q['currency'],[q['source']]),'scope':r['scope'],'basis':r.get('basis'),'published_at':r.get('published_at')})
    report['tables']['missing']=table({k:col(v) for k,v in [('key','行键'),('label','原行名'),('reason','限制'),('source','来源')]},selection['actual_exclusions'])
    coverage=[]
    with service.store.connect() as db:
        for did in selection['documents']:
            doc=service.store.document(project,did)
            parsed={r['table_id']:r['page'] for r in db.execute('SELECT table_id,page FROM source_tables WHERE document_id=?',(did,))}
            used={r[0] for r in db.execute('SELECT DISTINCT json_extract(source_json,\'$.table_id\') FROM research_records WHERE project_id=? AND document_id=? AND is_current=1',(project,did))}
            used.update(r[0] for r in db.execute('SELECT DISTINCT json_extract(source_json,\'$.table_id\') FROM current_financial_facts WHERE project_id=? AND document_id=?',(project,did)))
            missing=sorted({page for tid,page in parsed.items() if tid not in used})
            coverage.append({'key':did,'document':doc['original_name'],'state':doc['state'],'unrecorded_table_pages':page_ranges(missing),
                'note':'这些页存在已解析但未结构化的表；非整页缺失。'})
    report['tables']['coverage']=table({k:col(v) for k,v in [('key','文档'),('document','报告名'),('state','入库状态'),('unrecorded_table_pages','无记录表所在 PDF 页'),('note','覆盖限制')]},coverage)
    report['tables']['coverage']['report_section']='limitations'
    notes=[{'key':'identity','finding':'主体连接仅使用项目内名称/别名与不冲突证券身份；原实体：'+', '.join(selection['entity_ids']),'basis':'来源链保留原记录 ID'},
           {'key':'comparison','finding':'reference_gaps 是口径未对齐的数值参照，不是同口径预测误差，不参与最大/最小误差排名。净利润归母身份未定的记录单列。','basis':'reference_gaps / excluded / version_links'}]
    if selection['actual_exclusions']:notes.append({'key':'actual_period','finding':f'{len(selection["actual_exclusions"])} 条季报/中报年额标签与报告期间不符，单列而未作为全年实际值。','basis':'missing'})
    notes.append({'key':'coverage','finding':'结果仅覆盖当前入库记录；逐报告未结构化表的页码与进行中状态见 coverage。实际披露日缺失时保持未知，实际参照不代表截止日前已知。','basis':'coverage / actuals'})
    for name,t in report['tables'].items():
        titles={'ledger':'机构预测记录','excluded':'未纳入当时预期的记录','revisions':'同口径版本记录','actual_vs_expected':'同口径实际与预测','actuals':'年报实际值'}
        for prefix,title in titles.items():
            if name.startswith(prefix+'_'):t.setdefault('title',title)
        if name.startswith(('reference_gaps','version_links')):
            t['title']=('实际与最近预测的数值参照（口径未对齐）' if name.startswith('reference') else '机构前后版本关联（保留口径差异）')
            notes.append({'key':name,'finding':t['title']+f'：{len(t["rows"])} 行；准确差额和限制见绑定表。','basis':name})
        if name.startswith('excluded'):
            issues=defaultdict(list)
            for row in t['rows']:issues[(row['publisher'],row['published_at'],row['status'])].append(row)
            for i,((publisher,publication,status),rows) in enumerate(issues.items()):
                notes.append({'key':name+'_'+str(i),'finding':publisher+' '+str(publication)+f'：{status}（{len(rows)} 条，原值与来源逐条保留）','basis':name})
    for note in notes:note['table']=note.pop('basis')
    report['tables']['observations']['rows'].extend(notes)
    # The workbook/A1 retain every column; the narrative package uses the financial
    # fields below so source IDs and raw JSON do not squeeze the numeric columns.
    for name,t in report['tables'].items():
        if name.startswith('reference_gaps'):fields=['institution','metric','forecast','actual','difference','difference_rate','status']
        elif name.startswith('version_links'):fields=['institution','previous_date','published_at','metric','previous','value','change','status']
        elif name.startswith('actual_vs_expected'):fields=['institution','metric','value','actual','difference','difference_rate','status']
        elif name.startswith('revisions'):fields=['institution','published_at','metric','previous','value','change','status']
        elif name.startswith(('ledger','excluded')):fields=['institution','published_at','period','label','value','status']
        elif name=='coverage':fields=['document','state','unrecorded_table_pages','note']
        elif name=='missing':fields=['label','reason']
        elif name=='observations':fields=['finding']
        else:continue
        t['report_columns']=fields
    for t in report['tables'].values():
        for c in t['columns'].values():
            if c.get('unit')=='元':c['unit']='百万元';c['decimals']=4
        if 'metric' in t['columns']:
            t['columns']['metric_label']=col('指标名称')
            for r in t['rows']:r['metric_label']={'revenue':'营业收入','net_profit_parent':'归母净利润','net_profit':'净利润（归属未明）','eps':'EPS'}.get(r.get('metric'),r.get('metric'))
            if t.get('report_columns'):t['report_columns']=['metric_label' if k=='metric' else k for k in t['report_columns']]
    report['body']+=' 机构只统一法律后缀，展示名保留；同日冲突不任取。跨维度版本只关联，不删除维度。reference_gaps 明示未对齐口径，仅展示原数算术差额。'
    return report,records+actuals

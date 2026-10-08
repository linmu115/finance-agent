"""Economic dimensions with source-cell/section evidence, independent of the model."""
import re


def apply_source_dimensions(table, facts, page_text='', context=None):
    rows=table['rows']
    counterparty_columns={c for row in rows[:3] for c,raw in enumerate(row,1)
                          if re.fullmatch(r'\s*(?:关联方(?:名称)?|交易对方|往来单位(?:名称)?|Related part(?:y|ies)|Counterparty)\s*',str(raw),re.I)}
    total_rows={f['metric']:{g['source']['row'] for g in facts if g['metric']==f['metric'] and
                re.fullmatch(r'\s*(?:合\s*计|总\s*计|小\s*计|Total|Subtotal)\s*',str(rows[g['source']['row']-1][0]),re.I)} for f in facts}
    # Prefer the section preceding the actual table (geometry-aware when
    # available); the whole page can contain a later, unrelated section.
    prefix=(context or {}).get('text',page_text)
    headings=re.findall(r'(?m)^\s*\d+[、.．]\s*([^\n]+)',prefix)
    side=('asset' if headings[-1].endswith('资产') else 'liability' if headings[-1].endswith('负债') else None) if headings else None
    for fact in facts:
        ref=fact['source'];meta=ref['normalization'];row=ref['row'];cells=rows[row-1]
        dims=meta.setdefault('dimensions',{});proof=meta.setdefault('source_dimension_evidence',{})
        for column in counterparty_columns:
            if column<=len(cells) and str(cells[column-1]).strip() and column!=ref['column']:
                value=str(cells[column-1]).strip()
                dims['related_party']=value;proof['related_party']={'row':row,'column':column,'text':value}
        # Repair only empty component names introduced by this source rule.
        if not str(cells[0]).strip() and dims.get('component') == '' and 'composition' in proof:
            dims.pop('composition', None);dims.pop('component', None);proof.pop('composition', None)
        if str(cells[0]).strip() and total_rows.get(fact['metric']) and row not in total_rows[fact['metric']]:
            dims['composition']='component';dims['component']=str(cells[0]).strip()
            proof['composition']={'row':row,'column':1,'text':cells[0],'total_rows':sorted(total_rows[fact['metric']])}
        # Direction-neutral instrument labels can appear on both sides of the
        # balance sheet. Direction-bearing metrics already encode this identity.
        if side and not re.search(r'asset|liabil|payabl|receivabl|cash|equity|debt',fact['metric'],re.I):
            dims['balance_side']=side;proof['balance_side']={'page':table['page'],'heading':headings[-1]}
        if not proof:meta.pop('source_dimension_evidence',None)
    return facts

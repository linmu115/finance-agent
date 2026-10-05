"""Bounded verbatim header references for multi-page tables, not semantic rules."""
import re
from .normalization import numeric_candidate

def source_structure_context(parsed,table):
    page=table['page'];width=max(map(len,table['rows']),default=0)
    major=[];minor=[];pages={p['page']:p['text'] for p in parsed['pages']}
    for number,text in pages.items():
        if number>page:continue
        for raw in text.splitlines():
            line=raw.strip()
            if not 2<=len(line)<=100:continue
            if re.match(r'^(?:第.{1,8}[章节]|[一二三四五六七八九十百]+[、．.])',line):major.append((number,line))
            elif re.fullmatch(r'\d{1,2}[、．.]\s*[^\d]+',line):minor.append((number,line))
    context=[]
    # The model chooses whether these headings apply. Never assign scope, unit,
    # metric or period in this retrieval helper.
    for number,line in major[-1:]+minor[-1:]:context.append(f'原文标题（物理页{number}）：{line}')
    def headers(candidate):
        return [row for row in candidate['rows'][:3] if sum(bool(str(v).strip()) and not numeric_candidate(str(v)) for v in row[1:])>=2 and not any(numeric_candidate(str(v)) for v in row[1:])]
    if not headers(table):
        candidates=[t for t in parsed['tables'] if t['index']<table['index'] and 0<=page-t['page']<=12 and max(map(len,t['rows']),default=0)==width and headers(t)]
        if candidates:
            candidate=max(candidates,key=lambda t:t['index'])
            context.append(f"同列数的前序表头候选（物理页{candidate['page']}、表{candidate['index']}；须自行核对是否续表）：")
            context.extend(' | '.join(row)[:650] for row in headers(candidate))
            context.extend('原文单位行：'+line.strip()[:250] for line in pages.get(candidate['page'],'').splitlines() if '单位' in line and len(line.strip())<200)
    return '\n'.join(context)[:2400]

def with_structure_context(batch,parsed):
    result=[];marker='本表起始行（仅上下文，不表示都是表头）：'
    for item in batch:
        reference='结构原文参考（仅证据，不能代替当前表的核对）：\n'+source_structure_context(parsed,item['table'])+'\n当前表起始行：'
        # Keep shared page context identical so render_group can deduplicate it.
        text=item['text'].replace(marker,marker+'\n'+reference,1) if marker in item['text'] else reference+'\n'+item['text']
        result.append({**item,'text':text})
    return result

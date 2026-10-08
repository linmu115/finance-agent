"""Read-only audit summarizer; no requests or product mutations."""
import json,re,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from service.analysis_report import bind_text,display_table,format_cell,cell_column
BASE=Path(__file__).parent
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def quantities(text):
    # Counts printed numeric occurrences; manual review confirms exclusions.
    text=re.sub(r'`?[a-f0-9]{24,}(?:-[a-f0-9-]+)?`?', '',text)
    text=re.sub(r'https?://[^\s)）]+','',text)
    text=re.sub(r'(?<!\d)(?:19|20)\d{2}(?:[-年](?:FY|H[12]|Q[1-4]|\d{1,2}月?)?)?', '',text)
    text=re.sub(r'(?i)\bQ[1-4]\b|\bH[12]\b','',text)
    text=re.sub(r'第\s*[\d、,，–—\-至及与/\s]+\s*页','',text)
    text=re.sub(r'PDF\s*[\d、,，–—\-至及与/\s]+\s*页','',text)
    text=re.sub(r'(?i)(?<![A-Za-z])p(?:age)?\.?\s*\d+(?:\s*[,、，–—\-/]\s*(?:p(?:age)?\.?\s*)?\d+)*','',text)
    text=re.sub(r'^\s*\d+[.)、]\s*','',text,flags=re.M)
    return [dict(value=m.group(),context=text[max(0,m.start()-24):m.end()+28].replace('\n',' ')) for m in re.finditer(r'(?<![A-Za-z_\d])[-+−]?\d[\d,]*(?:\.\d+)?(?:\s*%|个百分点|倍|亿元|百万元|万元|元)?',text)]
allcases=[]
for d in sorted((BASE/'runs').glob('Q*-*')):
    if not (d/'result.json').exists():continue
    start=json.loads((d/'start.json').read_text(encoding='utf-8'));result=json.loads((d/'result.json').read_text(encoding='utf-8'))
    auditpath=d/'app-data'/'audit'/(start['runId']+'.jsonl')
    events=[dict(json.loads(line),line=i+1) for i,line in enumerate(auditpath.read_text(encoding='utf-8').splitlines())]
    tables={};calls=[];errors=[];requests=[];bounds=[];workpapers=[]
    for e in events:
        data=e['data'];kind=e['type']
        if kind=='tool_request':calls.append(dict(line=e['line'],**data))
        elif kind=='tool_result':
            envelope=data.get('result',{});payload=envelope.get('data',{})
            if not isinstance(payload,dict):continue
            if envelope.get('status') in ('error','failed') or payload.get('status')=='failed' or payload.get('state')=='failed':
                errors.append(dict(type='tool_return_failure',line=e['line'],name=data.get('name'),error=payload.get('error') or envelope.get('error'),stderr=payload.get('stderr')))
            for name in payload.get('scenario_context',{}).get('unqualified_names',[]):tables.pop(name,None)
            registered=payload.get('numeric_tables') or payload.get('report',{}).get('tables') or payload.get('result',{}).get('report',{}).get('tables') or {}
            tables.update(registered)
            if data.get('name')=='financial_workpaper':workpapers.append(dict(line=e['line'],toolCallId=data.get('toolCallId'),status=envelope.get('status'),data=payload))
        elif kind in ('tool_error','answer_binding_error'):errors.append(dict(type=kind,line=e['line'],data=data))
        elif kind=='model_request':requests.append(dict(line=e['line'],**data))
        elif kind=='answer_bound':bounds.append(dict(line=e['line'],**data))
    answer=(d/'answer.md').read_text(encoding='utf-8')
    template=bounds[-1]['template'] if bounds else answer
    bound_values=[];placeholders=[]
    for m in re.finditer(r'\{\{[^{}]+\}\}',template):
        try:rendered=bind_text(m.group(),tables)
        except ValueError as exc:rendered='';errors.append(dict(type='offline_binding_error',message=str(exc)))
        token=m.group()[2:-2].strip()
        if token.startswith('table:'):
            tab=tables[token[6:].strip()];display=display_table(tab);vals=[]
            for i,row in enumerate(display['rows']):
                for key,col in tab['columns'].items():
                    numeric=row.get(key) is not None and re.fullmatch(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?',str(row[key]))
                    if numeric and key not in ('key','period','year',tab.get('row_key')):
                        value=format_cell(row[key],cell_column(tab,i,key),with_unit=True)
                        vals.append(dict(value=value,context=f'{token}[{i}].{key}'))
        else:vals=quantities(rendered)
        bound_values+=vals;placeholders.append(dict(token=m.group(),rendered=rendered,values=vals))
    unbound=quantities(re.sub(r'\{\{[^{}]+\}\}','',template))
    tags=lambda s:dict(Counter(re.findall(r'【(?:事实/数据|事实|推论[^】]*|观点)】',s)))
    workpaper_results=[]
    for w in workpapers:
        request=next(c for c in calls if c.get('toolCallId')==w['toolCallId'])
        workpaper_results.append({'kind':request['args'].get('kind','statement_analysis'),'line':w['line'],'status':w['status'],'period_roles':w['data'].get('period_roles'),'error':w['data'].get('error')})
    info=dict(case=start['caseId'],profile=start['profile'],run_id=start['runId'],question=start['question'],status=result['run']['status'],duration_ms=result['durationMs'],usage=result['run'].get('usage'),workpaper_results=workpaper_results,
              calls=calls,errors=errors,requests=requests,workpaper_kinds=[x.get('args',{}).get('kind','statement_analysis') for x in calls if x.get('name')=='financial_workpaper'],
              binding=dict(bound=len(bound_values),unbound=len(unbound),total=len(bound_values)+len(unbound),ratio=len(bound_values)/(len(bound_values)+len(unbound)) if bound_values or unbound else None,placeholders=placeholders,unbound_values=unbound),
              tags_raw=tags(template),tags_final=tags(answer),all_labels_raw=dict(Counter(re.findall(r'【[^】]+】',template))),all_labels_final=dict(Counter(re.findall(r'【[^】]+】',answer))),answer_bound_events=len(bounds),answer_bound_line=bounds[-1]['line'] if bounds else None)
    dump(d/'audit-summary.json',info);dump(d/'workpapers.json',workpapers);dump(d/'a1-tables.json',tables)
    (d/'template.md').write_text(template,encoding='utf-8')
    allcases.append(info)
dump(BASE/'summary.json',allcases)
for x in allcases:
    print(json.dumps({k:x[k] for k in ['case','profile','status','workpaper_kinds','tags_raw','tags_final']}|dict(binding={k:x['binding'][k] for k in ['bound','unbound','total','ratio']},requests=len(x['requests']),errors=len(x['errors'])),ensure_ascii=False))

"""Package observations only. No model calls or product changes."""
import json, shutil
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
OUT=ROOT/'docs/evidence/n4-adoption-fixes-20261008'
OUT.mkdir(parents=True,exist_ok=True)
oldroot=Path(r'D:\AI\财报agent-wt\adoption-preflight\docs\evidence\n4-adoption-preflight-20261008')
shutil.copytree(oldroot,OUT/'baseline',dirs_exist_ok=True)
summary=json.loads((BASE/'summary.json').read_text(encoding='utf8'))
before=json.loads((oldroot/'summary.json').read_text(encoding='utf8'))
reviews=json.loads((BASE/'manual-review.json').read_text(encoding='utf8'))
assert len(summary)==12
assert len(reviews)==12
manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf8'))
for name in ('summary.json','manual-review.json','manifest.json','worker.ts','run_all.py','extract.py','package_evidence.py'):
    shutil.copy2(BASE/name,OUT/name)
def dump(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def totals(rows):
    result={}
    for arm in ('financial','prepared'):
        chosen=[r for r in rows if r['profile']==arm]
        keys=('calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls')
        result[arm]={k:sum(r['usage'][k] for r in chosen) for k in keys}
        result[arm].update(sessions=len(chosen),bound=sum(r['binding']['bound'] for r in chosen),unbound=sum(r['binding']['unbound'] for r in chosen),
                          sessions_with_binding=sum(r['binding']['bound']>0 for r in chosen),tool_errors=sum(len(r['errors']) for r in chosen))
        result[arm]['binding_ratio']=result[arm]['bound']/(result[arm]['bound']+result[arm]['unbound']) if result[arm]['bound']+result[arm]['unbound'] else None
    return result
usage={'expense_category':'研发预检','actual_CPA_cost':None,'cost_note':'CPA实际账单未知；原始usage.costUsd仅Pi目录估算，不作为费用对比。','previous':totals(before),'rerun':totals(summary)}
checks=[]
lines=['# 逐题采用与结果核对','',
       '本轮代码 `'+manifest['code_commit']+'`，开发基线 `58a903c`。旧轮 `7524cca` 的数据副本、问题、模型和低/高推理配置保持一致；没有重新入库。这是研发预检，不是正式盲评。','',
       '数值绑定按最终回答中绑定展开的财务数值出现次数统计；整表按非空数值格计，排除年份、季度、页码、序号、ID和URL。手写数值包括抄原文和抄计算结果，不等于错误。任务完成单独检查核心问题、数值与口径，不用绑定率替代。','']
for x in summary:
    key=x['case']+'-'+x['profile'];run=BASE/'runs'/key;dest=OUT/key;dest.mkdir(exist_ok=True)
    for name in ('answer.md','template.md','audit-summary.json','start.json','model.json'):
        shutil.copy2(run/name,dest/name)
    raw=run/'app-data/audit'/ (x['run_id']+'.jsonl')
    for q in x['requests']:
        assert q['model']=='gpt-6-luna'
        assert q['sentReasoningEffort']==('low' if q['phase']=='router' else 'high')
    assert len(x['requests'])==x['usage']['calls']
    payloads=[json.loads(v) for v in (run/'payloads.jsonl').read_text(encoding='utf8').splitlines()]
    assert len(payloads)==len(x['requests'])
    native=[json.loads(v) for v in (run/'native-events.jsonl').read_text(encoding='utf8').splitlines()]
    checks.append({'case':key,'requests':len(payloads),'native_retries':sum(e['type']=='auto_retry_start' for e in native),
                   'native_compactions':sum(e['type']=='auto_compaction_start' for e in native),
                   'tool_counts':sorted({len(p['payload'].get('tools',[])) for p in payloads}),
                   'unknown_usage':x['usage']['unknownCalls']})
    b=x['binding'];u=x['usage'];review=reviews[key]
    old=next(v for v in before if v['case']==x['case'] and v['profile']==x['profile'])
    lines += ['## '+key,'',x['question'].replace('\n','  \n'),'',
        f"绑定 {old['binding']['bound']}/{old['binding']['total']} → {b['bound']}/{b['total']}（{b['ratio']:.1%}）；手写 {old['binding']['unbound']} → {b['unbound']}；请求 {old['usage']['calls']} → {u['calls']}；本轮输入 {u['input']:,} / 输出 {u['output']:,}。",'',
        '[原始回答]('+key+'/answer.md) · [模型模板]('+key+'/template.md) · [数值与调用清单]('+key+'/audit-summary.json) · [原始审计]('+raw.as_posix()+')','',
        ' → '.join(c['name']+('['+c['args'].get('kind','statement_analysis')+']' if c['name']=='financial_workpaper' else '') for c in x['calls']),'',
        '原始标签 '+json.dumps(x['all_labels_raw'],ensure_ascii=False)+'；宿主呈现标签 '+json.dumps(x['all_labels_final'],ensure_ascii=False)+'。','']
    for c in x['calls']:
        if c['name']=='financial_workpaper':lines.append('- `'+c['args'].get('kind','statement_analysis')+'` periods=`'+json.dumps(c['args'].get('periods'),ensure_ascii=False)+'`，原始审计第 '+str(c['line'])+' 行。')
    for result in x.get('workpaper_results',[]):
        lines.append('- 底稿回包：`'+result['kind']+'` '+result['status']+'；'+json.dumps(result.get('period_roles') or result.get('error'),ensure_ascii=False)+'。')
    lines += ['',review['completion'],'']+['- '+t for t in review.get('issues',[])]+['',review['evidence'],'']
    for error in x['errors']:lines.append('工具/绑定失败（用量已包含）：`'+json.dumps(error,ensure_ascii=False).replace('`','')+'`\n')
    if not x['errors']:lines.append('无工具或绑定错误事件。\n')
followbase=BASE.parent/'adoption-followup'
follow=json.loads((followbase/'summary.json').read_text(encoding='utf8'))
assert len(follow)==2
followout=OUT/'followup';followout.mkdir(exist_ok=True)
for name in ('summary.json','manifest.json','worker.ts','run_all.py','extract.py','manual-review.json'):
    shutil.copy2(followbase/name,followout/name)
for x in follow:
    key=x['case']+'-'+x['profile'];run=followbase/'runs'/key;dest=followout/key;dest.mkdir(exist_ok=True)
    for name in ('answer.md','template.md','audit-summary.json','start.json','model.json'):shutil.copy2(run/name,dest/name)
    payloads=[json.loads(v) for v in (run/'payloads.jsonl').read_text(encoding='utf8').splitlines()]
    assert len(payloads)==len(x['requests'])==x['usage']['calls']
    assert all(q['model']=='gpt-6-luna' and q['sentReasoningEffort']==('low' if q['phase']=='router' else 'high') for q in x['requests'])
    native=[json.loads(v) for v in (run/'native-events.jsonl').read_text(encoding='utf8').splitlines()]
    checks.append({'case':key,'attempt':'followup','requests':len(payloads),'native_retries':sum(e['type']=='auto_retry_start' for e in native),'native_compactions':sum(e['type']=='auto_compaction_start' for e in native),'tool_counts':sorted({len(p['payload'].get('tools',[])) for p in payloads}),'unknown_usage':x['usage']['unknownCalls']})
usage['followup']=totals(follow)
usage['development_total']={k:sum(x['usage'][k] for x in [*summary,*follow]) for k in ('calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls')}
usage['development_total']['sessions']=14
usage['binding_sensitivity']={'initial_financial_excluding_workpaper_row_count':{'bound':26,'total':107,'ratio':26/107},'latest_per_question_excluding_workpaper_row_count':{'bound':34,'total':104,'ratio':34/104},'note':'Q5绑定的summary.basis.paired_rows=0是底稿元数据，单列敏感性口径。最新逐题观察取Q3/Q4补测，其余首轮，不是同一代码整轮分数或成本。'}
lines += ['## 两题补测（f21b419）','',
          '原失败记录未覆盖，费用全部保留。Q3/Q4在新的独立会话各补跑一次；补测公司写法发生变化，因此简称修复的直接证据另见原入参离线重放，不把全部回答差异归因于这一个修复。','']
reviews2=json.loads((followbase/'manual-review.json').read_text(encoding='utf8'))
for x in follow:
    key=x['case']+'-'+x['profile'];r=reviews2[key];b=x['binding'];u=x['usage']
    lines += ['### '+key+' 补测','',f"绑定 {b['bound']}/{b['total']}；手写 {b['unbound']}；请求 {u['calls']}，输入 {u['input']:,} / 输出 {u['output']:,}。",'',
              '[回答](followup/'+key+'/answer.md) · [完整数值和调用](followup/'+key+'/audit-summary.json)','',r['completion'],'']+['- '+i for i in r['issues']]+['',r['evidence'],'']
    for result in x['workpaper_results']:lines.append('- '+json.dumps(result,ensure_ascii=False))
(OUT/'cases.md').write_text('\n'.join(lines),encoding='utf8')
for name in ('replay_handoff.py','rerender.ts','replay-validation.json'):shutil.copy2(BASE/name,OUT/name)
dump('usage.json',usage);dump('validation.json',{'case_count':len(checks),'initial_case_count':len(summary),'followup_case_count':len(follow),'model':'CPA gpt-6-luna','router_effort':'low','main_effort':'high','checks':checks})
print(json.dumps(usage,ensure_ascii=False,indent=2))

"""Package completed observations. Does not run models or edit product files."""
import json,shutil
from pathlib import Path
from collections import Counter
BASE=Path(__file__).parent;ROOT=BASE.parents[1]
OUT=ROOT/'docs/evidence/n4-adoption-preflight-20261008';OUT.mkdir(parents=True,exist_ok=True)
summary=json.loads((BASE/'summary.json').read_text(encoding='utf-8'))
review=json.loads((BASE/'manual-review.json').read_text(encoding='utf-8'))
manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
for name in ['manifest.json','iteration.md','manual-review.json','summary.json','prepare.py','worker.ts','run_all.py','extract.py','read_source.py','write_evidence.py']:
    shutil.copyfile(BASE/name,OUT/name)
def write(name,body):(OUT/name).write_text(body,encoding='utf-8')
lines=['# 逐题采用证据（研发预检）','',
       '冻结代码 `7524cca`。每题两组各一次；这是行为预检，不是正式成绩。完整原始审计、原生 Pi 事件和最终请求体位于本工作树 `tmp/adoption/runs/<题号>-<组>/`。下列工具顺序按实际请求事件，不把started/completed重复算两次。','',
       '绑定率：最终答案中由 `{{...}}` 展开产生的财务数值出现次数 / 全部财务数值出现次数。重复值重复计数；整表按数值格计，空格不计；排除年份、季度编号、页码、来源ID、表行键、序号及URL；账龄阈值计入。非绑定包含手抄原文及手抄工具计算结果，不等于数值必错。数字清单保存在每题 `audit-summary.json`，已逐题人工核对。','',
       '“原始标签”来自模型回答模板；“最终标签”含宿主自动标注。不将自动标签算模型主动标注。请求数含路由；输入含缓存，推理token是输出的子集；费用字段仅保留目录估算，CPA实际账单未知。','']
totals={}
for x in summary:
    key=x['case']+'-'+x['profile'];d=BASE/'runs'/key;dest=OUT/key;dest.mkdir(exist_ok=True)
    for name in ['answer.md','template.md','audit-summary.json','start.json','model.json']:
        shutil.copyfile(d/name,dest/name)
    u=x['usage'];b=x['binding'];r=review.get(key,{})
    lines += [f'## {key}', '',x['question'].replace('\n','  \n'),'',
        f"状态：{x['status']}；请求 {u['calls']}（router {u['phases'].get('router',{}).get('calls',0)} / main {u['phases'].get('main',{}).get('calls',0)}）；输入 {u['input']:,}（未缓存 {u['uncachedInput']:,}，读缓存 {u['cacheRead']:,}）；输出 {u['output']:,}（推理 {u['reasoning']:,}）；未知用量请求 {u['unknownCalls']}。",
        '',f"绑定：{b['bound']}/{b['total']} = {b['ratio']:.1%}；手写/非绑定 {b['unbound']} 次。原始标签 {json.dumps(x['all_labels_raw'],ensure_ascii=False)}；最终标签 {json.dumps(x['all_labels_final'],ensure_ascii=False)}。",'',
        f"[最终回答]({key}/answer.md) · [原始模板]({key}/template.md) · [逐项数值/调用/用量]({key}/audit-summary.json) · [原始审计](../../../tmp/adoption/runs/{key}/app-data/audit/{x['run_id']}.jsonl)", '',
        '**实际工具与 kind 序列**','',
        ' → '.join(c['name']+(f"[{c['args'].get('kind','statement_analysis')}]" if c['name']=='financial_workpaper' else '') for c in x['calls']), '',
        '**参数与错误**','']
    for c in x['calls']:
        if c['name']=='financial_workpaper':lines.append(f"- 审计第 {c['line']} 行：`{c['args'].get('kind')}`；periods=`{json.dumps(c['args'].get('periods'),ensure_ascii=False)}`。")
    for e in x['errors']:lines.append(f"- 审计第 {e.get('line','?')} 行：{e.get('type')}，{json.dumps(e.get('data') or {k:v for k,v in e.items() if k not in ('line','type')},ensure_ascii=False)}")
    if not x['errors']:lines.append('- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。')
    lines += ['', '**金融核对与遗漏**','',r.get('result','待核对'), '']
    lines += ['- '+s for s in r.get('issues',[])]
    lines += ['',r.get('source_check',''),'']
    t=totals.setdefault(x['profile'],{k:0 for k in ['sessions','calls','router_calls','main_calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls','bound','unbound','model_native_retry_events','model_native_compaction_events']})
    t['sessions']+=1
    for k in ['calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls']:t[k]+=u[k]
    t['router_calls']+=u['phases'].get('router',{}).get('calls',0);t['main_calls']+=u['phases'].get('main',{}).get('calls',0)
    t['bound']+=b['bound'];t['unbound']+=b['unbound']
    native=[json.loads(line) for line in (d/'native-events.jsonl').read_text(encoding='utf-8').splitlines()]
    t['model_native_retry_events']+=sum(e['type']=='auto_retry_start' for e in native)
    t['model_native_compaction_events']+=sum(e['type']=='auto_compaction_start' for e in native)
    effort=Counter((q.get('phase'),q.get('model'),q.get('sentReasoningEffort')) for q in x['requests'])
    assert all((phase=='router' and effort=='low' or phase=='main' and effort=='high') and model=='gpt-6-luna' for phase,model,effort in effort),effort
write('cases.md','\n'.join(lines))
write('usage.json',json.dumps({'expense_category':'研发预检','actual_CPA_cost':None,'actual_CPA_cost_reason':'没有CPA实际账单价格；审计中的Pi目录估算不能当账单','totals':totals},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(totals,ensure_ascii=False,indent=2))

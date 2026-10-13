"""Summarize both sealed held-out reviews, retaining version and usage boundaries."""
import hashlib
import json
import statistics
from pathlib import Path
from metrics import DIMS, aggregate_scores

ROOT=Path(__file__).resolve().parents[2]
STUDY=ROOT/'data/evaluation/blind-eval-F12-heldout-20261008'
ANON=ROOT/'data/evaluation/blind-eval-F12-H-review-20261008'
read=lambda p:json.loads(p.read_text('utf-8-sig'))


def dump(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')


seal=read(ANON/'score-seal.json')
for record in seal['reviews']:
    assert hashlib.sha256((ANON/record['path']).read_bytes()).hexdigest()==record['sha256']
state=read(STUDY/'experiment.json');usage=read(STUDY/'usage.json')
runs={r['label']:r for r in state['runs']};costs={r['label']:r for r in usage['rows']}
identities={r['case_id']:r for r in read(ANON/'private-map.json')['cases']}
stability=read(ANON/'stability-original.json')
passes=[]
for rd in ['round1','round2']:
    mapping=read(ANON/f'private-{rd}-map.json');review=read(ANON/rd/'review.json');rows=[]
    for r in review['reviews']:
        ident=identities[mapping[r['case_id']]];run=runs[ident['label']]
        rows.append({**r,'label':run['label'],'split':'heldout','task_id':run['taskId'],
                     'task_type':run['taskType'],'profile':run['profile'],'repeat':run['repeat'],
                     'status':run['status'],'verified_cost':None,
                     'unknown_usage_calls':costs[run['label']]['usage']['unknownCalls']})
    groups=[]
    for profile in ['prepared','financial']:
        g=[r for r in rows if r['profile']==profile]
        groups.append({'profile':profile,'n':len(g),'material_defective_cases':sum(bool(r['material_defects']) for r in g),
                       'material_defect_entries':sum(len(r['material_defects']) for r in g),
                       'mean_scores':{d:statistics.mean(v) if v else None for d in DIMS for v in [[r['scores'][d] for r in g if r['scores'][d] is not None]]},
                       'unreviewed':[{'label':r['label'],'items':r['unreviewed']} for r in g if r['unreviewed']]})
    p,f=groups;depth={d:{'prepared':p['mean_scores'][d],'financial':f['mean_scores'][d]} for d in ['explanation','adjustments','anomalies'] if p['mean_scores'][d] is not None and f['mean_scores'][d] is not None}
    quality={'material_entries_not_more':f['material_defect_entries']<=p['material_defect_entries'],
             'depth_pairs':depth,'depth_condition':bool(depth) and all(v['financial']>=v['prepared'] for v in depth.values()) and any(v['financial']>v['prepared'] for v in depth.values()),
             'verified_cost_condition':None,'not_an_advantage_claim':True}
    e4=aggregate_scores(rows)
    if not stability['stable_by_preregistered_threshold']:
        e4['may_claim_advantage']=False;e4['blockers'].append('Independent reviews unstable by frozen threshold')
    decoded={'rows':rows,'summary':groups,'descriptive_quality_components':quality,'e4':e4}
    dump(STUDY/f'{rd}-decoded.json',decoded)
    passes.append({'round':rd,'summary':groups,'descriptive_quality_components':quality,'e4':e4})
result={'purpose':'formal heldout H1/H2 results on F1.2','score_seal':seal,
        'stability':{k:v for k,v in stability.items() if k!='cases'},'passes':passes,
        'metrics_purpose_note':'Unchanged frozen metrics.py uses legacy workflow_rehearsal_not_score label. Only that label is inapplicable; this is formal evaluation and original calculations remain unchanged.',
        'overall_advantage_claim':False,'version_boundary':'Development F1; aborted first heldout batch F1.1 preserved separately; formal rerun F1.2; later stage B requires separate F1.3 handoff.',
        'cost_boundary':'F1.2 participant costs and F1.1 aborted costs individually reported; full attempt costs additionally totaled. Actual bills unknown and 3 requests unknown across both batches; no cost advantage claim.',
        'delivered_code_static_check':{'files':16,'syntax_valid':15,'syntax_invalid':1,'runtime_validity':'Not established by static parsing. Generator replay is a separate check.'},
        'limitations':['Partial preparation shared; original report available, full ingestion not claimed.','No extrapolation from eight turns; no statistical significance claimed.','Declared tool lists and explicit anonymization do not guarantee against stylistic identity inference.','No merging favorable review scores or replacing original failures.']}
dump(STUDY/'heldout-results.json',result)
lines=['# H1/H2 正式盲评汇总（F1.2；N1私有）','','8/8参评回合完成。F1.1批次因宿主入库入口中止，F1.2重跑；旧2次中止及全部用量另账保留。运行版本、资料冻结、analysis_only审计、取消修复、全部费用和交付复算见 `EXECUTION_REPORT.md`。阶段A为F1，分别报告。','','两遍均为全新gpt-6-astra/high、fork_turns=none，只收到各自匿名答卷、rubric、冻结参考和原报告；第二遍换序。两份review.json先封存哈希，再解盲；原始评分不重写。', '',
       f"换序稳定性：**{'达到' if stability['stable_by_preregistered_threshold'] else '未达到'}预设标准**。实质缺陷有无一致{stability['material_presence_agreement']}/8；平均绝对分差{stability['mean_absolute_score_difference']:.4f}，最大单项差{stability['max_dimension_difference']}。按题适用性排除null。缺陷覆盖及严重性还须结合 `defect-comparison.md`，不能只看总分。",'',
       '| 评审批次 | 组别 | 实质缺陷回合 | 缺陷条目 | R1读取 | R2取数 | R3解释 | R4调整 | R5异常 | C共同 |',
       '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for rd in passes:
    for g in rd['summary']:
        values=['—' if g['mean_scores'][d] is None else f"{g['mean_scores'][d]:.2f}" for d in DIMS]
        lines.append('| '+rd['round']+' | '+g['profile']+f" | {g['material_defective_cases']}/4 | {g['material_defect_entries']} | "+' | '.join(values)+' |')
lines+=['','每题、组别、重复的原始分数、缺陷证据、未审范围见round1-decoded.json、round2-decoded.json；不挑有利一遍或事后平均以消除分歧。条目数是评审记录数，底层缺陷对应另列。', '',
        '**不能宣称总体优于基线。** 本批两遍均为通用组0/4、金融组1/4回合有实质缺陷，金融组未满足“缺陷不更多”，也未满足“深度更高”条件。开发集两遍亦未达深度高于基线条件。E4要求开发集与held-out各自同时满足缺陷、深度和已验证成本门槛；本批没有已核实实际账单且有未知请求，目录估价不能代替成本资格。完整分项与阻断记录在heldout-results.json。','',
        '唯一实质缺陷为F1_H2仍交付的Markdown报告：方向词与带符号差额组合不一致。两遍均判direction，R2最高1分；其他正确版本不能抵消该交付缺陷。解盲后追踪确认错误位置未经A1数值绑定，属于自定义脚本报告字符串的表达错误，非计算方向错误。主体结果不因此事后改分。','',
        '四个H1答卷的解释维度均为2分：数字桥接尚未充分落到原文支持的经营原因；非经常性差额和税后/归属口径解释也不足。详见两遍原始缺陷与defect-comparison.md；不能用数值格回放代替解释能力验收。','',
        '356个绑定数值格、9个成功生成脚本/68个产物的复算一致，只是各自检查范围的证据，不覆盖全部文字、图表、单位和金融语义。另对16份交付Python文件作离线语法解析：15份通过，P1_H1的recalculate.py含1处语法错误；没有据此宣称其他文件运行成功。生成脚本可复现一个有缺陷的文件，因此产物字节一致不等于该复算文件可运行。原文件与评审分数保留。见delivered-code-static-check.json。','',
        '独立评审的原生线程ID与用量工具未提供，仍未知，不混入参评分析。225页源材料、匿名包、原始映射和审计均保持N1范围，不用于主线/N2/N3调试。经授权的统计诊断另存blind-eval-heldout-diagnostics-redacted-20261008，只含类别、计数与机制。阶段B/X7等资料与版本通知，青啤剩余附注未擅自续跑。']
(STUDY/'HELDOUT_REPORT.md').write_text('\n'.join(lines)+'\n','utf8')
print(json.dumps({'report':str(STUDY/'HELDOUT_REPORT.md'),'stability':result['stability'],'passes':[{'round':p['round'],'summary':p['summary'],'quality':p['descriptive_quality_components']} for p in passes]},ensure_ascii=False))

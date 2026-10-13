"""Decode two already-sealed F1.4 extension reviews without pooling versions."""
import argparse
import hashlib
import statistics
from collections import Counter
from pathlib import Path
from blind import read, dump, output
from metrics import DIMS, aggregate_scores

p=argparse.ArgumentParser()
p.add_argument('study');p.add_argument('anonymous');p.add_argument('--title',required=True)
a=p.parse_args();study=output(a.study);anonymous=output(a.anonymous)
seal=read(anonymous/'score-seal.json')
for record in seal['reviews']:
    assert hashlib.sha256((anonymous/record['path']).read_bytes()).hexdigest()==record['sha256']
state=read(study/'experiment.json');usage=read(study/'usage.json')
assert state['freeze']['version']=='F1.4'
runs={r['label']:r for r in state['runs']}
assert len(runs)==len(state['plannedOrder'])
assert all(r['status'] in ['completed','failed','cancelled','blocked_dependency'] for r in runs.values())
costs={r['label']:r for r in usage['rows']}
identities={r['case_id']:r for r in read(anonymous/'private-map.json')['cases']}
stability=read(anonymous/'stability-original.json')
passes=[]
for rd in ['round1','round2']:
    mapping=read(anonymous/f'private-{rd}-map.json')
    review=read(anonymous/rd/'review.json');rows=[]
    for record in review['reviews']:
        identity=identities[mapping[record['case_id']]];run=runs[identity['label']]
        rows.append({**record,'label':run['label'],'split':'extension','task_id':run['taskId'],
                     'task_type':run['taskType'],'profile':run['profile'],'repeat':run['repeat'],
                     'status':run['status'],'verified_cost':None,
                     'unknown_usage_calls':costs[run['label']]['usage']['unknownCalls']})
    summaries=[]
    for profile in ['prepared','financial']:
        group=[r for r in rows if r['profile']==profile]
        summaries.append({'profile':profile,'n':len(group),
                          'material_defective_cases':sum(bool(r['material_defects']) for r in group),
                          'material_defect_entries':sum(len(r['material_defects']) for r in group),
                          'mean_scores':{d:statistics.mean(v) if v else None for d in DIMS
                                         for v in [[r['scores'][d] for r in group if r['scores'][d] is not None]]},
                          'unreviewed':[{'label':r['label'],'items':r['unreviewed']} for r in group if r['unreviewed']]})
    baseline,financial=summaries
    depth={d:{'prepared':baseline['mean_scores'][d],'financial':financial['mean_scores'][d]}
           for d in ['explanation','adjustments','anomalies']
           if baseline['mean_scores'][d] is not None and financial['mean_scores'][d] is not None}
    quality={'material_entries_not_more':financial['material_defect_entries']<=baseline['material_defect_entries'],
             'depth_pairs':depth,'depth_condition':bool(depth) and all(v['financial']>=v['prepared'] for v in depth.values())
                and any(v['financial']>v['prepared'] for v in depth.values()),
             'verified_cost_condition':None,'not_an_advantage_claim':True}
    e4=aggregate_scores(rows)
    if not stability['stable_by_preregistered_threshold']:
        e4['may_claim_advantage']=False
        e4['blockers'].append('Independent review order stability threshold not met')
    decoded={'rows':rows,'summary':summaries,'descriptive_quality_components':quality,'e4':e4}
    dump(study/f'{rd}-decoded.json',decoded)
    passes.append({'round':rd,**{k:v for k,v in decoded.items() if k!='rows'}})

cost_groups=[]
failure_categories={
    'F1_X3':('product_answer_binding','A1 一次修复后仍含无效占位符，受控 answer_reference_error'),
    'F2_X1':('infrastructure_upstream_transport','上游流在 response.completed 前断开；含 1 次未知用量，未补跑'),
    'F2_X7':('product_answer_contract','A1 一次修复后仍被假设/风险/适用范围校验拒绝，answer_contract_error；未补跑'),
    'P2_X7':('product_answer_contract','A1 一次修复后仍被假设/风险/适用范围校验拒绝，answer_contract_error；未补跑'),
}
failures=[{'label':r['label'],'profile':r['profile'],'status':r['status'],
           'category':failure_categories.get(r['label'],('unclassified','保留原始错误，待分类'))[0],
           'explanation':failure_categories.get(r['label'],('unclassified','保留原始错误，待分类'))[1],
           'raw_error':r.get('error'),'retried':False}
          for r in runs.values() if r['status']!='completed']
for profile in ['prepared','financial']:
    group=[r for r in usage['rows'] if r['profile']==profile]
    totals={}
    for key in ['calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls']:
        values=[r['usage'].get(key) for r in group if r['usage'] is not None]
        known=[x for x in values if x is not None]
        totals[key]={'known_sum':sum(known) if known else None,'missing_attempts':len(group)-len(known)}
    elapsed=[r['elapsed_seconds'] for r in group if r['elapsed_seconds'] is not None]
    cost_groups.append({'profile':profile,'attempts':len(group),
                        'completed':sum(r['status']=='completed' for r in group),
                        'tokens_and_requests':totals,'elapsed_median_seconds':statistics.median(elapsed) if elapsed else None,
                        'elapsed_range_seconds':[min(elapsed),max(elapsed)] if elapsed else None,
                        'provider_billed_cost':None})
result={'title':a.title,'version':'F1.4','commit':state['freeze']['head'],
        'score_seal':seal,'stability':{k:v for k,v in stability.items() if k!='cases'},
        'passes':passes,'usage_by_group':cost_groups,
        'statuses':dict(Counter(r['status'] for r in runs.values())),
        'failure_classification':failures,
        'failure_counts':dict(Counter(r['category'] for r in failures)),
        'tasks':sorted({r['taskId'] for r in runs.values()}),
        'known_material_limitations':state['config'].get('knownMaterialLimitations',[]),
        'overall_advantage_claim':False,
        'version_boundary':'A ran on F1; H rerun on F1.2; this extension batch F1.4. No pooling or causal attribution across tasks/versions.',
        'cost_boundary':'Preparation, aborted batches and independent judging separate. Actual CPA bill unknown; catalog estimates are not verified spend.',
        'metrics_note':'Legacy purpose label in frozen metrics.py is retained in raw output; this batch is formal extension evaluation.'}
if result['tasks']==['X7']:
    result['initial_handoff_material_limitations']=result['known_material_limitations']
    gate=read(study/'material-gate-and-freeze.json')['known_limitations']
    result['known_material_limitations']=[
        't9 披露扣非的 financial_item 维度仍阻止底稿采用；2024 计算扣非单列，2023 计算扣非为空，不冒充披露值。',
        f"原交接称 8 行冲突；冻结前完整复核为 {gate['period_conflicts_by_table']['quarters']} 行单季、{gate['period_conflicts_by_table']['cumulatives']} 行累计直接冲突，另 {gate['additional_unknown_input_nulls']} 行因输入未知为空。这些行与 N3 先前归档完全相同，未发生新漂移。",
        '门槛 7 表已提交，整份年报仅 147/344 表、1,880 条事实；两组共享相同部分入库状态和全量原文。',
    ]
    result['material_gate_receipt']='material-gate-and-freeze.json'
dump(study/'extension-results.json',result)
lines=[f'# {a.title}（F1.4）','',
       f"{len(runs)} 个参评回合，状态：{result['statuses']}。模型 gpt-6-luna / CPA；全部请求要求 analysis_only:true、独立隔离键。运行冻结与资料状态见本目录执行记录。",'',
       '两遍独立评审均使用全新 gpt-6-astra/high 线程，仅提供各自匿名包、rubric、冻结参考和原报告。第二遍反转顺序；两份原始评分先封存，再解盲，不回写评分消除分歧。','',
       f"换序稳定性：{'达到' if stability['stable_by_preregistered_threshold'] else '未达到'}预设标准；实质缺陷有无一致 {stability['material_presence_agreement']}/{len(runs)}，平均绝对分差 {stability['mean_absolute_score_difference']:.4f}，最大单项差 {stability['max_dimension_difference']}。缺陷逐条对应另见 defect-comparison.md。",'',
       '| 评审 | 组别 | 实质缺陷回合 | 条目 | R1 | R2 | R3 | R4 | R5 | C |',
       '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for rd in passes:
    for g in rd['summary']:
        values=['—' if g['mean_scores'][d] is None else f"{g['mean_scores'][d]:.2f}" for d in DIMS]
        lines.append('| '+rd['round']+' | '+g['profile']+f" | {g['material_defective_cases']}/{g['n']} | {g['material_defect_entries']} | "+' | '.join(values)+' |')
lines+=['','这是扩展集的独立报告，不能据此单独宣称总体优于基线。E4要求开发集和 held-out 各自满足缺陷、深度和已验证成本条件；本批不补齐或替换 A/H 的结果。F1.4改变了金融组底稿内容，题目也不同，跨阶段成绩差不能视为版本净改进。','',
        '| 组别 | 完成/尝试 | 请求数 | 已知输入 | 已知输出 | 未知用量请求 |',
        '|---|---:|---:|---:|---:|---:|']
for g in cost_groups:
    u=g['tokens_and_requests']
    values=[str(u[k]['known_sum']) for k in ['calls','input','output','unknownCalls']]
    lines.append('| '+g['profile']+f" | {g['completed']}/{g['attempts']} | "+' | '.join(values)+' |')
lines+=['','各类 token、逐回合时间和错误见 usage.json、extension-results.json。已知合计遇到未知请求时只是下界；缓存输入包含在总输入中。实际账单未知，不把目录估价当核实成本。入库准备与盲评线程支出另列，后者未取得的用量保持未知。','',
        '程序数值选择器、A5、下载与沙箱回放各有明确范围。数值格相符不能代替文字方向、因果、口径或图表的独立评审；生成脚本回放成功也不证明交付的独立复算文件可执行。详见 各回合 *-numeric-checks.json、A5、delivery-inventory、replay-results、delivered-code-static-check 记录。','',
        '未评范围、身份风格推断可能性、原始失败与全部仍交付版本保留。X2 本轮未执行：美的材料未入库。']
if failures:
    lines+=['','失败按原因单列，完成率保留全部尝试；不从分母删除基础设施失败，也不把它等同金融推理或产品绑定缺陷。','',
            '| 回合 | 分类 | 说明 |','|---|---|---|']
    lines += [f"| {r['label']} | {r['category']} | {r['explanation']} |" for r in failures]
if result['known_material_limitations']:
    lines+=['','已知资料限制（两组共享）：','']+['- '+s for s in result['known_material_limitations']]
if 'X1' in result['tasks']:
    lines+=['','本批金融组有 2/10 未完成，已知输入较低不能单独解释为等质省费；实际账单未知，失败和未知请求保留。',
            '', '首批双遍评审因只提供 MuPDF 页图、部分嵌入字体渲染缺字，在未读取或解盲时封存撤回。正式评分来自补齐两种原始渲染视图后重新开的两条独立线程，全部 20 案重评；未从原批次挑选分数。撤回评审成本保持未知并单列。']
(study/'EXTENSION_REPORT.md').write_text('\n'.join(lines)+'\n','utf8')
print(str(study/'EXTENSION_REPORT.md'))

"""Report the two sealed formal Stage A reviews without selecting a preferred pass."""
import hashlib
import json
import statistics
from pathlib import Path
from metrics import DIMS, aggregate_scores

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'data/evaluation/blind-eval-F1-20261008'
ANON = ROOT / 'data/evaluation/blind-eval-F1-A-review-corrected-20261008'


def read(p):
    return json.loads(p.read_text('utf-8-sig'))


def dump(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')


seal = read(ANON / 'score-seal.json')
for r in seal['reviews']:
    assert hashlib.sha256((ANON / r['path']).read_bytes()).hexdigest() == r['sha256']
state = read(STUDY / 'experiment.json')
usage = read(STUDY / 'stage-A-usage.json')
by_run = {r['label']: r for r in state['runs']}
by_usage = {r['label']: r for r in usage['rows']}
identities = {r['case_id']: r for r in read(ANON / 'private-map.json')['cases']}
stability = read(ANON / 'stability-original.json')
passes = []
for name in ['round1', 'round2']:
    review = read(ANON / name / 'review.json')
    mapping = read(ANON / f'private-{name}-map.json')
    rows = []
    for r in review['reviews']:
        ident = identities[mapping[r['case_id']]]
        run = by_run[ident['label']]
        u = by_usage[run['label']]
        rows.append({**r, 'label': run['label'], 'split': 'development',
                     'task_id': run['taskId'], 'task_type': run['taskType'],
                     'repeat': run['repeat'], 'profile': run['profile'],
                     'status': run['status'], 'verified_cost': None,
                     'unknown_usage_calls': u['usage']['unknownCalls']})
    summary = []
    for profile in ['prepared', 'financial']:
        group = [r for r in rows if r['profile'] == profile]
        summary.append({
            'profile': profile, 'n': len(group),
            'material_defective_cases': sum(bool(r['material_defects']) for r in group),
            'judge_material_defect_entries': sum(len(r['material_defects']) for r in group),
            'mean_scores': {d: statistics.mean(values) if values else None for d in DIMS
                            for values in [[r['scores'][d] for r in group if r['scores'][d] is not None]]},
            'unreviewed': [{'label': r['label'], 'items': r['unreviewed']} for r in group if r['unreviewed']],
        })
    aggregate = aggregate_scores(rows)
    if not stability['stable_by_preregistered_threshold']:
        aggregate['may_claim_advantage'] = False
        aggregate['blockers'].append('Independent reviews unstable under preregistered threshold')
    if any(r['unreviewed'] for r in rows):
        aggregate['may_claim_advantage'] = False
        aggregate['blockers'].append('Review scope limits recorded; assess materiality, do not claim all deliverables fully reviewed')
    dump(STUDY / f'stage-A-{name}-decoded.json', {'rows': rows, 'summary': summary, 'e4': aggregate})
    prepared, financial = summary
    depth_pairs = {d: {'prepared': prepared['mean_scores'][d], 'financial': financial['mean_scores'][d]}
                   for d in ['explanation', 'adjustments', 'anomalies']
                   if prepared['mean_scores'][d] is not None and financial['mean_scores'][d] is not None}
    measured_quality = {
        'purpose': 'Descriptive quality components only; no cost or completion eligibility implied',
        'material_defect_entries_not_more': financial['judge_material_defect_entries'] <= prepared['judge_material_defect_entries'],
        'defective_case_counts': {g['profile']: g['material_defective_cases'] for g in summary},
        'depth_pairs': depth_pairs,
        'depth_condition': bool(depth_pairs) and all(x['financial'] >= x['prepared'] for x in depth_pairs.values()) and any(x['financial'] > x['prepared'] for x in depth_pairs.values()),
        'verified_cost_condition': None,
    }
    passes.append({'round': name, 'summary': summary, 'e4': aggregate, 'measured_quality_components': measured_quality})

result = {
    'purpose': 'formal_Stage_A_development_results_F1',
    'review_validity': 'corrected anonymous package; both fresh reviews sealed before decoding',
    'anonymization_correction': {
        'initial_reviews': 'withdrawn; retained as diagnostic evidence only',
        'evidence': 'anonymization-correction-evidence.json',
        'reason': 'Original path redaction damaged CSV structure by treating s:/ in https:// as a Windows drive.',
        'repair': 'Separate anonymizer version preserves public URLs and parses/redacts CSV by cell; no participant rerun, gold/rubric/raw answers unchanged.',
        'review_thread_receipt': 'stage-A-corrected-review-thread-receipt.json',
    },
    'frozen_stability_output_purpose_note': 'The unchanged metrics.py output uses the legacy label workflow_rehearsal_not_score. This run is formal Stage A; only that historical label is inapplicable. Original calculation and output are preserved.',
    'score_seal': seal, 'stability': {k: v for k, v in stability.items() if k != 'cases'},
    'passes': passes, 'overall_advantage_claim': False,
    'version_boundary': 'Stage A F1 with fully ingested documents. First H1/H2 batch F1.1 aborted at host ingestion entry, then F1.2 rerun in new sessions with analysis_only:true. All aborted usage separate. Stage B awaits F1.3 ingestion-only scope repair, N3 review and data freeze. No replacement of F2_D1.',
    'limits': ['Development-only; heldout cannot be inferred from it.',
               'Provider bills unknown; one participant request usage unknown.',
               'F2_D1 failed and is retained with available answer/attachments.',
               'Defect entry counts are reviewer entries, not an independently deduplicated frequency. See defect-level comparison separately.',
               'Neither the more favorable pass nor a post hoc average replaces the two original judgments.'],
}
dump(STUDY / 'stage-A-results.json', result)

cost = read(STUDY / 'stage-A-cost-summary.json')
lines = [
    '# 阶段 A 正式执行与双遍盲评（F1）', '',
    '阶段 A 已执行卡罗特 D1/D2/D3，每组每题两次，12 回合、8 条链；通用组 6/6 完成，金融组 5/6 完成。F2_D1 回答绑定发生 decimal.ConversionSyntax，按事先规则和最新决定计失败、不补跑、不替换。', '',
    '代码冻结为 F1 `0c51eeb` / tree `b7e29d5`，3001 当时 PID 80212。阶段 A 最后回合于 2026-10-08 15:32:52 +08:00 完成；15:34:47 期末核对代码、配置、参考、资料均无差异。该项目文档当时已完整入库，不受后来发现的部分入库入口问题影响。F1.1 批次因宿主入库入口中止，F1.2 重跑：H1/H2 新会话统一 analysis_only=true，青啤资料不重新应用。阶段 B 等 F1.3 入库口径修复、N3复核和数据冻结；X7也统一带开关。不同版本分开报告；差异见 `../f1.1-freeze-20261008/F1-to-F1.1.diff`、`../f1.2-freeze-20261008/F1.1-to-F1.2.diff`。', '',
    '卡罗特资料摘要 `960d0f48cbf71ee5349c5dff349f59e4bcb5b6015b83af17e9beffa16b2c4540` 的准确值以 `verification-phase1.json` 为准。两组共享来源状态，各链隔离成果，D2→D3 同会话同键。', '',
    '## 独立评审', '',
    '两遍均为全新 gpt-6-astra/high，fork_turns=none；第二遍逆序并重新编号。评审只收到匿名题目、回答、附件、rubric 和冻结参考，提供两份原报告全部 102 页。177 个附件全部下载成功，14 张图逐张做身份检查且保留原像素；显式身份标记扫描为 0。共享文件系统的访问约束不是 OS 权限隔离，方法或风格仍可能被推测。', '',
    '两遍原始 review.json 先封存 SHA256，再解码。线程工具不返回原生 UUID/用量，记录为未知；评审费用不并入参评分析。', '',
    '匿名化完整性修正：首次评审完成后发现旧路径正则把 https:// 中的 s:/ 当作盘符，损坏 F2_D1 的 signals.csv。首次两遍评分全部撤回，原文件与封存记录保留为诊断证据。新版匿名器保护公开 URL，并逐格处理 CSV；85 份 CSV 的结构和 3,812 个数值格、14 张原图均已核对。随后重新开启两个全新评审线程，未提供首次评分；下表仅展示修正包的两遍结果。参评回答、参考、rubric 没有修改，也没有付费补跑。', '',
    f"换序稳定性：**{'达到' if stability['stable_by_preregistered_threshold'] else '未达到'}预设标准**；实质缺陷有无一致 {stability['material_presence_agreement']}/12，平均绝对分差 {stability['mean_absolute_score_difference']:.4f}，最大单项分差 {stability['max_dimension_difference']}。null 适用性按冻结金标核对。逐项缺陷覆盖/严重性另见缺陷对照记录，不能仅看均分。", '',
    '| 评审批次 | 组别 | 有实质缺陷回合 | R1 阅读 | R2 实质取数 | R3 解释 | R4 调整 | R5 异常 | C 共同 |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|',
]
# Exact canonical fingerprint, not a manually transcribed number.
lines[6] = '卡罗特资料摘要 `' + read(STUDY / 'verification-phase1.json')['expected']['material'] + '`；两组共享来源状态，各链隔离成果，D2→D3 同会话同键。'
for item in passes:
    for group in item['summary']:
        values = ['—' if group['mean_scores'][d] is None else f"{group['mean_scores'][d]:.2f}" for d in DIMS]
        lines.append('| ' + item['round'] + ' | ' + group['profile'] + ' | ' + str(group['material_defective_cases']) + '/6 | ' + ' | '.join(values) + ' |')
lines += ['', '各遍原始分数、理由、未审项目和缺陷定位见 `stage-A-round1-decoded.json`、`stage-A-round2-decoded.json`；不选择更有利的一遍。逐项覆盖/严重性见 `stage-A-defect-comparison.md` 与 JSON：两遍均对应通用组4条、金融组2条底层实质缺陷。主要问题是单位矛盾、情景值冒充原报值、图表年份反转、现金收息方向及原报估值列身份误读。', '',
          '两遍的深度条件均未达到：第一遍R3为通用3.00、金融2.83，第二遍均3.00；R5两遍两组均2.00，R4未考查。不能用较少实质缺陷抵消深度门槛。R3 中估值解释为辅助证据，不能替代经营归因；开发集不直接验证季报与会计重述能力。', '',
          'F2_D1运行失败，但仍对其已经交付的回答和附件评分；完成率与内容评分分别记录。评审未执行答卷代码、未查包外运行记录是预定边界，宿主复算另有证据；通用辅助模块未逐行审计、非核心外链未联网验证的具体范围完整保留，不当作另一次实质错误计数。', '',
          '## 参评分析用量（准备与评审另账）', '',
          '| 组别 | 请求数 | 已知输入 | 已知输出 | 未缓存输入 | 缓存读 | reasoning子集 | 用量未知请求 | 目录估计 USD | CPA实付 |',
          '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
for group in cost['groups']:
    lines.append('| ' + group['profile'] + ' | ' + ' | '.join(f"{group[k]:,}" for k in ['calls', 'input', 'output', 'uncachedInput', 'cacheRead', 'reasoning', 'unknownCalls']) + f" | {group['costUsd']:.8f} | 未知 |")
lines += ['', '有未知请求的已知总量是下界；reasoning 是输出子集，不能重复相加。目录估价不是账单，不用于 E4 成本优势判定。按题/组两次用量的中位数与范围、每次耗时在 `stage-A-usage.json`。并发期间有 N3 入库、早段 N1 青啤准备及离线复算，共享 CPU/CPA 负载；耗时不能解读为隔离性能基准。', '',
          '## 核验与 E4', '',
          '15 个有交付产物的成功脚本均在受控沙箱复算成功；162 个复算产物字节或 ZIP 内成员匹配，3 个 ZIP 封装字节不同已单列。453 个明确绑定的 CSV/JSON 金标格为精确值或显示舍入一致；这不等于全部数值、图表或金融语义通过。A5 只用现有 CLI，原始观察/误报/未命中保留，不能把 issue_count 当实质错误总数。', '',
          '**本阶段不能宣称“优于基线”。** 开发集与 held-out 必须各自满足 E4；目前阶段 A 仅开发集，且存在失败、未知请求及实际费用缺失。两遍各自的 E4 结果和阻断原因均保留在 `stage-A-results.json`。评审有分歧时先报告，不能更改 rubric、阈值或挑有利结论。', '',
          '青啤准备按材料门槛已暂停，59/310 表已提交；准备费用见 `../blind-eval-tsingtao-F1-20261008/REPORT.md`，未混入上表。已知伊利准备缺陷包括季度表口径 unspecified、分部资产负债余额期间 FY；最新决定另以 F1.3 在阶段 B 冻结前修正 t8 扣非等值的合并口径。是否已应用及其他缺陷的剩余状态，以 N3 复核和未来资料摘要为准；不修改本阶段记录。阶段 B、X7 等协调方通知。', '',
          'H1/H2 首批在 F1.1 上因分析中触发入库而停止；两次已提交尝试及全部用量另存 `../blind-eval-F11-heldout-20261008/STOP_REPORT.md`，不计为已完成 held-out，也不并入阶段 A。F1.2 新批次在 `../blind-eval-F12-heldout-20261008/`，旧失败不被替换；修正取消竞争已离线验证。', '',
          '主要证据：`stage-A-raw-seal.json`、`stage-A-corrected-review-thread-receipt.json`、`../blind-eval-F1-A-review-corrected-20261008/score-seal.json`、`anonymization-correction-evidence.json`、`stage-A-delivery-replay-summary.json`、`stage-A-numeric-summary.json`；崩溃交接：`../blind-eval-F1-F2_D1-crash-handoff-20261008/README.md`。']
(STUDY / 'STAGE_A_REPORT.md').write_text('\n'.join(lines) + '\n', 'utf8')
print(json.dumps({'stage_A_report': str(STUDY / 'STAGE_A_REPORT.md'), 'stability': result['stability'], 'passes': [{'round': p['round'], 'summary': p['summary']} for p in passes]}, ensure_ascii=False))

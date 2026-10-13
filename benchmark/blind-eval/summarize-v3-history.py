"""Read only sealed F1-series results; emit descriptive v3 planning tables."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/evaluation/blind-eval-v3-design-20261008'
STAGES = [
    ('A', 'F1', 'blind-eval-F1-20261008', 'stage-A-', 'stage-A-cost-summary.json'),
    ('H', 'F1.2', 'blind-eval-F12-heldout-20261008', '', 'usage.json'),
    ('B', 'F1.4', 'blind-eval-F14-B-20261008', '', 'usage.json'),
    ('X7', 'F1.4', 'blind-eval-F14-X7-20261008', '', 'usage.json'),
]
DIMS = ['reading', 'substantive', 'explanation', 'adjustments', 'anomalies', 'common']


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    stages = []
    calibration = []
    for stage, version, folder, prefix, usage_file in STAGES:
        p = ROOT / 'data/evaluation' / folder
        passes = [read(p / f'{prefix}round{i}-decoded.json') for i in (1, 2)]
        usage = read(p / usage_file)
        groups = []
        for profile in ('prepared', 'financial'):
            pass_stats = []
            for review in passes:
                rows = [r for r in review['rows'] if r['profile'] == profile]
                pass_stats.append({
                    'n': len(rows),
                    'material_defective_cases': sum(bool(r['material_defects']) for r in rows),
                    'material_defect_entries': sum(len(r['material_defects']) for r in rows),
                    'mean_scores': {k: statistics.mean(v) if (v := [r['scores'][k] for r in rows if r['scores'].get(k) is not None]) else None for k in DIMS},
                    'score_denominators': {k: sum(r['scores'].get(k) is not None for r in rows) for k in DIMS},
                })
            if stage == 'A':
                u = next(g for g in usage['groups'] if g['profile'] == profile)
            else:
                rows = [r for r in usage['rows'] if r['profile'] == profile]
                u = {k: sum(r['usage'].get(k, 0) for r in rows) for k in ['input','output','uncachedInput','cacheRead','cacheWrite','reasoning','calls','unknownCalls','costUsd']}
                u.update(attempts=len(rows), completed=sum(r['status']=='completed' for r in rows), failed=sum(r['status']!='completed' for r in rows), elapsed_seconds_median=statistics.median(r['elapsed_seconds'] for r in rows), provider_billed_cost=None)
                calibration.extend({'stage':stage,'profile':profile,'status':r['status'],**{k:r['usage'].get(k) for k in ['input','output','calls','unknownCalls']}} for r in rows)
            groups.append({'profile':profile,'usage':u,'review_passes':pass_stats})
        a = {r['label']:r for r in passes[0]['rows']}
        b = {r['label']:r for r in passes[1]['rows']}
        deltas = [abs(a[n]['scores'][k]-b[n]['scores'][k]) for n in a for k in DIMS if a[n]['scores'].get(k) is not None and b[n]['scores'].get(k) is not None]
        presence = sum(bool(a[n]['material_defects'])==bool(b[n]['material_defects']) for n in a)
        stability = {'paired_dimensions':len(deltas),'mean_absolute_difference':statistics.mean(deltas),'maximum_difference':max(deltas),'defect_presence_agreement':presence,'cases':len(a),'passed':presence==len(a) and statistics.mean(deltas)<=.5 and max(deltas)<=1}
        stages.append({'stage':stage,'version':version,'source_folder':str(p.relative_to(ROOT)),'review_sources':[f'{prefix}round{i}-decoded.json' for i in (1,2)],'groups':groups,'stability':stability})
    payload={'scope':'prepared vs financial only; no original Pi arm; do not pool quality across versions','stages':stages,'calibration_excluding_A':calibration,'actual_bills':None,'judge_cost':None,'preparation_excluded':True}
    (OUT/'historical-metrics.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# F1 系列历史指标：技术报告引用表','','这里只汇总最终修正后、已封存解盲的评分；撤回的 initial-stage-A 及旧评审不计。P=prepared，F=financial。历史 A/H/B/X7 没有原版 Pi 组，不能据此声称整套 harness 优于原版。版本分别报告，禁止拼出一个质量总分。','','|阶段/版本|组|完成/尝试|实质缺陷回合 第1/第2遍|缺陷条目 第1/第2遍|请求|已知输入 token|已知输出 token|未知用量请求|','|---|---|---:|---|---|---:|---:|---:|---:|']
    for s in stages:
        for g in s['groups']:
            u=g['usage'];a,b=g['review_passes']
            lines.append(f"|{s['stage']} / {s['version']}|{g['profile']}|{u['completed']}/{u['attempts']}|{a['material_defective_cases']}/{a['n']} ; {b['material_defective_cases']}/{b['n']}|{a['material_defect_entries']} ; {b['material_defect_entries']}|{u['calls']}|{u['input']:,}|{u['output']:,}|{u['unknownCalls']}|")
    lines += ['','有未知用量时已知 token 仅为下界。失败仍在分母及用量中；完成率和答案实质正确率是两件事。一次回合可以有多条缺陷，不能把条目当成独立样本。','','|阶段|组/评审批次|R1 读取|R2 实质正确|R3 解释|R4 特殊损益/口径|R5 异常|C 共同要求|','|---|---|---:|---:|---:|---:|---:|---:|']
    for s in stages:
        for g in s['groups']:
            for i,r in enumerate(g['review_passes'],1):
                vals=['NA' if r['mean_scores'][k] is None else f"{r['mean_scores'][k]:.3f}" for k in DIMS]
                lines.append('|'+ '|'.join([s['stage'],f"{g['profile']} / {i}",*vals])+'|')
    lines += ['','各维度分母见 JSON；not_tested 不按 0 分。A 的 D2/D3、H 的 H2 解释分含建模/局部更新辅助证据，不能当作完整经营归因得分。X7 的 R5 仅辅助覆盖。','','|阶段|维度配对数|平均绝对差|最大差|缺陷有无一致|稳定|','|---|---:|---:|---:|---:|---|']
    for s in stages:
        v=s['stability'];lines.append(f"|{s['stage']}|{v['paired_dimensions']}|{v['mean_absolute_difference']:.6f}|{v['maximum_difference']}|{v['defect_presence_agreement']}/{v['cases']}|{'通过' if v['passed'] else '未通过'}|")
    lines += ['','|阶段|失败类别与解释|','|---|---|','|A|F2_D1 为产品 Decimal 绑定崩溃；不补跑。|','|H|F1.2 正式批无失败；F1.1 中止批独列：25 请求、已知输入 644,114、输出 7,011、未知 1，不计 F1.2 质量。|','|B|F1_X3 为产品绑定失败；F2_X1 为上游传输中断（基础设施），未知 1，不补跑。F2_X3 调度竞争记录保留，完成结果有效。|','|X7|P2_X7、F2_X7 均为产品回答契约失败。|','','A 的局部优势不能替代 held-out 验证。H 金融组已知输入较 prepared 高约 86%，且有实质缺陷；B 换序评审未达标，金融组已知输入降低也受失败和未知用量影响；X7 两组各完成一半。没有一组结果足以宣称整套系统显著优于原版 Pi。X7 金融组 R3 为 2.5，prepared 为 2.0/2.5，不支持“所有阶段金融 R3 都更低”的绝对表述；这也不证明整体能力优势。','','已知输入与输出、缓存、reasoning、用时和目录估算详见 JSON。reasoning 是输出子类，不重复加到总输出。目录估算不是 CPA 账单；未知评审用量不是零。47/52 为跨阶段运维完成总数（4 产品失败、1 基础设施失败），仅可汇报运行概况，不能据其合并质量/成本优势。']
    attempts=sum(g['usage']['attempts'] for s in stages for g in s['groups'])
    completed=sum(g['usage']['completed'] for s in stages for g in s['groups'])
    lines[-1]=lines[-1].replace('47/52',f'{completed}/{attempts}')
    (OUT/'HISTORICAL_METRICS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'stages':[{ 'stage':s['stage'],'stability':s['stability']} for s in stages],'known_input':sum(g['usage']['input'] for s in stages for g in s['groups']),'calls':sum(g['usage']['calls'] for s in stages for g in s['groups'])},ensure_ascii=False))


if __name__ == '__main__':
    main()

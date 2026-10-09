"""Offline report from sealed, decoded reviews. Held-out prose stays private."""
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'data/evaluation/blind-eval-F21-formal-private-20261009'
PUBLIC=ROOT/'data/evaluation/blind-eval-F21-formal-20261009'
spec=importlib.util.spec_from_file_location('formal_math',Path(__file__).with_name('formal-summary-math.py'))
math=importlib.util.module_from_spec(spec);spec.loader.exec_module(math)


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def write(p,value):
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fmt(value):
    return '未知/不适用' if value is None else f'{value:.4f}' if isinstance(value,float) else str(value)


def main():
    assert (BASE/'all-reviews-sealed-before-unblinding.json').exists()
    state=read(BASE/'experiment.json')
    runs={r['label']:r for r in state['runs']}
    reviews={rd:read(BASE/f'{rd}-decoded.json') for rd in ['round1','round2']}
    assessment=read(BASE/'critical-unreviewed-assessment.json')
    assessed={(x['round'],x['label']):x for x in assessment}
    assert len(assessed)==324 and all(type(x['critical_unreviewed']) is bool and x['reason'] for x in assessment)
    for rd,rows in reviews.items():
        for row in rows:
            row['critical_unreviewed']=assessed[(rd,row['label'])]['critical_unreviewed']
    costs=read(BASE/'usage-bounds-final.json')
    usage={r['label']:r for r in costs['rows']}
    assert set(usage)==set(runs) and len(usage)==162
    # Verify sealed originals remain intact; reporting never rewrites them.
    for receipt in read(BASE/'all-reviews-sealed-before-unblinding.json')['packets']:
        folder=BASE/'review-packets'/receipt['packet']
        assert hashlib.sha256((folder/'score-seal.json').read_bytes()).hexdigest()==receipt['seal_sha256']
        for item in read(folder/'score-seal.json')['reviews']:
            assert hashlib.sha256((folder/item['path']).read_bytes()).hexdigest()==item['sha256']
    splits={}
    differences=[]
    for split in ['development','heldout','extension']:
        passes={rd:[x for x in rows if x['split']==split] for rd,rows in reviews.items()}
        assert all(len(rows)==54 for rows in passes.values())
        reliability=math.reliability(*[{r['label']:r for r in rows} for rows in passes.values()])
        comparisons={}
        for comparator in ['original_pi','prepared']:
            results={rd:math.comparison(rows,usage,comparator) for rd,rows in passes.items()}
            comparisons[comparator]={'passes':results,'verdict':math.independent_verdict(
                results['round1']['result'],results['round2']['result'],reliability['reliability_floor_passed']),
                'repeat_statistics':{rd:math.paired_task_summary(rows,comparator) for rd,rows in passes.items()}}
        groups={rd:{p:math.group_summary([x for x in rows if x['profile']==p],usage)
                    for p in ['original_pi','prepared','financial']} for rd,rows in passes.items()}
        splits[split]={'reliability':reliability,'comparisons':comparisons,'groups':groups}
        keyed=[{r['label']:r for r in rows} for rows in passes.values()]
        for delta in reliability['disagreements']:
            differences.append({'split':split,**delta,'round1':keyed[0][delta['label']],
                                'round2':keyed[1][delta['label']]})
    failures=[{'label':r['label'],'split':r['split'],'profile':r['profile'],'status':r['status'],
               'failure_class':r.get('failureClass'),'retry':False} for r in runs.values() if r['status']!='completed']
    totals=[]
    for split in ['development','heldout','extension']:
        for profile in ['original_pi','prepared','financial']:
            rows=[r for r in usage.values() if r['split']==split and r['profile']==profile]
            total={'split':split,'profile':profile,'positions':len(rows),
                   'completed':sum(r['status']=='completed' for r in rows)}
            for key in ['request_count','input_lower','input_upper_observed_scenario','output_lower',
                        'output_upper_observed_scenario','catalog_cost_lower','catalog_cost_upper_observed_scenario','unknown_calls']:
                values=[r[key] for r in rows];total[key]=sum(values) if all(v is not None for v in values) else None
            for key in ['input','cacheRead','cacheWrite','output','reasoning']:
                requests=[q for r in rows for q in r['request_usage']]
                values=[(q.get('raw_usage') or {}).get(key) for q in requests]
                known=[v for v in values if isinstance(v,(int,float))]
                total['raw_'+key]={'known_sum':sum(known) if known else None,'unknown_request_count':len(values)-len(known)}
            totals.append(total)
    summary={'version':'F2.1','deployed_commit':state['deployedCommit'],'batch':state['batchId'],
        'protocol_commit':'207e105','cases':162,'review_threads':18,'review_model':'gpt-6-astra','reasoning_effort':'high',
        'statuses':dict(Counter(r['status'] for r in runs.values())),'splits':splits,'usage_totals':totals,
        'failures':failures,'incident_usage':costs['incident_usage'],'actual_billed_cost':None,
        'overall_E4_by_comparator':{p:all(splits[s]['comparisons'][p]['verdict']=='成立' for s in ['development','heldout'])
                                   for p in ['original_pi','prepared']},
        'bound_policy':costs['bound_policy'],'cost_upper_cache_assumption':costs['cost_upper_cache_assumption'],
        'elapsed_measurement':'Non-isolated: at most two different-arm chains; other-project ingestion could overlap.',
        'limits':['One new held-out company; repeats are not independent companies.',
                  'Both passes reported independently; no averaging, pass selection, adjudication or result-driven threshold change.',
                  'Known input per completed clean case is supplementary, not an E4 substitute.',
                  'Missing and unknown values retained; catalog cost is not the provider invoice.',
                  'Held-out review prose and every disagreement original remain in the private directory.']}
    write(BASE/'formal-results.json',summary)
    write(BASE/'all-score-disagreements-originals.json',differences)
    # All raw per-case mechanism descriptions remain available, even where equal
    # scores/material-presence hide differing explanations or defect taxonomies.
    write(BASE/'all-reviews-side-by-side.json',[{'label':label,'round1':next(r for r in reviews['round1'] if r['label']==label),
        'round2':next(r for r in reviews['round2'] if r['label']==label)} for label in runs])
    write(PUBLIC/'formal-results.json',summary)
    write(PUBLIC/'development-extension-disagreements-originals.json',[r for r in differences if r['split']!='heldout'])
    write(PUBLIC/'heldout-disagreement-indicators.json',[{k:v for k,v in r.items() if k not in {'round1','round2'}}
          for r in differences if r['split']=='heldout'])
    lines=['# F2.1 正式三组评测','',
        '162 个预定题位，18 个全新 gpt-6-astra/high 评审线程。先封存全部原始评分，再统一揭盲。两遍独立判定，不取平均、不追加裁决。',
        '',f"完成状态：{summary['statuses']}。首回合环境前置失败按用户特批作废，事故用量保留；替代尝试占原题位。后续失败不补跑。",'']
    for comparator,title in [('original_pi','整套系统 vs 原版 Pi'),('prepared','金融层 vs prepared')]:
        lines += [f'## {title}','','| split | 第一遍 E4 | 倒序遍 E4 | 修订协议结论 |',
                  '|---|---|---|---|']
        for split in ['development','heldout','extension']:
            c=splits[split]['comparisons'][comparator]
            lines.append(f"| {split} | {c['passes']['round1']['result']} | {c['passes']['round2']['result']} | {c['verdict']} |")
        lines += ['',f"开发核心与 held-out 同时满足 E4：{'是' if summary['overall_E4_by_comparator'][comparator] else '否'}。扩展集单列，不抵消其他 split 的失败。",'']
    lines += ['## 两遍质量与补充成本指标','','| split | 评审 | 组别 | 完成且无实质缺陷 | 缺陷回合/条目 | R1 | R2 | R3 | R4 | R5 | C | 每完成且无缺陷回合已知输入 |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for split,v in splits.items():
        for rd,groups in v['groups'].items():
            for profile,g in groups.items():
                scores=' | '.join(fmt(g['scores'][d]) for d in math.DIMS)
                lines.append(f"| {split} | {rd} | {profile} | {g['completed_without_material_defect']}/{g['cases']} | {g['material_defective_cases']}/{g['reviewer_material_entries']} | {scores} | {fmt(g['known_input_per_complete_clean_case'])} |")
    lines += ['','缺陷条目采用评审各自的原始机制划分，不由 N1 根据工具告警去重。补充成本指标包含失败尝试的已知输入；分母为该遍完成且无实质缺陷题位，不能替代 E4 成本判据。','',
              '## 可靠性','','| split | 有/无一致率 | κ | 适用维度平均绝对差 | 最大差 | 分歧分布 G/P/F | 下限通过 |','|---|---:|---:|---:|---:|---|---|']
    for split,v in splits.items():
        r=v['reliability'];dist='/'.join(str(r['material_disagreement_by_group'][p]) for p in ['original_pi','prepared','financial'])
        lines.append(f"| {split} | {r['agreement']:.2%} | {fmt(r['kappa'])} | {fmt(r['mean_absolute_score_difference'])} | {fmt(r['max_dimension_difference'])} | {dist} | {r['reliability_floor_passed']} |")
    lines += ['','## 分析用量','','| split | 组别 | 完成/预定 | 请求 | 未知请求 | 输入下界 | 输入观测上界 | 输出下界 | 目录费用下界 USD | 目录费用观测上界 USD |',
              '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for t in totals:
        values=[fmt(t[k]) for k in ['request_count','unknown_calls','input_lower','input_upper_observed_scenario','output_lower','catalog_cost_lower','catalog_cost_upper_observed_scenario']]
        lines.append(f"| {t['split']} | {t['profile']} | {t['completed']}/{t['positions']} | "+' | '.join(values)+' |')
    lines += ['','费用主判据为各对比配对题位费用中位数，上下界两种情景分别判定；数值见 formal-results.json。未知请求的上界使用同批、同组、同题观测最大值，是预声明的敏感性情景，不是数学保证或实付账单。没有同层观测时保持未知。',
        '', '原版 Pi 成本判据不成立时不得写“更省”或“成本更低”。入库、连通性准备、事故与独立评审分账，未取得的账单及评审 token 保持未知。',
        '', '题级重复明细、胜平负、条件于本题集的配对重复区间均在 formal-results.json。区间只描述固定题目的重复波动，不作跨公司或跨行业显著性推断。耗时为非隔离测量。',
        '', '全部评分与分歧原文留存私有目录；开发/扩展分歧另提供公开副本。held-out 对外只提供编号和指标，不披露题面、回答、源文及原始评语。A5、程序数值选择器、交付下载和沙箱复放须结合各自覆盖记录理解，均不能替代金融语义正确性。']
    (PUBLIC/'FORMAL_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(PUBLIC/'FORMAL_REPORT.md'),'cases':162,'heldout_prose_exported':False}))


if __name__=='__main__':
    main()

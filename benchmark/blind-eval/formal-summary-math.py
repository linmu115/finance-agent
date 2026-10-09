"""Pure aggregation under V3_PROTOCOL_REVISION_20261009; no score access/IO."""
from collections import Counter
from statistics import mean, median
import random

DIMS = ['reading','substantive','explanation','adjustments','anomalies','common']
DEPTH = ['explanation','adjustments','anomalies']


def reliability(first, second):
    assert set(first) == set(second)
    keys = sorted(first)
    n = len(keys)
    assert n > 0
    matrix = [[0,0],[0,0]]
    differences = []
    disagreements = []
    distributed = Counter()
    for key in keys:
        a,b=first[key],second[key]
        assert a['profile']==b['profile'] and a['task']==b['task']
        x,y=bool(a['material_defects']),bool(b['material_defects'])
        matrix[int(x)][int(y)]+=1
        delta={}
        for dim in DIMS:
            av,bv=a['scores'][dim],b['scores'][dim]
            if av is None or bv is None:
                if av is not None or bv is not None:raise ValueError('Applicable dimension mismatch')
                delta[dim]=None
            else:
                delta[dim]=bv-av;differences.append(abs(bv-av))
        if x!=y:distributed[a['profile']]+=1
        if x!=y or any(v for v in delta.values() if v is not None):
            disagreements.append({'label':key,'profile':a['profile'],'task':a['task'],
                                  'material_presence':[x,y],'delta':delta})
    agreement=(matrix[0][0]+matrix[1][1])/n
    p1=(matrix[1][0]+matrix[1][1])/n;p2=(matrix[0][1]+matrix[1][1])/n
    chance=p1*p2+(1-p1)*(1-p2)
    kappa=(agreement-chance)/(1-chance) if chance!=1 else None
    mad=mean(differences) if differences else None
    return {'n':n,'material_presence_matrix':matrix,'agreement':agreement,'kappa':kappa,
            'kappa_note':'undefined under degenerate equal marginals' if kappa is None else None,
            'mean_absolute_score_difference':mad,'max_dimension_difference':max(differences) if differences else None,
            'material_disagreement_by_group':{p:distributed[p] for p in ['original_pi','prepared','financial']},
            'reliability_floor_passed':agreement>=.8 and mad is not None and mad<=.5,
            'disagreements':disagreements}


def group_summary(rows, usage):
    completed=sum(usage[r['label']]['status']=='completed' for r in rows)
    clean=sum(usage[r['label']]['status']=='completed' and not r['material_defects'] for r in rows)
    input_sum=sum(usage[r['label']]['input_lower'] for r in rows)
    costs=[usage[r['label']]['catalog_cost_lower'] for r in rows]
    return {'cases':len(rows),'host_completed':completed,'completed_without_material_defect':clean,
            'material_defective_cases':sum(bool(r['material_defects']) for r in rows),
            'reviewer_material_entries':sum(len(r['material_defects']) for r in rows),
            'scores':{d:mean(values) if (values:=[r['scores'][d] for r in rows if r['scores'][d] is not None]) else None for d in DIMS},
            'scored_counts':{d:sum(r['scores'][d] is not None for r in rows) for d in DIMS},
            'known_input_total':input_sum,'known_input_per_complete_clean_case':input_sum/clean if clean else None,
            'catalog_cost_per_complete_clean_case':sum(costs)/clean if clean and all(v is not None for v in costs) else None}


def cost_comparison(frows, brows, usage):
    key=lambda r:(r['task'],r['repeat'])
    fmap={key(r):usage[r['label']] for r in frows};bmap={key(r):usage[r['label']] for r in brows}
    assert set(fmap)==set(bmap)
    checks={};scenarios={}
    for name,field in [('lower','catalog_cost_lower'),('upper','catalog_cost_upper_observed_scenario')]:
        f=[fmap[k][field] for k in sorted(fmap)];b=[bmap[k][field] for k in sorted(bmap)]
        known=all(v is not None for v in f+b)
        checks[name]=median(f)<=median(b) if known else None
        scenarios[name]={'financial_paired_median':median(f) if known else None,'comparator_paired_median':median(b) if known else None,
                         'financial_total':sum(f) if known else None,'comparator_total':sum(b) if known else None,
                         'paired_difference_median':median(x-y for x,y in zip(f,b)) if known else None}
    # This extra diagnostic does not replace the two preregistered same-scenario tests.
    fu=[fmap[k]['catalog_cost_upper_observed_scenario'] for k in sorted(fmap)]
    bl=[bmap[k]['catalog_cost_lower'] for k in sorted(bmap)]
    cross=median(fu)<=median(bl) if all(v is not None for v in fu+bl) else None
    price_verified=all(v.get('host_and_raw_catalog_agree') is True for v in list(fmap.values())+list(bmap.values()))
    both=all(v is True for v in checks.values())
    has_unknown=any(v['unknown_calls'] for v in list(fmap.values())+list(bmap.values()))
    result='不确定' if not price_verified else '成立' if both else '不确定' if has_unknown or any(v is None for v in checks.values()) or len(set(checks.values()))>1 else '不成立'
    return {'scenarios':scenarios,'checks':checks,'has_unknown_requests':has_unknown,'host_catalog_reconciled':price_verified,'protocol_cost_result':result,'cross_bound_dominance_descriptive_only':cross,
            'interpretation':'Two protocol-defined observational scenarios; not a guaranteed bound on unknown actual bills.'}


def comparison(one_pass, usage, comparator):
    groups={p:[r for r in one_pass if r['profile']==p] for p in ['financial',comparator]}
    f,b=[group_summary(groups[p],usage) for p in ['financial',comparator]]
    cost=cost_comparison(groups['financial'],groups[comparator],usage)
    applicable=[d for d in DEPTH if f['scores'][d] is not None and b['scores'][d] is not None]
    depths={d:f['scores'][d]>=b['scores'][d] for d in applicable}
    strict=any(f['scores'][d]>b['scores'][d] for d in applicable)
    quality=f['material_defective_cases']<=b['material_defective_cases'] and f['reviewer_material_entries']<=b['reviewer_material_entries']
    all_completed=all(usage[r['label']]['status']=='completed' for r in groups['financial']+groups[comparator])
    review_complete=all(r.get('critical_unreviewed') is False for r in groups['financial']+groups[comparator])
    checks={'material_cases_and_entries_not_more':quality,'all_applicable_depth_means_not_lower':all(depths.values()) and bool(applicable),
            'at_least_one_depth_dimension_strictly_higher':strict,'cost_both_scenarios':cost['protocol_cost_result']=='成立',
            'paired_participants_complete':all_completed,'critical_delivery_review_complete':review_complete}
    if not all_completed or not review_complete or cost['protocol_cost_result']=='不确定':status='未证实'
    else:status='成立' if all(checks.values()) else '不成立'
    return {'comparator':comparator,'groups':{'financial':f,comparator:b},'checks':checks,'depth_dimensions':applicable,'cost':cost,'result':status}


def independent_verdict(first, second, reliability_passed):
    if not reliability_passed:return '评审可靠性不足，未证实'
    if first==second=='成立':return '成立'
    if first==second=='不成立':return '不成立'
    if first==second=='未证实':return '未证实'
    return '两遍不一致，未证实'


def paired_task_summary(one_pass, comparator, resamples=10000, seed=2026100903):
    """Equal task weight; bootstrap repeats within each fixed task, not companies.

    These intervals describe repeat variation conditional on these exact prompts.
    They do not enter E4 or imply a population-level significance result.
    """
    selected=[r for r in one_pass if r['profile'] in {'financial',comparator}]
    keyed={(r['task'],r['repeat'],r['profile']):r for r in selected}
    assert len(keyed)==len(selected)
    results={}
    for dim in DIMS:
        tasks={}
        for task in sorted({r['task'] for r in selected}):
            repeats=sorted({r['repeat'] for r in selected if r['task']==task})
            pairs=[(keyed[(task,i,'financial')]['scores'][dim],keyed[(task,i,comparator)]['scores'][dim]) for i in repeats]
            assert all((a is None)==(b is None) for a,b in pairs)
            values=[(a,b) for a,b in pairs if a is not None]
            if not values:continue
            diffs=[a-b for a,b in values]
            tasks[task]={'n':len(values),'financial_mean':mean(a for a,b in values),
                'comparator_mean':mean(b for a,b in values),'paired_differences':diffs,
                'paired_mean':mean(diffs),'paired_median':median(diffs),'paired_range':[min(diffs),max(diffs)],
                'win_tie_loss':[sum(x>0 for x in diffs),sum(x==0 for x in diffs),sum(x<0 for x in diffs)]}
        if not tasks:
            results[dim]=None;continue
        families={task:('D2-D3' if task in {'D2','D3'} else task) for task in tasks}
        sizes={}
        for task,t in tasks.items():
            family=families[task]
            if family in sizes:assert sizes[family]==t['n']
            sizes[family]=t['n']
        rng=random.Random(seed)
        bootstrap=[]
        for _ in range(resamples):
            indices={family:rng.choices(range(n),k=n) for family,n in sizes.items()}
            bootstrap.append(mean(mean(t['paired_differences'][i] for i in indices[families[task]]) for task,t in tasks.items()))
        bootstrap.sort()
        def quantile(p):
            at=(len(bootstrap)-1)*p;lo=int(at);hi=min(lo+1,len(bootstrap)-1)
            return bootstrap[lo]+(bootstrap[hi]-bootstrap[lo])*(at-lo)
        results[dim]={'tasks':tasks,'equal_task_weight_mean_difference':mean(t['paired_mean'] for t in tasks.values()),
            'conditional_repeat_bootstrap_95_interval':[quantile(.025),quantile(.975)]}
    return {'comparator':comparator,'dimensions':results,'seed':seed,'resamples':resamples,
        'scope':'Paired repeat resampling within each fixed task, equal task weights; D2/D3 share repeat draws to preserve the conversation chain. No company resampling, no population inference, no p value; descriptive and excluded from E4.'}

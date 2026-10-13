"""Offline-only design generation. No HTTP, model, database or runner imports."""
import hashlib
import itertools
import json
import random
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
OUT = ROOT / 'data/evaluation/blind-eval-v3-design-20261008'


def read(name):
    return json.loads((BASE / name).read_text(encoding='utf-8-sig'))


def save(name, obj):
    (BASE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def schedule(chains, permutations, seed):
    result=[]
    rng=random.Random(seed)
    for rep, order in enumerate(permutations,1):
        block=list(chains)
        rng.shuffle(block)
        for chain in block:
            for arm in order:
                key=f'v3-DRAFT-{seed}-r{rep}-{chain[0]}-{arm}'
                for i,task in enumerate(chain):
                    result.append({'ordinal':len(result)+1,'task':task,'arm':arm,'repeat':rep,'chain':chain[0],'isolation_key_template':key+'-{freeze}-{batch_uuid}','same_session_as':chain[i-1] if i else None,'evaluation':{'profile_logical':arm,'analysis_only':True,'isolation_key':None},'documentIds':[],'executable':False})
    return result


def main():
    arm=['original_pi','prepared','financial']
    f1,b,x=read('f1-config.json'),read('f14-stage-b-config.json'),read('f14-x7-config.json')
    tasks={t['id']:t for c in [f1,b,x] for t in c['tasks']}
    config={'schema':'blind-eval-v3-design-1','status':'approved_waiting_v3_implementation_and_freeze','executionEnabled':False,'model':'gpt-6-luna','provider':'cpa-local','main_reasoning':'high','router_reasoning':'low','arms':arm,'original_pi_api_profile':'original_pi','baseline_contract':'V3_THREE_ARM_PLAN_20261008.md','freeze':None,'dataSnapshots':{},'concurrency':{'max_chains':2,'distinct_active_arms':True,'dispatch':'preserve planned chain launch order; wait if next arm already active','rotation':['original_pi+prepared','prepared+financial','financial+original_pi'],'latency_is_isolated':False},'repeats':2,'tasks':[tasks[t] for t in ['D1','X3','X7']],'evaluationLimits':f1['evaluationLimits'],'request_contract':{'evaluation.analysis_only':True,'documentIds':[],'isolation_key':'fresh per chain/arm/repeat/freeze','budget_group_id':'same scope per chain; no cross-arm sharing'},'cancel_policy':'atomic stop-queue; check before every POST including same-chain successor; no successor after cancel','infrastructure_failure':'retain_no_manual_retry_continue','validity_failure':'stop_queue','judge':{'model':'gpt-6-astra','reasoning_effort':'high','passes':2,'fresh_thread_each_pass':True,'fork_turns':'none','seal_before_unblind':True},'gate':{'status':'approved_20261008','material_defective_cases':{'financial_lte_prepared_minus':2,'financial_lte_prepared_fraction':0.5,'if_prepared_lte_1':'inconclusive_floor'},'deduplicated_material_entries':'F <= P','R3_tasks':['D1','X3','X7'],'R5_primary_tasks':['D1','X3'],'R5_auxiliary_tasks':['X7'],'R3_R5':'paired mean F >= P in each pass','completion':'F >= P','product_failures_all_arms':0,'known_input_total_and_paired_median':'F <= P','unknown_usage_or_incomplete_pairs':'inconclusive','stability':{'all_material_presence_agree':True,'mean_abs_score_delta_max':0.5,'single_score_delta_max':1}},'blocking_items':['original_pi request capture verified against approved contract','v3 P0/P1.0/P2 merged and frozen','fresh project snapshots after ingestion paused','actual HTTP adapter cancellation verified with offline request capture'],'referenceFiles':['reference-development.json','reference-stage-b-additions.json','reference-stage-c-X7.json','selectors-stage-b-additions.json','selectors-stage-c-X7.json','rubric.md']}
    config['referenceDigests']={n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in config['referenceFiles']}
    save('v3-gate-plan.json',config)
    gate=[]
    orders=[arm,arm[1:]+arm[:1],arm[2:]+arm[:2]]
    for rep in [1,2]:
        for task,order in zip(['D1','X3','X7'],orders):
            for group in (order if rep==1 else list(reversed(order))):
                gate.append({'ordinal':len(gate)+1,'task':task,'arm':group,'repeat':rep,'isolation_key_template':f'v3-gate-{{freeze}}-{{batch_uuid}}-{task}-{group}-r{rep}','new_session':True,'analysis_only':True,'documentIds':[],'executable':False})
    save('v3-gate-schedule.json',gate)
    core=[['D1'],['D2','D3'],['BH1'],['BH2'],['BH3']]
    extension=[['X1'],['X3'],['X4'],['X5'],['X6'],['X7']]
    full=schedule(core,list(itertools.permutations(arm)),20261008)
    full+=schedule(extension,[arm,arm[1:]+arm[:1],arm[2:]+arm[:2]],20261009)
    for i,r in enumerate(full):r['ordinal']=i+1
    save('v3-formal-schedule.json',full)
    assert len(gate)==18 and len(full)==162
    assert set(Counter((r['task'],r['arm']) for r in gate).values())=={2}
    counts=Counter((r['task'],r['arm']) for r in full)
    assert all(n==(3 if t.startswith('X') else 6) for (t,_),n in counts.items())
    positions=Counter((r['arm'],i%3) for i,r in enumerate(gate))
    assert set(positions.values())=={2}
    for i,r in enumerate(full):
        if r['task']=='D3':
            prev=full[i-1]
            assert prev['task']=='D2' and prev['arm']==r['arm'] and prev['isolation_key_template']==r['isolation_key_template']
    result={'offline_only':True,'gate_turns':len(gate),'formal_turns':len(full),'formal_sessions':len(set(r['isolation_key_template'] for r in full)),'gate_position_counts':{str(k):v for k,v in positions.items()},'chain_order_verified':True,'network_calls':0,'paid_calls':0,'limitation':'Design schedule validated; not an implemented original_pi adapter or cancellation integration test.'}
    (OUT/'schedule-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()

"""Compare frozen source-first answers with legacy labels; never reads model predictions."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json
from pathlib import Path

here=Path(__file__).resolve().parent
source=here/'acceptance_a_independent_answers.json'
independent=json.loads(source.read_text(encoding='utf-8'))
assert independent['legacy_labels_accessed'] is False
gold_path=here.parent/'evaluator/gold.jsonl'
legacy={r['id']:r for r in [json.loads(s) for s in gold_path.read_text(encoding='utf-8').splitlines()]}
fractional_percent_indices={2,6,9,16,19,21,24,26,28,31,34,36,38}
corrections={
 1:'旧程序把1.11与1.08相加再除基期；百分比变化必须先相减。',
 10:'旧程序仅给44.11−39.03=5.08美元价差；原问明确percentage increase，必须再除39.03并转百分数。',
 14:'旧程序回答相对增长率0.14555，原问未要求百分比。按增加额口径为0.54美元/股，单位元数据须公开以固定该口径。',
 23:'829本身已经是所得税费用，旧程序又乘29%形成240.41，重复施加税率。',
 27:'题目投资100000美元，旧程序使用const_1000000，导致净收益被放大10倍。',
 29:'旧程序只计算支付额差−2072，原问明确percentage change，必须除11057并转百分数。',
 32:'旧程序最终等于119/2=59.5，与2014至2015研发费用百分比变化无关。',
 37:'旧程序仅计算销售额差284.5，原问growth rate必须再除2017的16772.9。',
}
items=[]
for index,base in enumerate(independent['items']):
    item=deepcopy(base);old=legacy[item['id']]
    # input_sha256 was frozen during the source-only review, before legacy access.
    item['source_sha256']=item['input_sha256']
    item['legacy_answer']=old['answer']
    item['legacy_unit']=old['unit']
    item['legacy_program']=old['program']
    item['legacy_recomputed']=old.get('recomputed')
    item['legacy_citations']=old['citations']
    item['legacy_abs_tolerance']=old['abs_tolerance']
    if item['independent_status']=='ambiguous':
        item['label_status']='ambiguous'
        item['status']='insufficient_evidence'
        item['reason_code']='ambiguous_question_or_source'
        item['legacy_comparison']='Legacy selected one interpretation despite underspecified target, period, or source.'
    else:
        item['status']='ok'
        factor=Decimal(100 if index in fractional_percent_indices else 1)
        equivalent=Decimal(old.get('recomputed') or old['answer'])*factor
        item['legacy_unit_scale_to_canonical']=str(factor)
        item['legacy_answer_in_canonical_units']=str(equivalent)
        if index in corrections:
            item['label_status']='corrected';item['legacy_comparison']=corrections[index]
            item['rationale']+=' '+corrections[index]
        else:
            assert abs(equivalent-Decimal(item['canonical_answer']))<=Decimal('0.000001'),item['id']
            item['label_status']='verified'
            item['legacy_comparison']='Same financial quantity after explicit ratio-to-percentage normalization; new answer retains full Decimal precision.' if factor==100 else 'Independent answer agrees with legacy recomputation; new answer retains full Decimal precision.'
    # Minimal sufficient alternatives for evidence-of-ambiguity; no answer value changes.
    prefix=item['id']+':'
    if index==25:
        item['evidence_sets']=[[prefix+'table_0',prefix+'table_3'],[prefix+'table_3',prefix+'text_19']]
        item['valid_context_citations'] += [prefix+'text_21',prefix+'text_22',prefix+'text_24']
    if index==30:
        item['evidence_sets']=[[prefix+'table_0'],[prefix+'table_0',prefix+'table_2',prefix+'text_8']]
        item['valid_context_citations'] += [prefix+'table_2',prefix+'text_8']
    if index==33:
        item['evidence_sets']=[[prefix+'text_0'],[prefix+'table_0',prefix+'text_1']]
        item['valid_context_citations'] += [prefix+'table_1']
    if index==39:
        item['evidence_sets']=[[prefix+'table_0',prefix+'table_1'],[prefix+'table_1',prefix+'text_2']]
        item['valid_context_citations'] += [prefix+'text_8']
    item['valid_context_citations']=list(dict.fromkeys(item['valid_context_citations']))
    items.append(item)
counts={status:sum(r['label_status']==status for r in items) for status in ['verified','corrected','ambiguous']}
report={'schema_version':'finance-source-curation-0.2','reviewer':'Codex independent agent /root/financial_service; not human double annotation',
 'scope':'Acceptance FinQA by lexicographic ID, first 40 of 80','created_at':datetime.now(timezone.utc).isoformat(),
 'workflow':'Read only agent_input and independently solve all 40; persist Decimal answers and hash; only then compare legacy evaluator gold. No model predictions read.',
 'independent_completed_at':independent['completed_at'],'independent_solution_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'legacy_gold_sha256':hashlib.sha256(gold_path.read_bytes()).hexdigest(),'original_assets_modified':False,'legacy_labels_modified':False,'model_predictions_accessed':False,
 'label_policy':'verified: same financial quantity after declared unit normalization; corrected: wrong operation, target, year or scale; ambiguous: no unique unconditional answer from supplied source. Every row is retained.',
 'counts':counts,'items':items}
(here/'curation-acceptance-a.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts));print('Independent frozen hash',report['independent_solution_sha256'])

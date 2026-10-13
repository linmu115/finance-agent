"""Freeze approved X7 against independently viewed CAS annual-report pages."""
import copy
import hashlib
import json
import shutil
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/evaluation/blind-eval-haier-reference-20261008'
BENCH = ROOT / 'benchmark/blind-eval'
SRC = ROOT / 'data/evaluation/blind-eval-analyst-alignment-20261008'


def read(p):
    return json.loads(p.read_text('utf-8-sig'))


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    with p.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


draft = next(t for t in read(SRC / 'new-task-drafts.json')['tasks'] if t['id'] == 'X7')
ref = copy.deepcopy(draft['reference'])
ref['status'] = 'frozen_before_any_X7_answer'
values = ref['values']
raw = {
    'revenue': ['285981225203.93', '274204520847.97', '261427783050.10'],
    'parent_profit': ['18741120122.93', '16596615045.87', '16596615045.87'],
    'adjusted_parent_profit': ['17804732809.63', '15824164161.43', '15824164161.43'],
    'cfo': ['26543081911.96', '26535780568.36', '25262376228.30'],
    'parent_equity': ['111366118999.17', '101265984771.17', '103514153535.04'],
    'assets': ['290113822824.61', '261067684897.49', '253379859977.97'],
}
checks = []


def add(key, value, unit, pages, formula=None, role='required_numeric'):
    checks.append({'key': 'X7.' + key, 'task': 'X7', 'expected': {
        'value': str(value), 'unit': unit, 'absolute_tolerance': '0.005'},
        'source_pages': {'annual': pages}, 'role': role, 'formula': formula,
        'missing_policy': 'report_missing_for_review_not_automatic_material_defect'})


for metric, amounts in raw.items():
    assert amounts == values[metric]['values_CNY_2024_2023adjusted_2023original']
    a, b, c = map(D, amounts)
    computed = {'adjustment_2023_CNY': b-c,
                'growth_using_adjusted_percent': (a/b-1)*100,
                'growth_using_original_percent': (a/c-1)*100}
    computed['growth_difference_pp'] = computed['growth_using_original_percent'] - computed['growth_using_adjusted_percent']
    for k, v in computed.items():
        assert abs(v-D(values[metric][k])) < D('1e-20')
        values[metric][k] = str(v)
    for label, amount in zip(['2024', '2023_adjusted', '2023_original'], [a, b, c]):
        add(metric+'_'+label, amount/D(1000000), 'CNY_million', [10])
    add(metric+'_adjustment_2023', (b-c)/D(1000000), 'CNY_million', [10], 'adjusted - original')
    role = 'required_numeric' if metric in ['revenue', 'parent_profit', 'cfo'] else 'supporting_if_present'
    for k in ['growth_using_adjusted_percent', 'growth_using_original_percent', 'growth_difference_pp']:
        add(metric+'_'+k, computed[k], 'pp' if k.endswith('_pp') else '%', [10],
            '((2024 / comparative) - 1) * 100; difference = original-basis growth - adjusted-basis growth', role)

margins = [D(p)/D(r)*100 for p, r in zip(raw['parent_profit'], raw['revenue'])]
for label, value in zip(['2024', '2023_adjusted', '2023_original'], margins):
    assert abs(value-D(values['parent_margin_percent'][label])) < D('1e-20')
    values['parent_margin_percent'][label] = str(value)
    add('parent_margin_'+label, value, '%', [10], 'parent profit / revenue * 100')
for label, value in [('2023_adjustment_pp', margins[1]-margins[2]),
                     ('2024_change_adjusted_pp', margins[0]-margins[1]),
                     ('2024_change_original_pp', margins[0]-margins[2])]:
    values['parent_margin_percent'][label] = str(value)
    add('parent_margin_'+label, value, 'pp', [10], 'difference of percentage margins')

r = D(raw['revenue'][1]); cost = D('198838470796.47'); sales = D('32726735817.73'); warranty = D('8328087511.15')
w = values['warranty_reclassification_2023']
w['source_inputs_CNY'] = {'adjusted_revenue_2023': str(r), 'adjusted_cost_2023': str(cost),
                           'adjusted_sales_expense_2023': str(sales)}
computed = {'cost_adjustment_CNY': warranty, 'sales_expense_adjustment_CNY': -warranty,
            'gross_margin_adjustment_pp': -warranty/r*100,
            'sales_expense_ratio_adjustment_pp': -warranty/r*100,
            'reported_adjusted_gross_margin_percent': (r-cost)/r*100,
            'same_scope_before_this_policy_gross_margin_percent': (r-cost+warranty)/r*100,
            'reported_adjusted_sales_ratio_percent': sales/r*100,
            'same_scope_before_this_policy_sales_ratio_percent': (sales+warranty)/r*100,
            'operating_profit_effect_CNY': D(0)}
for k, value in computed.items():
    assert abs(value-D(w[k])) < D('1e-20')
    w[k] = str(value)
    add('warranty_'+k, value/D(1000000) if k.endswith('_CNY') else value,
        'CNY_million' if k.endswith('_CNY') else 'pp' if k.endswith('_pp') else '%', [121, 122, 163],
        'Hold adjusted revenue and consolidation scope fixed; reverse only the disclosed cost/selling-expense reclassification.')

for k, v in values['weighted_parent_ROE'].items():
    if k != 'pdf_page':
        add('weighted_ROE_'+k, D(v), 'pp' if k.endswith('_pp') else '%', [11],
            'Disclosed weighted ROE, or difference in percentage points; not average-equity ROE.')

nonrec = values['nonrecurring']
for name, amounts in [('net_parent_contribution', nonrec['net_parent_contribution_2024_2023_CNY']),
                      ('government_grants', nonrec['government_grants_2024_2023_CNY'])]:
    for year, amount in zip(['2024', '2023'], amounts):
        add(name+'_'+year, D(amount)/D(1000000), 'CNY_million', [10, 12])
for index in [0, 1]:
    assert D(raw['parent_profit'][index])-D(raw['adjusted_parent_profit'][index]) == D(nonrec['net_parent_contribution_2024_2023_CNY'][index])
nonrec['component_sign_note'] = 'Page 12 income-tax and minority-interest effects are shown as negative contributions; do not subtract their signed values a second time. Government grants are not the net parent contribution.'
nonrec['continuity_boundary'] = 'Two disclosed periods support a recurrence observation, not a permanent forecast or a unilateral change to statutory nonrecurring classification.'

ref['restatement_evidence'] = {
    'quarter_restatement': {'pages': [12], 'fact': '2024年12月物流业务同一控制合并，前三季度财务数据重述。'},
    'policy_reclassification': {'pages': [94, 163], 'fact': '准则解释第18号；保证类质保费用从销售费用转营业成本，追溯调整；本项不改变营业利润。'},
    'combination': {'pages': [213, 214], 'fact': '优瑾（上海）企业管理有限公司，取得45%权益，合并前后均受海尔集团控制；2024年12月，表决权转让。',
                    'comparative_acquiree_revenue_CNY': '18423619653.79',
                    'group_revenue_comparative_adjustment_CNY': str(D(raw['revenue'][1])-D(raw['revenue'][2])),
                    'boundary': '被合并方收入不等于集团抵销后比较收入增量。两数差额不得无证据全认作内部抵销；CFO、权益、资产与ROE的逐项变化未从披露构成完整定量桥。'},
    'cross_disclosure_limit': {'pages': [12, 123, 214], 'fact': '合并利润表下方的被合并方合并前净利润（当期0、上期-2,581,701.76）与并购附注的被合并方净利润不直接相同。范围/抵销未逐项闭合，不能拿附注净利润直接解释归母利润调整。',
                               'grading': 'Supporting source conflict only; no extra mandatory numerical bridge beyond original question.'},
}
ref['delivery_interpretation'] = '按已批准题面的 Markdown/PDF、Excel/CSV 选择满足，不追加必须同时提交两种格式；图表与可复算文件须按题面检查。'

pages = [10, 11, 12, 94, 121, 122, 123, 135, 137, 163, 213, 214]
viewed = [10, 11, 12, 121, 122, 123, 163, 213, 214]
OUT.mkdir(exist_ok=True)
(OUT / 'source-pages').mkdir(exist_ok=True)
evidence = []
for page in pages:
    row = {'page': page, 'image_visually_verified_this_freeze': page in viewed}
    for extension in ['txt', 'png']:
        source = SRC / f'sources/haier2024-p{page}.{extension}'
        target = OUT / f'source-pages/annual-p{page}.{extension}'
        shutil.copyfile(source, target)
        row[extension] = str(target.relative_to(OUT)).replace('\\', '/')
        row[extension+'_sha256'] = digest(target)
    evidence.append(row)
pdf = ROOT / 'samples/native-pdf/海尔智家2024年年度报告.pdf'
final = {'version': 'stage-c-X7-v1-20261008', 'status': ref['status'],
         'rubric_version': 'analyst-requirements-v2-20261008',
         'task_prompt': draft['prompt'], 'tasks': {'X7': ref},
         'task_requirements': {'X7': ref['task_requirements']},
         'sources': {'annual': {'file': str(pdf.relative_to(ROOT)).replace('\\', '/'), 'sha256': digest(pdf),
                    'document_id': 'e7b0d9679ddc4b739f8f35ecb6dc6227',
                    'page_numbering': '1-based physical PDF pages equal printed page numbers', 'evidence': evidence}},
         'preparation_status': 'Reference freeze only; project data freeze and execution require coordinator notice.'}
reference_path = BENCH / 'reference-stage-c-X7.json'
selector_path = BENCH / 'selectors-stage-c-X7.json'
write(reference_path, final)
write(selector_path, {'version': final['version'], 'reference': reference_path.name,
                      'binding_policy': read(BENCH / 'selectors-stage-b-additions.json')['binding_policy'], 'checks': checks})
write(OUT / 'freeze-receipt.json', {'frozen_at': datetime.now(timezone.utc).isoformat(),
      'purpose': 'X7 approved prompt final reference/selector freeze before any X7 answer',
      'model_calls': 0, 'product_or_database_writes': 0, 'reference': str(reference_path.relative_to(ROOT)),
      'reference_sha256': digest(reference_path), 'selectors': str(selector_path.relative_to(ROOT)),
      'selectors_sha256': digest(selector_path), 'selectors_count': len(checks),
      'source_sha256': digest(pdf), 'visually_verified_pages': viewed,
      'draft_prompt_sha256': hashlib.sha256(draft['prompt'].encode()).hexdigest(),
      'calculation_check': 'Decimal recalculated all draft values; compared to independently viewed raw page cells.'})
print(json.dumps({'reference': str(reference_path), 'selectors': len(checks)}, ensure_ascii=False))

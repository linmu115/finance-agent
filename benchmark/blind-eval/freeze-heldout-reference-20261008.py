"""N1-only, offline H1/H2 source/reference freeze. No participant calls or DB writes."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'benchmark/blind-eval'
EVIDENCE = ROOT / 'data/evaluation/blind-eval-tsingtao-F1-20261008'
DEST = ROOT / 'data/evaluation/blind-eval-heldout-reference-20261008'


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


old = read(ROOT / 'data/evaluation/blind-eval-preparation-20261007/reference-drafts.json')['H1_H2']
spot = read(EVIDENCE / 'source-spotchecks.json')
assert all(x['presence_period_currency_scope_match'] for x in spot['checks'])
pdf = ROOT / 'data/evaluation/blind-eval-preparation-20261007/sources/Tsingtao_2024_Annual.pdf'
assert sha(pdf) == spot['pdf_sha256']
raw = {k: list(map(lambda v: D(str(v)), values)) for k, values in old['raw'].items()}
bridge = {k: list(map(lambda v: D(str(v)), values)) for k, values in old['cash_bridge'].items()}
bridge_sums = [sum(values[i] for values in bridge.values()) for i in range(2)]
assert bridge_sums == raw['cfo']
deltas = {k: values[0] - values[1] for k, values in bridge.items()}
assert sum(deltas.values()) == raw['cfo'][0] - raw['cfo'][1]
stress = raw['cfo'][0] - bridge['payables'][0] + bridge['payables'][1]
assert stress == D(str(old['H2']['cfo_stress_CNY']))
growth = {k: (v[0] / v[1] - 1) * 100 for k, v in raw.items()}
for k, value in growth.items():
    assert abs(value - D(old['computed']['growth_percent'][k])) < D('1e-20')

pages = [5, 6, 7, 9, 10, 80, 85, 86, 87, 88, 91, 92, 175, 176]
source = {
    'file': str(pdf.relative_to(ROOT)).replace('\\', '/'),
    'sha256': sha(pdf),
    'document_id': 'e283313993ac49db8ccea8fb7dc87983',
    'page_numbering': '1-based physical PDF pages, identical to printed pages',
    'visually_verified_pdf_pages': [5, 6, 7, 10, 87, 175],
    'page_evidence': [
        {'text': f'source-pages/annual-p{n}.txt',
         'text_sha256': sha(EVIDENCE / f'source-pages/annual-p{n}.txt'),
         'image': f'source-pages/annual-p{n}.png',
         'image_sha256': sha(EVIDENCE / f'source-pages/annual-p{n}.png')}
        for n in pages
    ],
}
checks = []


def check(task, key, value, unit, source_pages, role='required_numeric', formula=None):
    checks.append({
        'key': task + '.' + key, 'task': task,
        'expected': {'value': str(value), 'unit': unit,
                     'absolute_tolerance': '0.05' if unit in ['%', 'pp'] else '0.005'},
        'source_pages': {'annual': source_pages}, 'role': role, 'formula': formula,
        'missing_policy': 'report_missing_for_review_not_automatic_material_defect',
    })


for metric, values in raw.items():
    for year, value in zip([2024, 2023], values):
        check('H1', f'{metric}_{year}', value / 1000000, 'CNY_million', [5, 87, 175])
    check('H1', metric + '_growth', growth[metric], '%', [5, 87, 175],
          formula='(2024 / 2023 - 1) * 100')
for metric, values in bridge.items():
    for year, value in zip([2024, 2023], values):
        check('H1', f'bridge_{metric}_{year}', value / 1000000, 'CNY_million', [175])
    check('H1', 'bridge_change_' + metric, deltas[metric] / 1000000, 'CNY_million', [175],
          formula='2024 signed bridge item - 2023 signed bridge item')
gm = [(1 - raw['cost'][i] / raw['revenue'][i]) * 100 for i in range(2)]
coverage = [raw['cfo'][i] / raw['consolidated_profit'][i] for i in range(2)]
parent_coverage = [raw['cfo'][i] / raw['parent_profit'][i] for i in range(2)]
nonrec = [raw['parent_profit'][i] - raw['adjusted_parent_profit'][i] for i in range(2)]
for i, year in enumerate([2024, 2023]):
    check('H1', f'gross_margin_{year}', gm[i], '%', [87])
    check('H1', f'cfo_consolidated_coverage_{year}', coverage[i], 'ratio', [175], 'conditional_if_reported')
    check('H1', f'cfo_parent_coverage_{year}', parent_coverage[i], 'ratio', [5], 'conditional_if_reported')
    check('H1', f'parent_nonrecurring_{year}', nonrec[i] / 1000000, 'CNY_million', [5, 7])
check('H1', 'gross_margin_change', gm[0] - gm[1], 'pp', [87])
check('H1', 'cfo_change', (raw['cfo'][0] - raw['cfo'][1]) / 1000000, 'CNY_million', [175])
check('H1', 'parent_nonrecurring_change', (nonrec[0] - nonrec[1]) / 1000000, 'CNY_million', [5, 7])
for k, v in old['Q4_2024_CNY'].items():
    check('H1', 'Q4_' + k, D(str(v)) / 1000000, 'CNY_million', [6])
for key, value, unit in [
    ('payables_original', bridge['payables'][0] / 1000000, 'CNY_million'),
    ('payables_replacement', bridge['payables'][1] / 1000000, 'CNY_million'),
    ('cfo_original', raw['cfo'][0] / 1000000, 'CNY_million'),
    ('cfo_stress', stress / 1000000, 'CNY_million'),
    ('cfo_delta', (stress - raw['cfo'][0]) / 1000000, 'CNY_million'),
    ('consolidated_profit', raw['consolidated_profit'][0] / 1000000, 'CNY_million'),
    ('original_coverage', coverage[0], 'ratio'),
    ('stress_coverage', stress / raw['consolidated_profit'][0], 'ratio'),
]:
    check('H2', key, value, unit, [175], formula='CFO_stress = CFO_2024 - payable_2024 + payable_2023; coverage denominator = consolidated net profit_2024')

nonrec_components = {
    'asset_disposal': [4267451, 178576672],
    'government_grants': [469273541, 391133874],
    'financial_asset_fv_and_disposal': [38777451, 148603623],
    'other_nonoperating': [38474909, 9643261],
    'tax_deduction': [113279107, 159057738],
    'minority_deduction': [43632559, 21773062],
}
for i in range(2):
    assert sum(v[i] for k, v in nonrec_components.items() if 'deduction' not in k) - sum(
        v[i] for k, v in nonrec_components.items() if 'deduction' in k) == nonrec[i]

h1 = {
    'task_requirements': old['task_requirements']['H1'],
    'period_order': [2024, 2023], 'source_scope': 'consolidated CAS; CNY yuan source, million CNY deliverable',
    'raw_CNY': old['raw'], 'growth_percent': {k: str(v) for k, v in growth.items()},
    'gross_margin_percent': list(map(str, gm)), 'gross_margin_change_pp': str(gm[0] - gm[1]),
    'cash_bridge_CNY': old['cash_bridge'],
    'bridge_change_CNY': {k: str(v) for k, v in deltas.items()},
    'bridge_sums_CNY': list(map(str, bridge_sums)), 'bridge_residual_CNY': ['0', '0'],
    'cfo_consolidated_profit_ratio': list(map(str, coverage)),
    'cfo_parent_profit_ratio': list(map(str, parent_coverage)),
    'Q4_2024_CNY': old['Q4_2024_CNY'],
    'parent_nonrecurring_CNY': list(map(str, nonrec)),
    'parent_nonrecurring_components_CNY': nonrec_components,
    'must_mention': [
        '收入下降而归母、扣非及合并利润增长，毛利率提升，不能据此认为经营全面改善；必须独立列出Q4收入、归母/扣非亏损和负CFO。',
        '年报p10将收入下降归于销量，成本降幅更大归于销量及部分原料成本下降；费用、减值和处置收益变化也有披露。业务解释须引用原文，不把全部利润变化归给一项。',
        '以合并净利润开始完整间接法现金桥；两年各行保留符号，逐行差额可加总至CFO改善2377.093992百万元，残差0。归母净利润不能替代合并起点。',
        '经营性应付调节的同比改善2879.028529百万元是主要正贡献，存货同比贡献-646.861022百万元反向；应收+50.168490百万元、合并净利+143.577762百万元等其余项目仍保留，不能只以净利润增长解释现金。',
        'p10公司解释CFO增长来自原料成本及销量下降导致支付原料款减少，以及支付各项税费减少；这与间接法数量桥是不同层次，不能将全部应付贡献直接解释为拖欠供应商或未来永久改善。',
        'Q4负利润、负CFO构成年度汇总的反证；单份年报的季度序列不能证明全部下降仅为季节性，更不能直接推断下一年同样发生。',
        '归母减扣非对应税及少数股东影响后的非经常总额，2024小于2023；现金桥的非现金调整不自动等于非经常损益。',
        '事实、管理层披露和自己的推论可辨；改善持续性与后续采购/付款/税款/销量条件相关，不能把桥接数字当未来预测。',
    ],
    'limits': [
        '题目没有要求逐项展开全部非经常损益税前明细；p7补充值供检查主动引用，不新增硬要求。',
        '毛利率按合并营业收入及营业成本计算；年报主营业务分行业毛利率口径可能不同，需说明而不能互换。',
        '现金覆盖率可用合并或归母分母但必须明示；现金桥起点只能是合并净利润。',
        '季度变动可准确描述；没有多年度季度证据时，季节性只能是待验证解释。',
    ],
}
h2 = {
    'task_requirements': old['task_requirements']['H2'],
    'formula': 'CFO_stress = 5154661132 - 669396598 + (-2209631931)',
    'original_CFO_CNY': str(raw['cfo'][0]), 'stress_CFO_CNY': str(stress),
    'change_CNY': str(stress - raw['cfo'][0]),
    'consolidated_profit_unchanged_CNY': str(raw['consolidated_profit'][0]),
    'coverage_original': str(coverage[0]), 'coverage_stress': str(stress / raw['consolidated_profit'][0]),
    'must_mention': [
        '仅替换经营性应付项目这一现金流调节行：先去掉2024项，再加入2023负数，其他利润和调节项固定2024。',
        '并列原值与压力值、差額及合并净利覆盖倍数，图/表/报告/计算文件一致。',
        '压力情景表明现金覆盖对指定应付贡献敏感，不能说明实际应付款必定这样变化，不能当公司预测或供应商付款原因的证明。',
        '这是固定其他变量的算术情景，不是完整经营预测，忽略了各变量现实中的联动。',
    ],
}
gold = {
    'version': 'heldout-reference-v1-20261008',
    'status': 'frozen_before_any_H1_H2_participant_answer',
    'rubric_version': 'analyst-requirements-v2-20261008',
    'evidence_root': str(EVIDENCE.relative_to(ROOT)).replace('\\', '/'),
    'sources': {'annual': source}, 'tasks': {'H1': h1, 'H2': h2},
}
selectors = {
    'version': gold['version'], 'reference': 'reference-heldout.json',
    'binding_policy': read(HERE / 'selectors-phase1.json')['binding_policy'],
    'precision_note': 'Values recomputed from unrounded yuan source; tolerance allows 2 decimal million CNY/ratio or 1 decimal percent/pp. Correct alternative displayed rounding remains judge-reviewable, not an automatic substantive error.',
    'checks': checks,
}
DEST.mkdir(exist_ok=False)
write_new(HERE / 'reference-heldout.json', gold)
write_new(HERE / 'selectors-heldout.json', selectors)
receipt = {
    'at': datetime.now(timezone.utc).isoformat(), 'participant_runs_started': 0,
    'source': source, 'semantic_review': 'N1 original pages; previous spot checks plus direct nonrecurring p7 visual inspection; no participant answers or outside agents used',
    'data_snapshot': {'path': str((EVIDENCE / 'material-freeze-H-project.json').relative_to(ROOT)), 'sha256': sha(EVIDENCE / 'material-freeze-H-project.json')},
    'preparation_state': {'submitted_tables': 59, 'candidate_tables': 310, 'remaining_tables': 251,
                          'heldout_required_tables_submitted': True, 'ingestion_paused': True,
                          'limits': 'Some submitted facts/table carry needs_review. Full report source is retained; complete ingestion not claimed. See N1 private preparation report.'},
    'checks': len(checks),
    'reference_files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in [HERE / 'reference-heldout.json', HERE / 'selectors-heldout.json']],
    'execution_state': 'Waiting for explicit F1.1 deployment notice and new runtime freeze; no H1/H2 execution authorized now',
    'access_scope': 'N1 only until isolated heldout judges receive anonymous answer/reference packages; not mainline/N2/N3 debugging material',
}
write_new(DEST / 'freeze-receipt.json', receipt)
print(json.dumps({'reference': 'benchmark/blind-eval/reference-heldout.json', 'selectors': 'benchmark/blind-eval/selectors-heldout.json', 'checks': len(checks), 'participant_calls': 0}))

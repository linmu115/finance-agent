"""Verify the affected output's binding path locally; export only mechanism and counts."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'data/evaluation/blind-eval-F12-heldout-20261008'
OUT = ROOT / 'data/evaluation/blind-eval-heldout-diagnostics-redacted-20261008'
rows = [json.loads(x) for x in (P/'F1_H2-audit.jsonl').read_text('utf-8-sig').splitlines()]
code = next(x['data']['args']['code'] for x in rows if x['type']=='tool_request' and x['data']['name']=='run_analysis')
report = (P/'F1_H2-artifacts/stress_report.md').read_text('utf8')
bound = [x['data'] for x in rows if x['type']=='answer_bound']
assert len(bound) == 1
assert len(re.findall(r'减少-\d[\d,.]*', report)) == 1
assert '减少{delta:,.3f}' in code
assert not re.search(r'\{\{(?:table:|[\w]+\.)', report)
template = bound[0]['template']
numeric = re.findall(r'\{\{(?!chart:)[^{}]+\}\}', template)
charts = re.findall(r'\{\{chart:[^{}]+\}\}', template)
assert len(numeric) == 0 and len(charts) == 1
assert not re.search(r'减少-\d[\d,.]*', bound[0]['rendered'])
result = {
    'scope': 'One material direction defect; two independent reviews agree; one underlying defect, not two.',
    'mechanisms': {
        'direction_word_combined_with_signed_change_inconsistently': 1,
        'scenario_update_order_or_effect_reversed': 0,
        'chart_direction_reversed': 0,
        'inflow_outflow_accounting_sign_reversed': 0,
    },
    'surface_counts': {'affected_generated_markdown_reports': 1, 'affected_final_chat_answers': 0},
    'binding_counts': {'affected_occurrence_A1_numeric_bound': 0,
        'final_chat_answer_bound_events': 1, 'final_chat_numeric_or_table_placeholders': 0,
        'final_chat_chart_placeholders': 1},
    'mechanism': 'A custom analysis script interpolated a correctly calculated signed change into a sentence with a directional verb. The sign convention of the number and the verb were not reconciled.',
    'A1_classification': 'The affected file occurrence was not A1 numeric-bound. It was calculated and formatted by custom script, not a wrongly rendered bound value and not a manually mistyped numeric constant.',
    'evidence_classes_checked': ['sealed reviewer categories', 'original delivered report', 'generation tool arguments', 'answer_bound template and rendered output'],
    'limits': 'Zero counts apply to this reviewed defect only, not a claim that every other direction in the batch is defect-free.',
}
(OUT/'direction-counts.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
(OUT/'direction-defect.md').write_text('''# 方向缺陷脱敏诊断

两遍独立评审指向同一个底层缺陷，计 **1 个**，不因两遍命中而计成两个。仅报告机制与计数，不含题面、回答摘录、财务数值、公司／文档信息或原文。

| 机制类别 | 本缺陷计数 |
|---|---:|
| 方向词与带符号变动量的组合不一致 | 1 |
| 情景更新先后顺序或作用方向反了 | 0 |
| 图表方向反了 | 0 |
| 现金流入／流出的会计符号写反了 | 0 |

**具体机制：**自定义分析脚本先算出带符号的变动量，再用字符串插值将其直接接在方向词后，没有协调“方向词＋幅度”和“带符号变动量”两种表达。计算本身与情景作用方向正确，出错的是生成报告中的措辞与符号组合。受影响交付报告 1 份；该处错误没有出现在最终聊天正文中。以上零计数仅针对这一个已确认缺陷，不代表整批其他位置均无方向问题。

**A1 覆盖：该处数值没有经过 A1 数值绑定。**它来自自定义脚本计算与格式化，再直接写入 Markdown 文件。归类应为“未绑定的自定义报告表达错误”；更精确地说，数值不是手抄错了，而是计算值旁的方向措辞错误。

该回合虽然有 1 次 `answer_bound` 事件，但其对象是最终聊天答案，不是这份脚本产物；模板中数值／整表占位符 0 个、图表占位符 1 个。因此，事件存在不能当作错误位置已经绑定的证据。

核对类别包括原始交付文件、生成脚本参数、A1 模板与渲染记录、两遍封存评审。底层证据保持 N1 私有，本目录只有统计结论。机器可读计数见 `direction-counts.json`。未修改产物、评分或产品。
''','utf8')
print(json.dumps({'material_direction_defects':1,'affected_A1_numeric_bound':0,'export':'direction-defect.md'},ensure_ascii=False))

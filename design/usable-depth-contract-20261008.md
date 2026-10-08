# N4 → N2：v3 分析深度字段契约

基线 `328b8e2`，N4 分支 `feat/usable-depth`。范围为 P1.2 / P1.4 / P1.5；不修改宿主、必经流水线、交付修复或服务。用户已明确授权本轮实施，覆盖 spec 中旧的阶段顺序限制。

## 组合入口

已读取 N2 工作树的 `design/n2-v3-workpaper-contract-20261008.md` 与主线回执。接受其公共入口 **`service/workpaper_depth.py::enrich_workpaper_context(service, project_id, *, selection, reports, context)`**。不修改 N2 的流水线。该函数把本文的 kind 原始字段映射为 N2 的 `management_evidence / signal_followups / comparability_constraints / extensions`，同时把 A1 表名转为 `statement_ / variance_ / signals_` 前缀。可接 raw 或 compiled report，不重复取数或检索。相同原句合并为一条并保留所有 linked_refs；信号通过 management_evidence_ids 关联。未传 comparison/expectations 等报告时约束扩展为 `not_provided`，不冒充已完成口径检查。

披露状态映射：quantitative → quantified，qualitative → qualitative_disclosed，not_stated → no_statement_found；未带 drivers_evidence 的旧报告保持 pending/partial，不能写成原文未说明。信号持续性同时返回 sample_count、allow_continuous_claim、assessment。约束同时返回 affected_refs、issues、record_ids、forbidden_claims，主线无需解析自然语言原因。

`variance_attribution` / `anomaly_signals` 已接受 N2 草案的 `_analysis=None` 内部参数，支持复用同一个 AnalystData；外部工具参数不变。N2 的实际函数传入 raw reports，与草案写的 compiled reports 略有不同，本适配器对两者均适用，因为只读取顶层深度字段。

三个字段均位于 **report 顶层**，并由 `answer_handoff` 原样投影到工具结果顶层。它们是普通 JSON 对象/数组，不需要反解析 CSV 或中文状态。`compile_report` 保留 report 顶层扩展字段。原有数值表、A1 绑定、交付文件继续保留。

- `variance_attribution`: `drivers_evidence[]`，含利润、现金和营运资金变动。
- `anomaly_signals`: `drivers_evidence[]`、`signal_followups[]`，只为已触发信号生成追问。
- `expectations` / `comparison`: `answer_constraints[]`。
- 未产出相应内容的 kind 可不带字段；消费者按空列表处理。N2 合并时按 `kind + key/id` 定位，不能只按不同 kind 的裸行键去重。

## drivers_evidence[]

```json
{
  "key": "finance_net",
  "driver": "财务净收益/费用",
  "period": "2025-H1",
  "quantity_ref": {"table": "profit_bridge", "row_key": "finance_net", "column": "contribution"},
  "disclosure_status": "qualitative",
  "status": "原文只给定性原因",
  "evidence": [{"document_id": "...", "report": "...", "page": 12, "quote": "原句，保留原文", "section": "管理层讨论与分析"}],
  "quantitative_limit": "原因已披露，但未披露该原因的独立贡献金额；算术利润桥不等于原因的定量归因",
  "search": {"searched_pages": [11,12], "preferred_pages": [11,12], "note": "检索的是本报告已解析原文；未命中不证明其他材料未披露"}
}
```

`disclosure_status` 固定三值：`quantitative` / `qualitative` / `not_stated`，中文分别为“原文给出定量原因” / “原文只给定性原因” / “原文未说明”。定量要求**原因自身**有金额、比例、数量等明确量化，不因同段含本期/上期金额就判定为定量原因。候选原句是管理层披露，不是程序证明的因果。来源保留 document_id 与 PDF 页；多个相关原因保留多条。检索缺页和报告期限制在 search 中明示，不把缺少定量桥写成原因未知。

每条 evidence 另含 matched_topic 与 relation（direct_driver / related_driver）；关联驱动解释不等于管理层直接解释了筛选阈值。alignment_note 明示这一边界。被重复披露的相同原句优先保留管理层讨论页，其他页在 corroborating_pages 中保留。

`quantity_ref` 指向现有 A1 表；没有可用金额时仍保留原因检索与缺失说明。`drivers_evidence` 表继续作为可读交付；顶层数组是组合器使用的结构化版本。

## signal_followups[]

```json
{
  "key": "2025-H1_cash_conversion",
  "signal_ref": {"table": "signals", "row_key": "2025-H1_cash_conversion"},
  "management_explanation": {"disclosure_status": "qualitative", "status": "原文只给定性原因", "evidence": [], "quantitative_limit": "...", "search": {}},
  "alternative_explanations": [{"hypothesis": "季节性备货占用现金", "status": "candidate_not_evidence", "test": "核对同季库存、销售与次期去化", "tracking_metrics": ["存货周转天数", "经营现金流"]}],
  "persistence": {"sample_periods": ["2025-H1","2024-H1"], "known_sample_count": 2, "triggered_periods": ["2025-H1"], "missing_periods": [], "allow_continuous_claim": false, "summary": "仅有2期可比样本，不足以判断持续性"},
  "tracking_metrics": ["经营现金流/合并净利润", "应收回款", "存货周转天数"]
}
```

替代解释按信号类型生成，是待检验候选，不冒充公司事实。持续性统计同一信号**实际可计算**的可比观察期，不把两期作差当作两次异常，也不把全部报表年份当作全部信号样本。样本不足三期时 `allow_continuous_claim=false`，生成描述不用“连续”。样本够三期也须同窗口相邻、无缺值且同一条件反复成立，才能允许对应的持续性表述。未触发/未知不生成追问。

## answer_constraints[]

```json
{
  "id": "reference_gaps_CNY_money:record-id:comparison_basis_unaligned",
  "code": "comparison_basis_unaligned",
  "subject": {"table": "reference_gaps_CNY_money", "row_key": "record-id", "columns": ["forecast","actual","difference","difference_rate"], "record_ids": ["record-id"], "metric": "revenue", "period": "2024-FY"},
  "issues": [{"dimension": "scope", "status": "unknown", "detail": "预测合并范围未明确"}],
  "prohibited_uses": ["same_basis_error", "forecast_accuracy_ranking", "beat_miss_conclusion"],
  "allowed_uses": ["quoted_source_value", "qualified_numeric_reference"],
  "message": "这两个数不能作为同口径误差；只允许明确标注口径未齐的数值参照",
  "evidence": []
}
```

另有 `profit_attribution_unknown`，禁止 `label_as_parent_profit` / `parent_profit_comparison`；`comparison_basis_unaligned` 用于期间、范围、经济维度、收入边界、每股、重述等未齐。数值缺失与口径未齐分别记录，缺失不能证明口径相同。机器字段直接伴随对应数值/来源，主线交付检查按 `subject` 及 `prohibited_uses` 使用；N4 不实现答案扫描或重试。已可比项目不被无关约束阻断。

comparison 的同一列对适用多行时，subject.row_key 为 `*`，同时必须提供明确的 `row_keys[]`；适配器只展开所列行，避免无限通配。它的禁止用途为 same_basis_comparison / same_basis_error / unqualified_cross_period_growth。跨口径预测版本另禁止 same_basis_revision。前值利润归属未明、后值明确归母时，禁止改标的约束只覆盖 previous 单元格及前值记录；整对另带禁止跨归属比较的约束，不能误伤后值已经明确的归母标签。

## 工作记录与验收计划

- 已确认：全部主要驱动项检索原文；每个触发信号四项追问；口径约束必须进入工具结果，不能只留中文脚注。
- 拒绝：把任意带数字段落认作定量原因；用两期异常断言长期趋势；利润归属不明时改标归母；关键词命中即认定经济因果。
- 验收：卡罗特中报 PDF p11–12、p14；伊利至少5处人工核对；构造误匹配/缺页/时期/口径样例；单测及真实隔离底稿交付，无模型付费调用。
- 对接状态：已读取并接受 N2 的函数/输出契约并提供适配器；未直接连接 N2 会话，尚无 N2 端合并回执。独立分支不合并、不部署；主线需要在收集工具结果时承接 answer_constraints，并在流水线提供 comparison/expectations report 时承接 comparability_constraints。尚未执行宿主答案修复或正式盲评。

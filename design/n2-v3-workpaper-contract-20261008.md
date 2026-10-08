# v3 底稿流水线契约 v1（N2 → 主线 / N4）

基线 328b8e2；分支 feat/v3-workpaper-pipeline。只做 P0.1/P0.2 和 P1.0 服务端；不合并、不部署，不读取 held-out 内容。N3 的维度语义与提交规范化继续独立实现，不在本分支复制其规则。

## 入口（主线宿主调用）

`financial_workpaper(project_id, kind="analysis_pipeline", document_id?, company?, scope="consolidated", periods?, focus?)`

复用现有包络 `status/data/source_refs/warnings`。支持部分入库文档；只读、无 LLM。成功或局部未齐返回 `data.context`（给模型），`data.numeric_tables`（只给宿主，登记 A1），`data.handle`（完整表）。主线先登记数值表，再仅注入 context。失败/歧义的包络 status 为 insufficient_evidence，同时 data.context.status=selection_required、selection 保留候选和可直接重调的参数；宿主可注入这个 context。局部缺项的包络仍为 ok，context.status=partial。

`context` 字段：

```json
{
  "schema_version": "workpaper-pipeline-v1",
  "status": "ready | partial | selection_required",
  "selection": {"company": "", "document_id": "", "scope": "", "periods": [], "basis": []},
  "key_metrics": [],
  "bridges": {"profit": {"table":"variance_profit_bridge","columns":[],"rows":[]}, "cash": []},
  "major_changes": [],
  "triggered_signals": [],
  "management_evidence": [],
  "signal_followups": [],
  "comparability_constraints": [],
  "missing": [],
  "source_evidence": {"table":"variance_drivers_evidence","rows":0,"basis":""},
  "full_tables": {"handle": "", "tables": {}, "read": {}},
  "extensions": {"management_evidence": "pending", "signal_followups": "pending", "comparability_constraints": "pending"}
}
```

数值项使用 `ref="表名.行键.列名"` 加紧凑展示值/单位；不会将完整来源链多次注入。A1 表保存精确值与完整证据。摘要按业务项目选取，不按字符预算截掉缺项；按表汇总缺项数量；每格具体原因在 pipeline_gaps 和该格 evidence，关键值缺失时原因同时内联。利润桥/现金桥按 table + columns + rows 传输展示矩阵；数值列的 A1 引用仍是 table.key.column。major_changes 为已知利润步骤绝对金额前三项的引用，完整步骤均保留，不宣称这些贡献证明因果。

完整表按需读：`financial_workpaper(project_id, kind="read_table", read={"handle": "交付 ID", "table": "表名", "offset": 0, "limit": 50})`。返回总行数、next_offset、精确单元格与对应证据；不返回其他项目内容。handle 是现有项目隔离的交付目录标识，不新增主库表。

## P0.1 可行动歧义

`data.selection` 包含 `reason`、`candidates[]`（主体、文档、事实数、可用期间、口径）、`retry_calls[]`（tool + arguments + 一行调用串）。没有唯一证据时不任取。文档档案报告主体、明确主体别名、同一报告合并口径、已披露起止日期足以定位时自动选择，selection.basis 保留依据。原表不存在或单位/列头不明时明确指出，而不写“先完整入库”作为唯一出路。

## N4 扩展约定（预留接口，请在独立模块实现）

建议公共函数：`enrich_workpaper_context(service, project_id, *, selection, reports, context) -> dict`，位置 `service/workpaper_depth.py`。`reports` 为 `statement_analysis / variance_attribution / anomaly_signals` 的完整已编译 report；N4 返回下面三字段和相应 extensions 状态，不修改 N2 的选择、直读及流水线函数。N2 基础版本保留现有 variance 原文候选，扩展缺席时写 pending，不能说“原文未说明”。

- `management_evidence[]`: `{id, metric, period, linked_refs[], status, quotes:[{document_id,page,quote}], quantitative_gap?}`。status 使用 `qualitative_disclosed / quantified / no_statement_found / not_searched`。
- `signal_followups[]`: `{signal_key, management_evidence_ids[], alternatives:[{text, status:"hypothesis"}], persistence:{periods:[],sample_count,assessment}, tracking_metrics:[]}`。
- `comparability_constraints[]`: `{id, kind, affected_refs[], status:"unaligned|unknown", reason, forbidden_claims:[], required_qualification, evidence:[]}`。主线接答案约束；N2 不代替模型推断归因。

扩展在文件和函数到位后调用；未合并时明确 `pending`。保持现有原文信息，不凭空补解释或猜未齐原因。

## 验收计划与边界

五类底稿按现有开发回放口径：statement_analysis、comparison、period_analysis、variance_attribution、anomaly_signals；每类加流水线，覆盖伊利/海尔/卡罗特/茅台/瑞和。构造多主体、集团/母公司、非标准日期区间、重述比较列及部分入库原表样例。记录每类关键数、缺项原因、直读来源和紧凑/完整 JSON 字节数；使用本地 o200k_base 实测文本 token（并明确不是供应商账单或未知模型真实 tokenizer）。真实对照的总输入与质量由主线/N1 门槛评测验证，本分支不据摘要体积宣称金融组成本胜出。

## 实现与主线接入注意

- 五类表名均加前缀：statement_ / variance_ / signals_；A1 按返回的完整 numeric_tables 登记，不能再按模型摘要回填数值。将 data.context 序列化一次给模型即可，勿同时注入 report、numeric_tables、source_refs 或交付文件清单。
- 已有金融配置允许 financial_workpaper；服务端新增两个 kind 和 read 参数，无需新增工具。自动识别财报请求、调用时机、数值表宿主登记、报告包/回答注入由主线完成，本分支不修改 server/。
- N4 函数只在 service.workpaper_depth 模块存在时调用；返回 management_evidence / signal_followups / comparability_constraints / extensions 中实现的字段。异常原样抛出，不吞掉扩展失败。reports 是完整已编译子报告、原表名未加前缀；context/A1 名已加前缀。N4 生成 linked_refs 时需使用相应前缀。
- 原表直读复用 standard_metrics / cleaning_rules / semantic.materialize / source_semantics。只处理明确归属和单位/期间的三大主表；不补零，不改库。source_ref.source_method=原表直读；table-read: 开头的 fact_id 是本次底稿内的临时来源格标识，不能当作已入库 fact_id 调查询工具，完整证据通过句柄或 get_source_table 读取。
- 未识别行、期间、单位保留原文/坐标到 source_gaps 和 pipeline_gaps。原始与重述记录都保留；比较计算优先显式调整后列，源格带 normalization.restatement 和 column_label。会计框架不能由 A+H 名称推断一致。
- 主线已在 v3-host-contract-ack-20261008.md 确认 context / numeric_tables / handle 及 read_table 契约；read_table 复用 delivery_manifest / delivery_path，遵守 evaluation.isolation_key，同键可读，越界与不存在同样返回。N4 尚未交付扩展模块，三项扩展为 pending；这不是“没有管理层说明”。

- 对纵向合并单元格，geometry_rows 用既有 PDF 字坐标将标准行名与数值横向对齐，materialize 再核验原格 numeric_span；不按数值出现序号猜行名。标签换行未能确定时保留未识别。
- 原表补齐时若发现存量事实的框架后缀与同一份报告明确声明的框架冲突，底稿视图按原文统一，selection.basis 保留前后口径和原句，单格 record_scope 保留旧标记，不改主库；若调用明确指定了相反框架，则返回带候选的不足证据，不静默改参数。多份 A+H 报告仍不合并。

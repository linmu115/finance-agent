# N2 v3 底稿侧第一批交付与验收（2026-10-08）

基线 `328b8e2`，分支 `feat/v3-workpaper-pipeline`。本轮落实 P0.1、P0.2、P1.0 服务端，未合并、未部署。入口和 N4 预留字段见 [契约](n2-v3-workpaper-contract-20261008.md)；主线已在 worktree 的 `v3-host-contract-ack-20261008.md` 确认契约，回执原文件保留、不纳入本提交。

## 实现结果

- P0.1：主体/报告/会计框架/期间不足时返回候选、事实数、原标签、可用期间、币种、口径和 `retry_calls`。文档档案主体、已披露起止日期和默认合并口径足够时自动决定并保留依据。陌生期间行保留为未识别，不使其余项目失败；显式调整后比较列优先，原报数仍在来源中。
- P0.2：标准三大主表按 `standard_metrics` 复用既有确定性映射、单位、期间和源格解析。部分入库/零结构化事实均可直读，带 `source_method=原表直读`、页/表/行/列/原值。纵向合并单元格用 PDF 字坐标将已识别标准标签与金额横向对齐，保留原格 numeric_span 和标签/金额 bbox；不按行序猜标签。
- 同份报告出现新取数的原文框架与存量事实标签冲突时，仅在底稿视图中按原文统一，保留 `record_scope`、原句和选择依据。明确请求不同框架则给候选；不把多份 A+H 报告合并，不写原库。
- P1.0：`analysis_pipeline` 复用一份 AnalystData 组合 statement_analysis、variance_attribution、anomaly_signals；返回 compact context、宿主用 numeric_tables 和完整表 handle。利润/现金桥、主要贡献、触发信号、来源证据表和逐格缺项原因均保留。`read_table` 分页读完整表，复用 delivery manifest 的项目及 `evaluation.isolation_key` 约束，越界与不存在同样返回。
- 关键值带精确 A1 ref；bridge 用展示矩阵避免反复嵌入来源链。完整表采用 `statement_ / variance_ / signals_` 前缀。主线仅注入 context，不能把 report、numeric_tables 和 source_refs 也注入。

## 数据与验收

当前库复制到 `.tmp/v3-workpapers/finance.sqlite`，所有查询使用 mode=ro。只查询授权的伊利、海尔、卡罗特、瑞和 document_id。茅台不在当前库，复制本地已有 `贵州茅台2024年年度报告.pdf`，在临时库保存 143 页、275 原表、**0 条事实**，未主库入库、未调用模型。运行依赖复用 worktree 已有的主目录 .venv/node_modules 联接；tokenizer 单独装到 `.tmp/v3-workpapers/tokenizer`，未修改共享依赖。

每家公司分别运行 statement_analysis、comparison、period_analysis、variance_attribution、anomaly_signals、analysis_pipeline，**30/30 产出结果**。所有流水线 context 为 partial，局部缺失及不可算项均在 `pipeline_gaps` 中，不能把产出成功读成全部项目齐备。

| 材料 | 六条路径 | 已触发信号 | context UTF-8 字节 | context token | 原三工具模型响应 token 合计 | 流水线秒 |
|---|---:|---:|---:|---:|---:|---:|
| 伊利 | 6/6 | 9 | 13,342 | 3,899 | 53,419 | 20.812 |
| 海尔 | 6/6 | 1 | 12,340 | 3,557 | 56,980 | 22.438 |
| 卡罗特 | 6/6 | 6 | 12,866 | 3,777 | 37,168 | 3.766 |
| 瑞和 | 6/6 | 6 | 12,863 | 3,781 | 33,374 | 4.078 |
| 茅台 | 6/6 | 3 | 12,258 | 3,526 | 36,367 | 12.266 |

使用本地 `o200k_base` 对紧凑 JSON 实测。原三工具比较口径为本分支单独调用 K1/归因/信号后的既有 model-context 形状（去掉 report/numeric_tables，保留其它字段及 source_refs）；只比较同三种能力的工具响应体。context token 减少 **88.67%–93.76%**，这不是整轮 LLM 总输入/费用或相对 prepared 的正式优势结论。完整管线响应仍约 3.88–7.38 MB，由宿主处理，不可直接塞给模型。N4 扩展尚未并入，扩展后须重测体积。

- 财务结果：伊利、海尔、卡罗特、瑞和的利润桥四个检查点残差为零；五家公司现金桥残差均为零。茅台利润桥四个阶段延续同一 **8,346,828.30 元**未解释差额，非四项相加。原 PDF63 的利息支出减少 8,372,327.90 元、手续费及佣金支出增加 25,499.60 元，其净影响恰等于该差额。当前通用利润桥未列入这两个营业总成本项目，残差和原因保留，未强制配平。
- 茅台原表直读 **52 个披露数**与实际打开的 PDF63/64/67/68 原页一致（收入/成本/费用/税/合并与归母利润/CFO/CFI/CFF/现金余额），全部带原格坐标。期初现金、汇兑方向和上期比较列一并覆盖。
- 故意在内存中移除四家公司全部 revenue 别名记录：伊利、海尔、卡罗特、瑞和的本期及比较期收入 **8/8 恢复**，均是原表直读；没有对 SQLite 做删改。瑞和覆盖纵向合并格；卡罗特同时覆盖存量 IFRS 标签与原文 HKFRS 不一致的只读视图处理。
- **122 项相关 Python 测试通过**，其中新增 16 项构造测试：多主体/A+H、集团与母公司、非标准日期、仅时点的流量、合并表头重述列、零事实原表、缺单位、原框架冲突、几何对齐、A1引用、分页、项目隔离及评测隔离。最后对新增 16 项另做一次定向复核，均通过。
- 验收人工初次转录有 4 处数字误写（2023 所得税、合并利润、少数损益、CFI）；断言捕获后重新打开原页核对，修正的是验收期望。程序取数和源数据未为这些错误调整。

## 缺项、偏差与交接

1. 主线宿主的财报请求识别、自动预调用和 A1 注册/注入由主线接入，本分支提供可调用服务契约；金融配置已有 financial_workpaper 工具，新 kind 无需新增工具名。本分支不改 server/。
2. N4 的 management_evidence、signal_followups、comparability_constraints 留空并标记 pending；模块到位后自动调用约定函数。现有归因原文候选保存在 `variance_drivers_evidence`，没有把 pending 写成“原文没有说明”。
3. 海尔部分扣非等记录仍受当前 dimensions_ok 的 financial_item 维度过滤影响；N3 负责的维度语义未在本分支复制。三大表直读不扩展到所有摘要/附注，披露 ROE/扣非等依赖尚未入库或现有附注适配的项目仍可能缺失。期初余额不足、中报没有年度季度表、量价或账龄原表不足，均保留明确原因；完整清单按公司见 missing.json。
4. 复杂合并格若缺 PDF 字坐标或标签不能唯一匹配，则保留未识别原文和位置，不按金额序列猜行名。相同源格已有有效事实时不以兜底重写其数值。
5. 本轮未测新 held-out 的题目/数值或正式模型质量。仅查阅获准的脱敏机制统计；没有读取青岛啤酒或其它 held-out 内容。没有主目录写入、3001/新端口/Docker 操作，模型调用数与主库写入均为 0。

## 可复验文件

- [结果摘要](../docs/evidence/n2-v3-workpapers/summary.json)、[体积实测](../docs/evidence/n2-v3-workpapers/tokens.json)、[关键数与桥](../docs/evidence/n2-v3-workpapers/key-tables.json)
- [52 个原页核对](../docs/evidence/n2-v3-workpapers/moutai-52-pdf-checks.json)、[移除事实后的 8 个恢复值](../docs/evidence/n2-v3-workpapers/partial-ingestion-revenue.json)
- `docs/evidence/n2-v3-workpapers/{yili,haier,carote,ruihe,moutai}/context.json` 与 `missing.json`
- 完整 30 个结果和交付目录在 `.tmp/v3-workpapers/final/` 与 `.tmp/v3-workpapers/deliveries/`，不把源 PDF/数据库提交入 Git。

```powershell
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay_v3_workpapers.py --snapshot .tmp/v3-workpapers/finance.sqlite --out .tmp/v3-workpapers/final
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/verify_v3_workpapers.py --snapshot .tmp/v3-workpapers/finance.sqlite --replay .tmp/v3-workpapers/final --out docs/evidence/n2-v3-workpapers --tokenizer-path .tmp/v3-workpapers/tokenizer
```

重放前须由调用者准备授权材料的临时只读数据库；不得把命令的 snapshot 指向主库。茅台临时零事实库的准备参数见 replay 脚本 `--moutai-pdf`。本分支的开发回放不是正式盲评。

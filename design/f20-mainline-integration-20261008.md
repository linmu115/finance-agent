# F2.0 主线集成：已批准范围与待执行记录

## 当前状态

main / 3001 基线为 F1.5 `328b8e2`。开发在 `feat/f20-integration` 独立 worktree 进行；先集成、验收，再将最终结果合入 main 并按协调流程上线。没有取消或重启任何生产运行。

original_pi 已完成并提交 `b6a45ce73a23c7ba6d8b0c760874a741e1142132`，分支基于 P2 `e07cd6a`。验收和实际模型请求/挂载捕获在该分支 `docs/evidence/original-pi-20261008/`。

用户已批准新的合并顺序：

1. N3 `feat/harness-v3-ingestion` 最终提交 `69b3758`（含 `8691dcf`、政策文字表、派生比较列）；用户已明确指定。
2. N2 `bdabf2f`：P0.1/P0.2、analysis_pipeline/read_table。
3. N4 `61f9522`：P1.2/P1.4/P1.5 底稿字段和 N2 适配器。
4. P2 `e07cd6a`。
5. original_pi `b6a45ce`。
6. P1.0 宿主集成和 P1.3 三层解释指导。P3 留到门槛检查以后。

每一步完成相关回归后记录 commit。用户已提供全部最终提交并授权开始；本轮按此序列实施。暂停生产仍须先告知时间点，等协调者通知 N1/N3 完成。

## 已核对的集成契约

- N2 `financial_workpaper(kind=analysis_pipeline)` 返回 `context / numeric_tables / handle`。只把 compact context 给模型，完整 numeric_tables 登记 A1，完整结果留宿主和审计；不能把约数 MB 的 report/来源链同时注入。
- 只在 financial 财报分析请求的首轮模型推理前执行。prepared/original_pi 不调用，不注入、不登记其表；普通产品原有入库保留。局部缺失与 selection_required 注入原始原因和可行动候选；异常保留错误但不阻断回答。
- N4 `enrich_workpaper_context` 在模块存在时由 N2 调用。验收要确认 management_evidence、signal_followups 实际进入 context，不能停留在 pending。当前基础流水线没有 comparison/expectations；其 comparability_constraints=not_provided 必须如实保留，不解释为口径已齐。手动相关底稿返回 answer_constraints，宿主需承接。
- N2 context.full_tables.read.arguments 与候选 retry.arguments 目前含 project_id，而模型的所有工具都禁止传 project_id。合并时去掉模型可见示例中的绑定项目参数，服务内部参数与项目隔离保持。
- 三层解释指导：披露事实（原句/页码）→ 量化影响（缺什么就说明）→ 推论；区分“定性已披露、定量未披露”与“原文未说明”。持续性与口径约束沿用 N4 返回证据。
- original_pi 的固定 SHA 对应原生 system sections 中的配置 preamble，完整原生提示还含会话 cwd；最终 F2.0 捕获继续分别列出两类哈希，不改 Pi 来凑摘要。

## 零付费端到端验收

使用授权的伊利、海尔、卡罗特开发资料复制库及合成 provider 响应，通过实际 RunManager/原生 Pi/MCP 路径捕获：流水线在首轮推理前完成，context 注入一次且表在 A1 可解析；N4 字段被消费；prepared/original_pi 不获得金融层。三组实际可见提示、schema、挂载与能力矩阵分别存档。复制库分析不写主库，不读取白云机场/青岛啤酒等 held-out 内容。

## 部署与重新应用边界

部署版本 F2.0。先告知协调者预计暂停时间，待其通知 N3/N1；之后在提交边界只取消指定的伊利、海尔、白云机场入库，确认无悬挂后续和全局活动运行后统一构建、重启 3001 一次。不能将单纯等待视作协调完成。

重启后通过产品既有 reapply_document_facts 对伊利、海尔、卡罗特应用 v3 规则，记录实际变化/历史/幂等结果；白云机场由 N1 在冻结前协调，不自行读取或重新应用。完整交接后由 N1 做 18 回合门槛检查；这里不运行付费评测、不宣称胜出。

## 本轮确定性结果

指定五个分支已按序合并并通过相关回归，P1.0/P1.3 与 N4 约束承接已实现。详细日志、三组实际请求捕获、复制库重应用差异见 `docs/evidence/f20-integration-20261008/README.md`。发现并解决 pipeline 的 report/numeric_tables 及 MCP 文本重复导致的 10 MB 传输失败，保留完整表并传一次，不截断。三家公司九次原生回放均完成；金融 context 为 8,949–14,194 粗估 token，成本门槛尚未检验，P3 未实施。

当前只在集成分支，main/3001 仍为 F1.5。遵照用户要求，提交验收完成后先通知暂停时间，再等待 N1/N3 协调确认；确认前不切主目录、不取消、不重启、不重新应用主库。

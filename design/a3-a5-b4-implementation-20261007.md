# 本轮实施：A3/A5 合并与批准的 B4

用户已授权按顺序合并 feat/charts-consistency（A3 bf35d55、A5 21718d3），验收并先回报合并提交，再实施 B4。A3 必须在两组沙箱启动中生效；A5 只用于评测/离线，不接入回答、不向模型或用户提示。

B4 以已批准的候选为基础：末尾补简短答复方式；删除自绘图检查标签/色条/对比度句，保留图形语义；共享工具说明明确回答占位符、整表嵌入、params 和 get_artifact；底稿入口只描述当前 K1/K3。合并后拍摄原生 Pi 的前/后快照，保持工具和 schema 结构，做 K1/B2/params/edits/绑定确定性验收，无付费调用。

3001 仅最后确认空闲后重启一次。Docker/WSL 持续共享运行；已停用的 Dify/mineru 不操作。N2 A 股适配、N3 feat/ingestion-scale 等待用户后续通知，不提前合并；不读取 held-out 材料。保留其他会话的未提交文件。

## 已完成：A3/A5

合并提交 `c057c52bad4d5710d81a02bbb630e2385beae753`，已在 B4 开工前回报。两个冲突保留双方功能：数值表收集同时排除 scenario_bindings.json 与 plot_diagnostics.json；分析结果同时保留 scenario_context 与 plot_diagnostics。

A3 两组真实 Docker 启动均验证 constrained 布局与深色单元白字，底层数组逐项不变。相关 Python 24 项、绘图运行时 9 项通过，均无跳过。A5 在运行时没有入口或调用，仅离线脚本和测试使用，feedback_enabled=false。未重跑 N2 已做的全历史图；保留其 4 图共 8 个报告遮挡及另 1 个目视轴线问题、A5 严格正确样本误报 119/2592（4.59%）的边界。详见 [合并验收](../docs/evidence/a3-a5-b4-20261007/merge-validation.json)。

## B4 实施与诊断更正

批准的指导与工具描述已直接写入生产定义，无描述替换适配层。金融指导按 statement_analysis → 财务解释、dcf_fcf → 估值、overrides/params → 更新的任务路径组织；末尾补入结论与关键数值、驱动因素及实质缺失的答复方式。移除 A3 接管的图形布局检查文字，保留柱形零基准、缺失留空及单位期间语义。底稿入口只描述当前 K1/K3，不预告未合并的 A 股功能。

两组共享 run_analysis/get_analysis_status 说明包含聊天单值占位符、整表嵌入、params、edits 和 get_artifact。prepared 原生 Pi 快照确实可见这些入口；金融 39 个工具、prepared 13 个工具，工具顺序与除 description 外的完整参数结构逐字段一致。financial_workpaper 仍仅金融可见；A5 没有加入任一配置的工具。

**修正上一轮“七处不一致”中的两处判断：**原始宿主结果没有 analysis.model_refs，且使用 delivery.files；但 server/model-context.ts 会向模型投影 analysis.model_refs 和 delivery.delivered_to_user，真实模型看到的这两个入口有效。因此保留该正确接口，不要求模型拼接引用，不将模型提示改成 raw API 字段。集成测试验证 model_refs 的 artifact/revision 与保存版本一致、delivered_to_user 与真实文件名一致。确需修改的是“run_analysis 只能画图/成文”的限制，现明确保留自由计算。原方案与证据存档不重算，已加更正指向本记录。

## 合并后重新测量

前后均实际创建隔离空默认项目的原生 Pi 会话，读取 session.systemPrompt 与 agent.state.tools，没有模型推理。字符为 Unicode 码点；粗估 token = ceil(ASCII/4 + 非 ASCII)。这不是 tokenizer 或账单结果，未校准估算误差。完整上下文包含系统和紧凑 JSON 工具 schema；不含供应商传输封装、用户问题、历史、动态工具返回。按需技能全文与单独路由请求不冒充初始上下文收益。

| 配置/部分 | 改前字符 | 改后字符 | 改前粗估 token | 改后粗估 token |
|---|---:|---:|---:|---:|
| prepared 系统 | 813 | 550 | 507 | 370 |
| prepared 工具 description | 5,928 | 2,520 | 1,500 | 909 |
| prepared schema description | 0 | 0 | 0 | 0 |
| prepared 说明文字合计 | 6,741 | 3,070 | 2,006 | 1,279 |
| prepared 完整上下文 | 12,832 | 9,148 | 3,529 | 2,798 |
| financial 系统 | 7,473 | 2,384 | 5,385 | 1,695 |
| financial 工具 description | 14,549 | 6,778 | 4,707 | 2,479 |
| financial schema description | 624 | 405 | 473 | 255 |
| financial 说明文字合计 | 22,646 | 9,567 | 10,565 | 4,429 |
| financial 完整上下文 | 42,080 | 28,968 | 15,423 | 9,279 |

完整上下文：金融字符减少 **31.16%**、粗估 token 减少 **39.84%**；prepared 分别减少 **28.71% / 20.71%**。最终比原候选稍长，来自用户补充的答复方式、共享入口完整描述和上述接口更正。金融仍达到字符减少 30% 以上目标；不以长度变化宣称真实质量或费用改善。

原始 [before-context.json](../docs/evidence/a3-a5-b4-20261007/before-context.json)、[after-context.json](../docs/evidence/a3-a5-b4-20261007/after-context.json) 及 [逐工具/逐字段测量](../docs/evidence/a3-a5-b4-20261007/b4-measurements.json) 可复核。

## 确定性验收与边界

- 类型检查、生产构建通过；构建保留既有大 chunk 警告。
- Python 42 项通过：prepared 来源、K1 财务底稿、B2 dcf_fcf、analysis 接口/参数及显示加总；绘图和 A5 的 33 项已在合并时另验。
- 宿主/Pi 6 文件 9 项最终均通过。首次 8 通过、1 失败：model-delivery-flow 测试辅助 CSV 解析器按 LF 分行，Windows 合法 CRLF 令最后列键变成 after\r，row.after 得到 undefined。仅修复测试解析器后定向重跑该 1 项通过，未改 CSV 输出或计算，原失败保留在验收记录。
- 两组实际 Docker 各 3 次（基准、params 情景、edits 修复）：10 → 11 → 22；更新后基准 10 与情景 11 均可绑定，对比表成功嵌入；修复后单值/整表均为 22，get_artifact 读取原 CSV 为 22.0。详见 [共享路径证据](../docs/evidence/a3-a5-b4-20261007/b4-shared-paths.json)。
- 无付费调用、无新真实模型冒烟，不读取 held-out 入库内容或答案。确定性接口通畅不能证明模型采用率或优于通用基线，正式对照仍由 N1 执行。

3001 的最终空闲检查、一次重启和健康状态另见环境记录；Docker/WSL 保持运行，12 个已停止且 restart=no 的 Dify/mineru 容器不操作。N2 A 股适配与 N3 入库分支仍待通知合并。

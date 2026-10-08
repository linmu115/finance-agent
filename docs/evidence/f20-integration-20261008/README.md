# F2.0 候选集成验收（尚未部署）

按批准顺序在 `feat/f20-integration` 集成。3001 仍为 F1.5 `328b8e2` / PID 69528；本轮没有取消生产任务、重启、写主库、启动 Docker 或调用付费模型。主目录切换也留到三份入库暂停后，避免运行中的 Python 从已更新工作树加载不同版本。

## 提交与相关验证

|步骤|合并提交|结果|
|---|---|---|
|N3 69b3758|a5d9183|56 Python、10 Node 通过|
|N2 bdabf2f|eda8457|53 Python 主回归、19 期间回归通过|
|N4 61f9522|c612191|64 Python、5 Node 通过；流水线深度扩展已实际 ready|
|P2 e07cd6a|bbe4be6|12 Node（含原生 7 场景）、17 Python 通过|
|original_pi b6a45ce|3db91af|4 Node、4 Python 通过；历史提示及十工具契约一致|
|P1.0/P1.3、交叉修复|见包含本文的集成分支历史|最终 35 Python 通过；宿主相关 24 个不同 Node 测试最终通过（含约束 2 项）；类型检查、构建通过|

各阶段有重复覆盖，不把它们相加成独立测试总数。`host-final-node.txt` 最初有 1 个旧表标题断言失败；N4 已将“驱动因素原文”改为“管理层解释对齐”，更新断言后 `host-chapter-final.txt` 验证 MD/PDF/Excel 章节和来源通过。`n3-python.txt`、`n2-python.txt` 保留最初错误模块名的 ImportError，正确模块的完整结果分别见 `n3-contracts.txt`、`n2-final.txt` 和 `n2-periods.txt`。最终宿主专项见 `host-final.txt`，真实资料回放见 `host-real-replay-final.txt`。

## 实际原生回放与能力矩阵

`native-host-replay.json`：伊利、海尔、卡罗特 × original_pi / prepared / financial，**9/9 completed**。使用实际 RunManager、Pi 原生主循环、MCP stdio、A1 和持久审计；provider 用合成响应，未调用模型或开启 HTTP 服务。三家公司请求均为 `documentIds: []`、`analysis_only: true`、独立 isolation_key。金融底稿在第一次 provider 请求（包括路由）前生成；非金融两组零流水线调用、无 context。A1 直接绑定宿主表，报告包 snapshot 与完整 numeric_tables 一致。

|能力|original_pi|prepared|financial|
|---|---|---|---|
|可见工具数（analysis_only）|10|13|32|
|Pi、原文、沙箱、安全、文件下载、压缩、重试、审计|有|有|有|
|facts / research records|无|有|有|
|A0/A1/P2、语义标注与估值检查|无|有|有|
|金融资源、模型、底稿、宿主流水线|无|无|有|

original_pi / prepared 的完整模型工具 schema+description 与 `b6a45ce` 的离线捕获逐字一致，配置 preamble 亦一致。original_pi preamble SHA 为 `6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f`。完整系统提示还含原生 cwd，不能把不同路径引起的完整哈希变化误报为能力变化。三组工具和说明摘要详见 `validation.json`；原文/挂载/读取隔离另由 `test_original_pi` 回归验证。

金融注入使用 Pi 原生 context 变换，放在对应用户请求之后、后续工具和回答之前；每个模型视图只有一份，后续更新优先。完整结果留审计、附件与 A1；恢复从本运行审计取回，不让模型重新抄表。`tool_request/tool_result` 的 `origin: host_precompute` 区分宿主预计算与模型主动采用；`workpaper_precompute` 留紧凑结果和用户消息 ID。预计算异常或选择歧义原样注入并继续回答，不冒充成功。

|公司|注入 context 字符|UTF-8 字节|粗估 token|
|---|---:|---:|---:|
|伊利|36,075|49,875|14,194|
|海尔|22,995|31,529|8,949|
|卡罗特|34,622|42,452|11,592|

口径：实际模型可见 `context` 的紧凑 JSON，Unicode 字符数；粗估 `ceil(ASCII/4 + 非 ASCII)`，不是模型 tokenizer 或计费用量。相比 N2 单独 3.5–3.9k 的初始估计，N4 原文与信号字段明显扩大 context。**本次未证明金融分析成本低于 prepared**；不提前做 P3 或裁掉必要证据，交 N1 门槛检查。

## 集成差异及实际发现

- N2/N3 重叠的重述优先选择统一用 N3 维度实现，并保留 N2 的 adjusted 语义；没有两套定义。N4 管理层证据、信号追问均 ready；基础流水线未运行 comparison/expectations，其约束状态仍为 not_provided。
- 模型工具已绑定项目，N2 示例中的 project_id 会被拒绝：只在模型投影去除它并重生成示例调用，服务端原始参数及项目/评测隔离保留。
- 首次真实回放撞到 MCP 单条 10 MB 限制，记录留在 `host-real-before-size-fix.txt`。伊利/海尔/卡罗特 Python 包络 data 分别约 8.32/9.57/7.22 MB，其中 report.tables 与 numeric_tables 重复；FastMCP 又将整个结构重复写进文本。现在只在线上传一份完整 numeric_tables，文本部分传紧凑 context；完整报告仍在交付目录。没有扩大 SDK 限制、截断表或加备用通道。
- P1.3 保留“披露→量化→推论”、两种未知、样本期数和口径限制。N4 明确约束随同一数值表登记；对已绑定的受限单元格/整表写成归母、同口径误差或超预期等结论，复用 P2 一次修复与降级。否定句、未受限单元格、同名重跑更新均有回归。**它是对明确绑定的确定性检查，不是自由文字的完整语义裁判**。

## 复制库重应用与部署边界

快照时间 2026-10-08 23:35:23 +08:00；只读生产库，复制这三份开发文档及关联数据，无其他项目内容。未复制会话、凭据或生产运行。

|公司|快照事实数|修改 / 新增历史|重复修改|
|---|---:|---:|---:|
|伊利|2,755|125 / 125|0|
|海尔|2,755|107 / 107|0|
|卡罗特|732|732 / 732|0|

字段差异在 `reapply-field-diff.json`：值和期间未改变；伊利是指标规范化，海尔包含指标与来源语义。海尔原被误标扣非的 71,866,159,446.57 来自 t12/B3 的“营业收入”原行，本次归回 revenue。卡罗特全部 scope 从 consolidated_IFRS 改为 consolidated_HKFRS，依据文档自身 HKFRS 声明，另有 55 条指标规范化。历史完整保留。

这些是仍在入库期间截取的复制库数据，不能当成最终主库重应用条数承诺。部署前按协调信号在提交边界暂停伊利、海尔、白云机场，确认无后续和全局活动运行；再快进 main、构建并只重启一次。生产重应用仅伊利、海尔、卡罗特，并记录当时实际变化及历史。白云机场由协调者/N1 处理；未读 held-out 内容。Docker/WSL 继续共享，不操作已停用的 Dify/mineru 容器。

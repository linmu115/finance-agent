# original_pi：离线契约验收与 N1 交接

实现分支 `feat/original-pi`，基于 P2 `e07cd6a`；本次没有合并 main、部署、操作入库或调用付费模型。后续按协调者给定顺序合并，F2.0 时重新捕获三组最终接口；这里的 financial 尚未包含待合并的 N2/N4 流水线。

## 结论与边界

通过：显式 `evaluation.profile="original_pi"` 恢复 `db23e5b` 的原文型 generic v0.2 能力契约；当前 generic 保持不变。它仍是本项目历史 10 工具适配，并非上游 Pi CLI 的默认工具集合。

`native-request-capture.json` 来自真实 RunManager、Pi 原生会话、MCP stdio 与宿主审计；仅模型 provider 替换为脚本化响应，沙箱结果为合成值。捕获发生在宿主用量包装之内，使用 Pi 的 `normalizeContext/getCurrentSystemPrompt/getCurrentTools` 还原当前实际请求，不只读取静态配置。`sandbox-capture.json` 来自真实 FinanceService 导出路径，假 Runner 记录交给沙箱的文件字节和启动脚本。未执行 Docker 容器或远端模型，不证明金融质量、网络供应商序列化或正式评测成绩。

### 提示哈希口径

从原生请求中取得的 `preamble` SHA256 精确为：

`6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f`

历史审计的 `promptHash` 也是应用配置提示的摘要。当前 Pi 在请求中为三组共同追加会话专属 `<cwd>`；因此完整原生提示的 SHA 随会话路径变化，不能冒充上述固定 SHA。本次 original_pi 实际系统 sections **仅有 preamble 与 cwd**，无领域指导/资源。完整文字、原生完整哈希与配置哈希分别保存在请求捕获和 `summary.json`。没有为了凑固定哈希修改原生 Pi。

历史 10 个工具的签名、说明与字段约束从 `db23e5b:service/server.py` 提取，经当前 MCP 生成 schema，并经过当时宿主的项目参数隐藏。`scripts/check_original_pi_contract.py` 可重新核对：只编译旧函数签名及 docstring，函数体替换为空，不执行旧服务代码。`legacy-contract.json` 记录核对通过。

|能力/入口|original_pi|prepared|financial|
|---|---|---|---|
|本次 analysis_only 实际工具数|10|13|32（合并后重新拍快照）|
|原文页、原表、检索、Python、产物下载|有|有|有|
|facts / research_records 挂载|空数组，保留历史路径|共享准备记录|同 prepared|
|report/save_table、params/edits、get_artifact 内容分页|不提供|有|有|
|A1/P2 绑定、修复、语义标注、估值检查、标准报告包|不提供|有|有|
|领域资源、金融底稿/模型、finance_charts|不提供|不提供|有|
|金融宿主预计算|不进入；集成 P1.0 后须再次确认|不进入；同左|本快照尚待合并|
|Pi/模型配置、原生主循环、压缩、传输重试、项目/沙箱隔离、下载、审计|共同实现|共同实现|共同实现|

original_pi 工具顺序：prepare_document_sources、list_documents、get_document、get_document_index、get_source_page、get_source_table、search_evidence、run_analysis、get_analysis_status、get_artifact。其工具声明整体 SHA256 为 `e67785cc82164f505ad823d1c7f0cf4c0172eb24aa5024dddf67bacc49697f2f`（实际请求工具数组 JSON，含 description/parameters）。其他两组的完整接口和摘要在捕获文件中。

### 宿主及数据路径

- profile 经评测请求与可信 MCP `_meta` 传递；模型参数不能选择 profile、项目或分析资产挂载。普通请求没有这些元数据，维持原行为。
- original_pi 不加载领域资源与回答扩展，不登记数值表、不增加绑定表达式、不调用 render_answer。相同无效引用/估值回答在该组原样保留；P/F 一次修复后绑定 137 元，均正常交付。
- get_analysis_status 不从 CSV 自动生成数值表；get_artifact 保留历史的清单/校验/下载元数据，不开放模型/底稿交付 ID。跨 profile、跨隔离键、跨项目的分析运行均不可读；本链原版运行可读。用户自行生成 MD/CSV/PDF 的下载路径继续走共同项目/路径/hash 检查。
- 原页 segments、源表 row_source_refs、FTS/向量共用过滤器排除结构化摘录，保留原始内容。用合成原文 137 和结构化摘录 999 验证边界，不读取 held-out 材料。
- original_pi 的 `/input` 精确为 analysis.py、pages.json、tables.json、facts.json、research_records.json、plot_runtime.py。四个共同输入（原页/表、脚本、plot_runtime）在三组捕获中逐字节相同；未挂 A0/P2 SDK 和金融资产，未自动处理 analysis_report.json。保留基础绘图启动、执行代码留档。
- `analysis_only:true` 的 prepare 只复用已有原文视图；缺失时明确返回 analysis_sources_not_prepared。三组相同，不写冻结资料。普通 prepare 仍解析。
- 接通可信 scope 时发现 P2 的宿主 render_answer 位于工具 scope 外，现使其携带同一隔离键，避免附件检查绕过跨链隔离。这不改变普通产品行为；回归覆盖已通过。

## N1 调用

仍向 3001 的普通会话消息入口发送，使用新建会话；不能把旧 prepared/financial 会话改成 original_pi。示意：

```json
{
  "content": "题面由评测执行器填写",
  "documentIds": [],
  "evaluation": {
    "profile": "original_pi",
    "analysis_only": true,
    "isolation_key": "F2_gate_O_chain_r1",
    "budget_group_id": "F2_gate_O",
    "budget": {
      "max_model_calls": 100,
      "max_input_tokens": 1000000,
      "max_output_tokens": 100000,
      "max_total_tokens": 1100000,
      "max_wall_seconds": 900
    }
  }
}
```

预算仅为格式示例，以批准的评测预算为准，0 不是无限额。同链续题保持同一 profile、isolation_key；不同实验链换键。prepared/financial 仍传各自 profile，原文准备状态和预算口径按 N1 三组方案统一。正式启用等待 F2.0 部署及最终捕获。

## 验证记录

- 新增 Node 2/2：历史提示/接口，以及三组原生请求捕获、禁用入口、MCP 元数据、相同重试/用量审计；没有测试 HTTP 监听器。
- 相关 Node 集首跑 19/20；余下一项旧 analyst-delivery 断言仍期待估值缺失使回合失败，改成 P2 已批准的降级交付后，该项和 2 项原生压缩回归 3/3。合计 **24 个不同 Node 测试通过**。原压缩回归使用自带临时本机 mock provider，运行后关闭，无产品服务/付费调用。
- Python 24/24（本项、原文输入/准备、评测隔离）；额外绑定、报告、方向、研报、沙箱安全回归 61 项：59 通过、2 项 Windows 符号链接权限跳过。合计 **83 通过、2 跳过**。
- 旧 raw-input 清单测试补上 P2 已加入的 delivery_text.py，仅更新当前 generic 的预期；original_pi 明确不含此模块。
- 类型检查、构建、依赖完整性检查、git diff --check 通过；编译产物包含固定 JSON schema。构建保留已有的大 chunk 提醒；MCP 保留既有 Pydantic lifespan 注解警告。

完整日志、挂载捕获、接口捕获与公共实现摘要均在本目录。失败的旧断言首跑日志保留为 node-regression.txt，修订后结果见 node-regression-recheck.txt。

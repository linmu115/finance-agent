# 瞬时传输重试：离线交接

2026-10-08，独立分支 `feat/transport-retry`，基线 F1.2 `3df658fd56fbc075f340e2baba0015bd1d29fc01`。实现完成，未合并、未部署，评测结束后再决定。主目录仍在该基线；只读检查 3001 仍由 PID 84032 监听。本轮未暂停入库、重启服务、操作 Docker、写生产数据或读取 held-out 材料。

## 改动与依据

Pi 1.0.0 原生分类器不认识已发生的 `stream error: stream disconnected before completion: stream closed before response.completed`，且会无边界匹配 `500`。宿主现在只准许明确的流中断、暂时连接/TLS 错误、5xx 或 overloaded 进入原生重试；鉴权、额度、请求/业务错误和证书配置错误不进入。业务工具报错仍按原有工具处理。

使用 Pi 公开 `message_end` 扩展和 SettingsManager。Pi 漏识别的传输错误加 `Network error: ` 前缀，原始错误全文留在每次 model_usage 审计中；失败尝试保留在 native session，Pi 从下一次请求的模型投影中移除失败消息，成功工具结果继续保留。未修改依赖源码、工具说明、提示词或 schema。

同一模型步骤最多重试 3 次，等待 2/4/8 秒，随后失败报告。成功响应后按 Pi 原生规则重置；文档/入库的逻辑无推进继续由原机制独立判断。取消和评测预算优先。主循环 provider 隐式重试关闭，每次宿主可见尝试有独立 requestId 和用量结算；未知仍 unknown，清洗失败尝试仍归 cleaning 费用。

预算测试还发现 Pi 把 `aborted` 响应当作 retry success。宿主按实际取消/预算状态写 `success=false`，同时保留 `nativeSuccess`，不把停止包装成成功。

## 验收数据

| 合成场景 | 实际请求 | 安排重试 | 结果 |
|---|---:|---:|---|
| 已提交工具后，流中断、TLS 各一次 | 5 | 2 | 完成；提交只执行 1 次；5 次用量全部保留，其中 1 次 unknown |
| 流中断连续发生 | 4 | 3 | 2/4/8 秒后耗尽；保留原始错误；4 次 unknown，费用未记为免费 |
| 请求业务错误含 HTTP 500 文本 | 1 | 0 | 直接失败 |
| 上个回合业务错误后复用会话，再遇 503 | 2 | 1 | 完成；重试开关不遗留为禁用 |
| 模型调用预算为 2 | 2 | 2 | 第 3 次请求在发出前被预算阻止；没有虚增请求或用量；重试结束记为失败 |
| 退避期间用户取消 | 1 | 1 | 立即取消；无第二次请求 |

新增测试 3/3，通过分类、上下文溢出处理仍可用、上述完整宿主场景。相关回归 25/25，覆盖绑定、入库续跑、analysis_only、用量与重载、预算、路由、压缩。`npm run typecheck`、`npm run build` 和 `git diff --check` 通过。构建仍有既有大 chunk 提示，Python 启动仍有既有 Pydantic forward-reference 警告。

原始日志及按请求提取的审计在同目录：`targeted-tests.txt`、`regressions.txt`、`typecheck.txt`、`build.txt`、`validation.json`。测试期间曾有一个预算错误名断言写错，改为现有的 `evaluation_budget_exceeded:max_model_calls` 后复测通过；没有为测试改产品错误码。

## 验证边界与后续

- 只对本次实际故障所在的主模型循环扩展传输恢复；路由、旧 extraction 桥及摘要的既有重试策略没有扩展。上下文压缩仍交给 Pi，不被本次错误分类禁用。
- 新测试是内存 provider + native Pi + MCP stdio + 临时库，不监听 HTTP。已有的 3 项回归内部使用过临时 loopback provider mock，已随测试关闭；未开第二个产品服务。无付费调用，尚未做真实上游故障/长入库验收。
- 独立 worktree 最初的 node_modules junction 被既有依赖检查拒绝，已替换为本地物理副本后通过检查，未修改 main 依赖。没有跳过依赖检查。
- F1.3 是另一个待协调任务：等 N3 复制库验收与伊利阶段 B/计划暂停通知；暂停前先向协调者告知时间点，重启后只对伊利、海尔走 reapply_document_facts，青岛不重应用。本分支不应混进 F1.3。

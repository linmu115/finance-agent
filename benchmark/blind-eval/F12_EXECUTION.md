# F1.2 分析批次执行（2026-10-08）

最新协调指令批准 H1/H2 在 F1.2 重跑。阶段 A 保持 F1 原结果；该项目文档当时已完整入库，不受部分入库入口问题影响。F1.1 批次因宿主入库入口中止，F1.2 重跑；旧批次的请求、取消、用量、断点和已交付附件全部保留。

执行器为 `runner-f12.mjs` / `study-f12.mjs`，独立于已冻结的 F1/F1.1 文件。每个请求（含链内续题）的 `evaluation.analysis_only` 固定为 true；原 profile、预算、空 documentIds 和题面不变。新实验 UUID 生成新隔离键，H1→H2 同会话同键，其余组别、重复与题链独立。实际请求、run_config 开关和工具清单逐回合保存到 analysis-only-receipt.json，并与部署交接核对。

取消竞争修复直接针对此前出现的调度错误：轮询到 cancelled 后退出；重新调用或重启调度器时，如果批次中已有 cancelled 回合，禁止提交下一题。主动取消命令先写批次 STOP.json，再调用当前运行的标准取消接口；STOP 标记存在时不能自动恢复。失败与取消不同：普通 failed 仍按原规则阻断其依赖续题，其他独立链可继续；uncertain POST 不重复提交。

```powershell
node benchmark/blind-eval/runner-f12.mjs cancel blind-eval-F12-heldout-20261008 "停止原因"
```

取消后保存最终运行、会话、审计和资料摘要；不要把仍运行状态包装成已完成。不删除停止标记后接着跑剩余题；若获准重跑，另建批次并保留原账。

离线验证 `test-f12-heldout.mjs` 覆盖原顺序与题面、8 回合/4 条链、所有续题的开关、预算不变、取消后下一题和重启均停止、验证过程中收到停止不发 POST、未知用量、丢失响应不重发、父题失败和同会话依赖。没有真实 HTTP 或模型请求；回执在 `data/evaluation/blind-eval-heldout-reference-20261008/f12-scheduler-offline.json`。

H1/H2 青啤资料与 F1.1 开始时的冻结摘要一致，不重新应用入库规则。原准备冻结时 state=normalizing，F1.1 开始前重启后为 failed 的单字段变化已在旧批次显式记录；不能把本文理解为追溯宣称最早准备快照的全部字节不变。

阶段 B 等 F1.3 仅入库口径修复应用、N3 复核及协调方通知后再冻结资料。X7 等各自材料冻结与开跑通知。两者都必须使用 analysis_only=true；实际代码/进程另记，不能冒用 F1.2 的部署回执。伊利季度口径 unspecified、分部余额期间 FY，以及 t8 扣非等值口径 unspecified 的已知问题保留；是否已修以未来数据冻结证据为准。

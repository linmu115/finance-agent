# N1：评测成果隔离接口交接

本项已完成代码与离线验收，**尚未部署**。3001 仍运行 58a903c（PID 56120，2026-10-08 12:43:53 +08:00）。等主线合并 N4 adoption-fixes、N3 后续入库修复后，再统一构建并重启一次冻结 F1；不要在当前 3001 提前使用新字段。

## 请求用法

在原消息请求的 evaluation 中增加可选 `isolation_key`：

```json
{
  "content": "这里保持冻结题面原文",
  "documentIds": [],
  "evaluation": {
    "profile": "financial",
    "isolation_key": "F1_batchUUID_D2_financial_r1",
    "budget_group_id": "F1_D2_financial_r1",
    "budget": {
      "max_model_calls": 1000,
      "max_input_tokens": 50000000,
      "max_output_tokens": 2000000,
      "max_total_tokens": 52000000,
      "max_wall_seconds": 43200
    }
  }
}
```

发到原有 `POST /api/conversations/{id}/messages`。示例预算仅展示原接口形状，不是本轮付费执行或预算授权；正式预算沿用协调方已批准值。

- 键由执行器生成，1–120 个 ASCII 字母、数字、下划线或连字符。采用**本轮新生成的批次 UUID＋独立题链＋profile＋重复次序**，正式批次不要复用彩排键。未打键的所有历史模型、报告和运行产物对该范围不可见，无须克隆资料或清空项目。
- D2→D3 用同一个键；H1→H2 用同一个键。其他独立题、另一组、另一次重复使用不同键。键的命名不自动区分组别：两个请求故意传同一键，就是显式要求共享一条链；因此执行器应按上述映射分配。范围同时受原 project_id 限制。
- **同一会话每次 POST 都传相同键**，包括 steer/followUp；会话已有消息后改键、删键、或给原无键会话补键返回 `409 evaluation_conversation_isolation_conflict`，不追加消息、不启动模型。请新建独立会话开展另一条链。
- 同键的新会话可以读取本链已有成果，普通同会话续题还保留原生历史。重开会话、服务恢复、参数更新、修复重跑均保留归属。
- `budget_group_id` 仍只管预算：同一 profile、同一预算组可以容纳多个隔离键，不会因此共享成果。预算组原有 profile/限额一致性规则不变。实际请求键见 `GET /api/runs/{id}` 的 `request.evaluation.isolation_key`，会话为 `evaluationIsolationKey`；审计 `run_config.isolation_key` 保存同一值。预算汇总 `run.evaluation` 不承担链归属。

## 生效范围

| 对象/入口 | 带键运行 | 不带键的产品调用 |
|---|---|---|
| list_research_artifacts / read_research_artifact、指定 revision | 只列出/读取同键成果；其他键、无标记旧成果及不存在 ID 均视为不存在 | 仍按项目共享 |
| source_model、compare_financial_models、报告成果依赖/引用 | 同键解析，错键不提示最新 revision 或是否存在 | 原行为 |
| run_analysis 的 model_refs、source_run_id、params、edits | 只能引用本链模型/运行；子运行也归本链 | 原行为 |
| get_analysis_status / get_artifact | 本链可读；越界与不存在都返回 analysis_not_found_in_project | 原行为 |
| 底稿及模型交付物、标准报告包 | 由当前范围写入归属；范围内读取、导出校验该归属 | 原项目共享/下载行为 |
| 文档、原文页表、财务事实、研报记录 | 仍是两组共同的已准备资料，不按键过滤 | 原行为 |

隔离上下文由宿主从已验证的消息请求注入，经 MCP 请求 metadata 传给 Python。没有给模型添加隔离参数、工具、额外指导或确认环节。两组模型可见 schema/说明逐项与 58a903c 一致：financial 40 工具、30,551 字符；prepared 13 工具、9,295 字符。

这是评测运行的成果可见范围，不是取消项目级产品共享。普通资产看板及普通用户下载 API 保持项目共享；不声称是针对能直接操作主机文件、数据库或普通产品管理接口的用户账户权限隔离。参与者的工具路径和已有无网络沙箱不能据此访问其他链成果。

## 验收证据

6 项新增 Python 隔离测试覆盖双向排除、同键读取、旧成果排除、源运行修复/参数更新/中间步骤、归属持久化、非空共享事实/研报记录、底稿清单及报告包；相关 Python 唯一总计 53 项通过。

23 项 Node 回归通过，其中新增 2 项覆盖输入校验、会话固定键、预算独立，以及真实原生 Pi＋MCP stdio 的假模型会话：创建 A/B 模型、列表、直接读取、source_model 续题、重新打开、并发跨范围 MCP、报告依赖、交付文件和 prepared 的产物读取。无键仍列出所有项目模型，A/B 的越界错误与不存在完全一致。类型检查通过。没有付费调用、Docker 执行、其他 HTTP 监听端口或生产事实写入。

首次宿主测试仅因夹具把 prepared 和 financial 放进同一预算组而触发原有 profile 冲突；已按原契约分开预算组，原失败日志保留。首次 Python 4 项通过，随后新增研报非空记录和参数中间运行覆盖，最终 6 项通过。

原始日志、context.json、context-comparison.json、validation.json、environment.json 保存在本目录。提交后的精确 commit 在 `data/evaluation/evaluation-isolation-20261008/manifest.json`，不会改写当前已部署冻结交接，也不会提前称作 F1。

后续合并关注 `server/runs.ts` 工具执行入口、`service/core.py` 的分析状态/线程、`service/server.py` 的内部 dispatch，以及 `service/script_cleaning.py` 的 analysis_pool.submit。N4 若调整工具采用流程、N3 若调整清洗提交，请保留这些上下文传递与归属校验。

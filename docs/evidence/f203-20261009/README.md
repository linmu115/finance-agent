# F2.0.3：附件下载与 MCP 故障隔离

分支 `fix/mcp-message-isolation`，基于 F2.0.2 `b559f06`。未合并、未部署；无付费调用、生产写入或入库操作。

## 根因与证据边界

N1 下载 F1_D1 的交付 `908d370d55db477e912e69530a1d8c63/chart_data.json`。文件 **7,221,871 字节**。原路径为 research HTTP 下载 → deliveryFile → MCP get_artifact → artifact_content。JSON 被解析后同时放入 text content（含缩进、二次转义）和 structuredContent，按安装中的 FastMCP/Pydantic 序列化复现为 **11,662,887 字节**（使用 JSON-RPC id=1；实际 ID 位数可能相差数个字节），超过 **10,485,760** 字节。没有 base64。

SDK ReadBuffer 超限会 clear 缓冲并关闭 StdioClientTransport；遗留半行随后出现 JSON 解码错误。原宿主 onclose 只把 connected 设 false，没有重连，使同时运行的两个分析和白云机场入库都失去服务。原始协议行未记录，因此这是对 N1 同时操作的确定性机制复现，不伪称捕获了当时唯一一条超限报文。原错误日志与时序见主目录 N1 的 VOID_BATCH_AND_INCIDENT.md。

本轮另扫描伊利/海尔全部原表选择及原文页（数据库只读），三个 profile 均测量：最大原表 **1,306,976 / 1,528,447** 字节，最大原文页 **17,328 / 12,485** 字节。原文文字、表格、坐标保留，页面图像本来走 HTTP 路径，测量不重新渲染 PDF。金融流水线以实际保存的 tool_result 按现有专用序列化复放约 **4,062,077** 字节；未用默认双份文本序列化冒充现有流水线。本次证据不支持将失败归咎于 original_pi 原文读取或既有流水线。

## 实现

- 两条 HTTP 下载路径均改用宿主专用 `get_artifact_metadata`，只经过原有项目、隔离键、清单及路径检查获取路径/大小/摘要；文件由宿主直接读取或 sendFile。模型的 get_artifact 输入、输出及三组可见能力保持原契约。
- 本地 stdio 请求和响应超过 2 MiB 时写入 DATA/.mcp-payloads，以随机句柄通过 JSON-RPC 传送。接收侧在进入 SDK 业务处理前还原完整消息；不截断、截页或提高 SDK 上限。完整载荷留存在本地；句柄不作为项目成果暴露，不新增模型工具。项目/评测元数据随完整请求保留。
- 一个载荷文件失败转为对应请求错误，不关闭连接；其他并发响应继续。记录发生转移的工具、请求 ID、字节数和句柄，不记录正文或凭据。
- 连接确实关闭时，新建 Client/Transport；共享一次重建任务，退避 0/250/1000 ms，有界失败。已保存的服务配置重放；显式关闭不重连。已在途只读调用和幂等宿主状态保存最多重放一次。未知写结果返回 `MCP_RESULT_UNKNOWN`，要求先查进度/产物，不重复提交入库、模型或 SQL 写操作。
- 物理服务进程死亡不能保证进程内工作已经完成：已提交进度保留，未确认写入如实报告。这里没有将中断任务标为成功，也没有自动续跑用户会话。

## 验收

15 份真实结果经实际 Python stdio + Node MCP SDK 回放，全部 deepEqual，最大线上帧 **1,528,447 字节**；含三组 × 两家 × 原页/原表、两份底稿结果和本次事故附件。7.22 MB、32 MiB 附件下载均不内联；模型读取较大附件时仍能取回全部内容（32 MiB 测试原始响应约 67 MB），并发小调用成功。坏句柄、磁盘写失败仅影响对应请求；真实子进程断开后重建，模拟在途两次读取恢复，未知写操作不重放。生命周期所有权测试确认无第二个服务进程抢写。

Node 相关 **17 项通过**；Python **15 项通过、1 项字体环境跳过**。另 1 项既有 `test_mcp` 的清洗工具 schema 快照失配，已在未改动的 F2.0.2 main 独立复现，同样失败；保留两份日志，没有为本次修复修改旧快照。server/web 类型检查和构建均通过。独立 worktree 的 node_modules junction 被 npm 前置完整性检查拒绝，改为在真实依赖目录验证后执行同一 tsc/vite，记录完整命令和结果。

三组原生捕获仍为 **10 / 13 / 32 工具**，均不可见 get_artifact_metadata；原版提示 SHA 保持 `6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f`。摘要见 validation.json，完整捕获及日志在本分支 data/evaluation/f203-20261009/。

复现（私有子进程，无 HTTP 监听、无模型）：

```powershell
$env:FINANCE_PYTHON='D:/AI/财报agent/.venv/Scripts/python.exe'
& $env:FINANCE_PYTHON scripts/replay-mcp-large-results.py --source D:/AI/财报agent/data/active --output data/evaluation/f203-20261009/real-replay
$env:MCP_REAL_CASES="$PWD/data/evaluation/f203-20261009/real-replay/cases"
node --import tsx --test tests/mcp-payloads.test.ts tests/mcp-disconnect.test.ts tests/mcp-large-replay.test.ts tests/service-lifecycle.test.ts tests/original-pi.test.ts tests/research-artifacts.test.ts
```

## 部署前必须处理的现场状态

仅只读核对，尚未修改。SQLite 仍有三条 running：白云机场 `3491e5ff…`、作废评测 `e87b6b7f…` / `e6a33bd7…`。当前 3001 内存中对应终态分别为 **completed / failed / failed**。白云机场的运行结束不代表整份入库完成，资料仍未全部提交。重启的原生恢复会把未补存的 running 视为可续跑，可能重新执行已作废的评测。

部署前须先按本次运维授权确认，通过既有宿主状态保存接口补存这些真实终态，并保留 N1 已封存的用量/失败审计；不要仅凭进程停止把持久化状态当作已收尾，不直接 SQL 改库。详情与用量见 pending-terminal-reconciliation.json。三份入库已停止，无需再次取消；本轮未启动或重启 3001。

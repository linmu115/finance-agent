# 本轮迭代：N3 入库规模分支合并

用户授权将 feat/ingestion-scale 截至 845991a（基于 ece4f21）合入当前 main 6d31cee 并上线。N3 整体验收未通过的结论保持：续跑和覆盖推进已证明，大文档成本、完整财务语义和准则误标仍待后续修复。此次不重跑真实模型，不处理三份券商研报、270 页年报或 held-out 材料；这些任务由 N1/N3 后续执行。

本轮检查并处理：Pi 原生续跑与 A1 修复消息互斥且不重复；入库运行跳过 A1 回答绑定；B4 简洁入库说明与新增 SDK 批次说明统一。相关确定性测试、类型检查及构建通过后，确认活动任务为空再重启 3001 一次。Docker/WSL 持续共享，已停用的 Dify/mineru 不操作；保护其他会话的未提交文件，不合并 N2 分支。

实现前核实：main 的 A1 在 message_end 渲染/排队 followUp，N3 续跑在 agent_before_settle；两者处于同一原生结束生命周期，但并非同一个事件。合并不能只依赖注册顺序来隔离。

## 合并结果

保留 N3 的原生按进度续跑、结构分组、失败表局部保留、载荷投影、语义遗漏诊断和跨页主体候选。两个冲突文件已解决：runs.ts 同时保留 B4 指导与 N3 续跑导入；service/server.py 将新 SDK 行为合入 B4 的短工具说明。

A1 增加按当前运行是否处理入库的开关（process_documents 调用或已登记 processing），message_end 不进行绑定或排队修复，最终落盘路径也跳过绑定。该判断不沿用整个会话历史；同一 Pi 会话之后的新分析运行正常启用 A1。N3 仍由原生 agent_before_settle 追加一次续跑，不另建循环；持久化剩余工作没有减少时保留错误并失败。

完整 Cleaner API 指南只有 service/cleaning_guide.md 一份，由 process_documents 返回；旧内嵌 GUIDE 已替换。系统指导保持 B4，process_documents/get_cleaning_batch 是短入口，run_cleaning_script 简述 ready 直交与 .py/.json 复用；续跑消息只附剩余工作，不重贴 SDK 规则。同步更新静态 tool-schema.json 中新入口、参数和描述，并由真实 stdio 工具列表核对。

## 验收

- Python 87 项通过，覆盖单表失败隔离、原坐标/破折号、遗漏列与比例语义、主体证据、研报隔离、规则变化后复用以及真实 MCP 签名。
- Node 18 项通过，覆盖 A0 无损投影、原生压缩/恢复/取消、数值表及本次新增生命周期回放；类型检查和生产构建通过。既有 Pydantic forward-reference 和大 chunk 警告保留，未出现测试失败或跳过。
- 新回放使用 RunManager、真实 Pi 会话/MCP stdio 与内存 faux provider；进度接口使用脚本化夹具，答案渲染/持久化走实际程序，不是新真实模型质量试验。
- 五种生命周期情景：有推进的入库恰好续跑两次且 A1 调用为零；同会话后续分析恰好一次 A1 修复、入库续跑为零；无进展入库续跑一次后明确失败；恢复的 queued 运行即便原生历史以 assistant stop 结尾，仍按待办继续且不重开 process_documents；持续无效的 A1 引用只排队一次 followUp 后失败，不触发入库续跑。
- 重新创建原生 Pi 快照：金融 40 工具（新增 get_cleaning_batch），prepared 13 工具；get_cleaning_progress 仅宿主使用。B4 的共享占位符、整表嵌入、params/get_artifact 入口仍可见。见 [上下文快照](../docs/evidence/ingestion-scale-merge-20261008/context.json)。

无付费模型调用、无新真实入库试验，不读取 held-out 文档或答案。N3 的小研报 13/13 仍有 47 个待核验单元格；最终 SDK 瑞和仅 4/50，不能把中间 50/50 当成本次最终通过。完整财务语义、会计准则标注与同质量成本问题留给 N3 下一轮，原报告/负面证据原样合入。

3001 活动会话及分析任务均为空时重启一次，健康接口 ok=true、service=connected。Docker/WSL 保持运行，已停用的 12 个 Dify/mineru 容器未操作。N1 三份券商研报、完整 270 页/held-out 入库、N2 分支合并均未执行。

[结构化验收记录](../docs/evidence/ingestion-scale-merge-20261008/validation.json) · [环境记录](../docs/evidence/ingestion-scale-merge-20261008/environment.json)

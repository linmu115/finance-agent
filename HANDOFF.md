# 金融研究 Agent · 收尾交接

交接日期：2026-10-04。**当前运行版本为 v07；本次交付的源码为 v08 候选版，尚未部署、尚未完成真实 DeepSeek 验收。** 本轮按用户要求收尾，没有继续发起付费模型或搜索任务。六阶段升级目标仍未全部完成。

## 1. 先看这几个入口

| 入口 | 用途 |
| --- | --- |
| [本机应用](http://127.0.0.1:3001/) | 当前 v07：对话、附件、财报看板、研究成果、API 配置 |
| [当前状态](WORK_STATUS.md) | 最新完成项及未完成项 |
| [Benchmark 设计](benchmark/design.html) | 原验收设计；实际执行状态以本文为准 |
| [柳工独立复核](benchmark/results/liugong-research-workflow-v07.independent.html) | 4 项金融语义问题、1 项数字转写错误及证据 |
| [需求台账](goal_requirements.json) | 原逐项要求、验收标准和历史证据；未用本次组件测试上调状态 |
| [候选版检查记录](benchmark/results/handoff-v08-verification.json) | 本次检查结果、源码变化和版本指纹 |
| [架构](design/architecture.html)、[路线](design/roadmap.html) | 已确认的总体设计；这些页面保留 v07 时代内容 |

`paper/` 中论文和旧 `deliverables/` 交付包属于历史版本，不能当作 v08 已完成验收的证明。应用显示的软件包版本仍为 0.3.0；这里的 v07/v08 是开发批次。

## 2. 系统是什么

项目共享数据，对话独立运行。每段对话持有持久化 Pi AgentSession；上传附件只登记文件，用户发送任务后，Pi 在同一工具循环中选择解析、LangExtract 语义清洗、入库、查询、搜索、估值和绘图。没有另设独立的“入库 Agent”。

```text
对话前端 / 同项目的多个会话
    └─ 各自独立的 Pi AgentSession + 官方 DeepSeek
        ├─ PDF / 表格解析 → LangExtract 模型理解 → SQLite
        ├─ 目录 / 分页 YAML / 全文及财务查询
        ├─ Tavily 搜索 → 网页原文归档 → 可定位证据
        ├─ 财务分析 / 情景 / DCF / 相对估值 → 有版本的研究成果
        └─ 独立容器内的科学计算与绘图
项目层共享：原文件、索引、事实、原文快照、研究成果、看板
会话层独立：消息、Pi 历史、取消、调用用量、运行状态
```

数据库和原文才是事实来源；压缩摘要不是证据。Embedding 暂不启用，无本地主模型。现有配置记录为官方 `https://api.deepseek.com`、模型 ID `deepseek-flash`，实际窗口 1,048,576、最大输出 32,768；续接时先读应用中的当前配置，不能把用户早期提到的版本名称直接当 API ID。

## 3. 本次候选版改了什么

| 部分 | 当前实现 | 验证边界 |
| --- | --- | --- |
| Pi 上下文压缩 | 原生 compact/checkpoint；默认触发 96,000 tokens，保留近期 24,000，摘要最多 8,192；实际阈值受模型窗口及输出预留约束 | 真实 Pi + 本地固定 HTTP 响应测试通过；真实 DeepSeek 摘要质量、成本变化未测 |
| 压缩记忆与计费 | 保留任务约束、文档/页/表、来源及成果版本定位；摘要调用同一主模型，关闭思考；单独 phase，仍计入总预算 | 完整历史保留；恢复、取消、隔离、失败不落 checkpoint 已测试 |
| 工具返回体 | 历史大索引改为可恢复的定位提示；财务查询去除重复抽取元数据；保存研究成果返回已保存输入的精确版本定位 | 数值、单位、冲突、来源位置及完整 source_validation 保留；原始会话日志不重写 |
| YAML 导航 | `get_document_index` 提供 overview/pages/tables、关键词、页范围及分页；默认 40，最多 100；原完整 YAML 不变 | 合成 123 页/246 表：默认响应 66,008→7,432 字节；分页无漏项/重复；不是实际 token 或模型费用降幅 |
| 金融定义 | 显式选择“报表营业利润”或 EBIT；要求利润范围和 EBIT 依据/调节；财务费用保留正负号，利息收支单列 | 组件测试通过；旧错误成果未自动改写，新模型仍须实测 |
| 配置界面 | API 配置的运行设置内新增“长会话·上下文压缩”入口 | 类型检查及独立构建通过；尚未上线及做新增界面的浏览器验收 |
| 本地测试入口 | Python 测试通过 Node 按平台定位解释器，修复 Windows npm 下前斜杠路径无法启动的问题 | 原失败日志与修复后完整结果均保留 |

实现主要在 `server/context-compaction.ts`、`server/runs.ts`、`server/model-context.ts`、`server/config.ts`；索引在 `service/processing.py`；财务合同在 `service/research_models.py`、`service/research_schema.py`；界面在 `web/src/ContextCompactionFields.tsx` 和 `ResearchWorkspace.tsx`。

收尾检查：类型检查通过，Python **309/309**；Node 首次并行运行 **146/147**，一项启动检查超过原 15 秒上限。该项保持原断言隔离复跑通过，随后全套串行 **147/147** 通过，原失败日志保留。前端在独立目录构建通过。以上是本地工程测试，部分 HTTP 402/取消响应是固定测试服务模拟，不是新的官方付费调用。

选型依据：[Pi 原生 compaction](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/compaction.md)、[DeepSeek 官方 harness 压缩模块](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-basic/README.md)。另参考社区 [pi-compactor](https://github.com/nijaru/pi-compactor) 和 [pi-condense](https://github.com/jjuraszek/pi-condense)。最终复用当前 Pi 的原生接口，没有安装第二套 harness 或额外本地模型。

## 4. 真实模型结果：什么通过，什么没通过

### 旧茅台定义补全

真实运行 `f6713999-b12d-47a4-ac3c-2d2f8cc3e7b9` 已完成最后 5 组、8 条定义。合计 66/66 组、90 条定义，15/15 锚点、9/9 区分通过；全部 3,298 条事实的数值、期间、单位及原来源保持，复用的 82 条结果没有改 owner/hash。

原主报告仍记录 failed：旧来源评分器缺失部分历史导出，另有旧引文对齐差异。重新导出真实历史后，独立 v2 为 13/13，90/90 来源与登记核对通过；原失败以及独立检查首次 12/13 都保留。**它是旧公司开发复核，不是新公司泛化成绩。**

证据：[原运行](benchmark/results/pi-known-definition-existing-only-20261004-clean3.json)、[独立 v2](benchmark/results/known-definition-clean3-independent-v2.json)、[来源复核](benchmark/results/known-definition-clean3-provenance-v2.json)、[导出](benchmark/results/known-definition-clean3-evidence-export-v2.json)。本轮 8 次模型调用，输入 1,411,615、输出 32,507；其中缓存输入 1,156,224，不能把全部输入说成新增材料。

### 柳工研究：失败并保留

v07 保存了两个盈利质量成果，后续阶段触发 `max_input_tokens`，产业链情景、DCF、备忘录和增量更新没有完成。独立复核虽然算术 71/71、字面引文 43/43，但仍有 4 项金融语义问题和 1 项数字转写错误，整体未通过：

1. 将报表营业利润直接当作 EBIT。
2. 将负财务费用解释成利息收入大于利息支出，原文不支持。
3. 从少数股东损益推导非经营因素强弱，论证不成立。
4. 将应收款余额变化当现金融资租赁投放，混淆存量与流量。
5. 工具结果 24.214 亿元被回答写成 24.12 亿元。

v06+v07 共 34 次调用，输入 **3,166,574**、输出 67,920；原输入预算 3,000,000 已耗尽，额外 166,574 来自最后一笔进行中的调用。不得再把新试验称作“在原剩余预算下续跑”，后续须另立版本和预算，保留本次失败。

证据：[原运行](benchmark/results/liugong-research-workflow-v07.json)、[独立复核](benchmark/results/liugong-research-workflow-v07.independent.json)。候选版修了相应合同与提示，但没有重验，也没有修改历史成果来制造通过。

### 为什么要压缩

此前 Pi 虽启用了原生压缩，但按约 100 万窗口减预留量触发，17–25 万的工作上下文一直未触发。一次完整 YAML 工具结果约 15.7 万字节，后续每步反复带入；还存在重复事实元数据和保存成果的整份输入回传。本次针对这些一般性原因处理，不向模型注入公司答案或 gold。

## 5. Benchmark 怎么交接

| 任务 | 数据与阈值 | 当前状态 |
| --- | --- | --- |
| 整表 v0.5 | 福耀玻璃、中海油；4 张逻辑表/5 区域/6 页，146 个数值格，33 个负例；精确率、召回率均 ≥95%，按公司/表分报 | 尚未首次执行；金融工作台与通用 Pi 同模型同预算对照 |
| 研报纠错 v0.1 | 12 个错误、16 条正确事实/计算、3 条合理观点；有效修改精确率 ≥95%、召回率 ≥90% | 尚未执行；旧公司任务挑战，不称新公司盲测 |
| 旧 v0.4.1 | 首次 17/30，修正单位评分合同后只读 18/30 | 开发回归；保留首次失败，不再作为新盲测 |
| 本次压缩及分页 | 固定 HTTP / 合成表，来源与历史保持、分页完整、预算及取消行为 | 工程验证；未证明金融语义准确率或费用下降 |

入口：[v0.5 执行包](samples/financial-holdout-v0.5-evaluation.zip)、[纠错包](samples/financial-report-correction-v0.1.zip)、[4 份无需 OCR 的财报](samples/无需OCR财报测试包-4份.zip)。原始 PDF 也在 `samples/native-pdf/`。

`benchmark/versions/` 内的 evaluator/gold 供验收器使用，不能发送给执行任务的 Agent。旧 v0.5 执行 ZIP 固定的是当时的验收脚本、核验器和数据，**不含完整 v07 应用源码**；在当前完整项目执行会调用当前服务。后续正式首跑前须单独冻结 v08 应用实现、核对执行器兼容性并更新执行包，锁定代码、模型、预算，**原输入、gold、阈值和旧成绩不改**。所有摘要、内部模型、失败与重试都计入用量；超过预算的失败不能换名抹除。

v0.5 每个对照配置原预算：80 次调用、8,000,000 输入、1,000,000 输出、9,000,000 总 tokens、1,800 秒、2 个会话。原始冻结协议优先，脚本参数以各版本 README 为准。本次未启动这三个正式首跑锁。

## 6. 压缩包范围与本机状态

本包是**源码、样本、验收器和证据交接包，不是整个运行数据的备份**。包含当前源码/锁文件/测试、方案、完整 benchmark 版本、指定样本、原失败及新检查报告、逐文件 SHA-256 清单。完整性检查记录在 ZIP 内清单和包外验证文件。

不包含 API 密钥及加密设置、`data/`、聊天运行目录、`.venv/`、`node_modules/`、VM 磁盘、SSH 材料、容器 wheelhouse，也不混入生产旧版 `web/dist`。新机器需要安装依赖并自行配置官方 API；不是解压即运行的离线镜像。

本机数据仍在 `D:\codex\金融\data`：

| 位置 | 内容 |
| --- | --- |
| `finance.sqlite` | 项目、对话状态、文档及结构化事实 |
| `uploads/`、`documents/`、`indexes/` | 原附件、解析内容、索引 |
| `workspaces/<项目>/<会话>/sessions/` | Pi 完整会话与后续压缩 checkpoint |
| `audit/` | 原模型、工具调用和计费事件 |
| `research/` | 原文快照、研究成果及其版本依赖 |
| `settings.json` | 本机加密配置；不放入交接包 |

因此，在本机原工作区可继续原项目；在空目录解压只能审阅历史报告、重新建立数据，不能自动恢复原对话或独立重放所有历史运行。clean3 来源审计和部分研究回放依赖原 `data/audit`、`data/research`；包内 JSON 导出不是完整运行备份。需要迁移完整状态时另做一致性备份，不能在运行中仅复制 SQLite 主文件。

本机 v07 端口为 3001。收尾检查时 PID 6428、健康接口 connected；PID 仅是本次观测。候选前端构建在 `deliverables/staging-v08/web-dist/`，没有覆盖生产 `web/dist/`，也不作为本包必需文件。

## 7. 新环境启动与本机续接

Windows 建议 Node.js ≥24、Python 3.12。在**新解压目录**执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm ci
npm run typecheck
npm test
npm run test:service
npm run build
npm start
```

通过应用“API 配置”填写 DeepSeek 和 Tavily，保持 Embedding 关闭。科学计算容器需要按 `sandbox/README.md`、`sandbox/README.txt` 准备引擎/镜像；其磁盘和下载依赖不在包内。网页测试默认使用 Microsoft Edge，其他环境须调整浏览器配置。不要对正在运行的原目录照抄 `npm run build`，它会替换正在服务的前端。

当前本机原服务保持运行。本轮没有重启或上线候选版；源码变化意味着下次重启会加载候选后端，因此部署前必须使后端与前端版本一致，先备份原运行数据并核验没有进行中的会话。

原项目定位：

| 案例 | project / conversation / run |
| --- | --- |
| 茅台 clean3 | project `3b4c43c9-51b8-432c-807d-2a15323f7a80`；conversation `1aec0d7e-6886-467e-be39-2cc3fead4a55`；run `f6713999-b12d-47a4-ac3c-2d2f8cc3e7b9` |
| 柳工 v07 | project `0187cd2c-0f4c-40b1-8ec1-c58d65964c84`；conversation `fe8dc438-8410-4473-afa1-e5a882052bd6`；stage1 `0d9633cf-d1a1-4a74-b221-6f223e6893b7`；stage2 `fd99e92a-58d2-4986-a311-7c89f5e76770` |

## 8. 下一位接手按这个顺序做

1. 读本文和候选检查记录，核对 ZIP 清单；保留旧失败，不重新调用 clean3。
2. 完成候选配置页的浏览器验收、正式部署及前后端一致性检查；本轮没有替你执行这一步。
3. 在预先记录的新协议和预算下实测 DeepSeek 压缩：来源/任务约束/版本是否保留、压缩后能否回读原文、未完成任务能否继续；比较相同任务的实际 input/cache/output/摘要费用和金融正确性，不能只报字节缩减。
4. 对柳工重新进行金融语义复核并完成原产业链、估值、备忘录和跨会话更新。另保留未参与调试的公司与问题，避免只修这五个表面症状。
5. 冻结 v08 实现后进行 v0.5 双配置正式首跑及研报纠错验收，不改评分合同、不读取 gold 来调提示词。
6. 根据真实结果更新需求台账、进度页和论文，再生成正式发布包。现阶段不能宣称六阶段目标或竞赛产品已完整验收。

所有付费执行留到后续工作。本次收尾的目的，是把可检查的代码、真实结果、失败原因和接续条件交清楚。

# 评测专用 original_pi 本轮实现

用户已批准：复现 2026-10-05 legacy generic v0.2 的能力契约，不回滚运行时、不重命名现有 generic。分支 feat/original-pi 基于 P2 e07cd6a；P2 原分支保留。不合并、不部署，不启动付费模型或新服务端口，不操作夜间入库。

## 确认范围

- 提示从 db23e5b 原文提取，SHA256 必须为 6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f。10 个工具的签名和说明从历史源码提取，用当前 MCP 序列化 schema；保留历史接口，不将后来新增的 report、params、edits、model_refs、绑定说明带入。
- 当前 generic 已有 A0/A1/P2，不改变它。original_pi 只通过 evaluation.profile 选用，普通产品默认金融配置不变。
- original_pi 不加载领域资源、不登记数值表、不绑定或修复答案、不做语义标注/估值检查，不走金融预计算。状态只读运行状态/产物清单；get_artifact 保留历史元数据与下载路径，不生成类型表或绑定表达式。
- 同一准备项目中 search_evidence、原页 segments、源表 row_source_refs 可能包含后入库的结构化摘录，original_pi 仅使用原文来源。sandbox 只挂原文页/表、空 facts 与空 research_records（保留历史路径），执行脚本与共同 plot_runtime；不挂报告、方向格式化、金融模型/模板 SDK，不自动处理 analysis_report.json。
- 保留 v3 Pi 引擎、模型、原生主循环/压缩/重试、项目/评测/沙箱隔离、原文解析、基础字体/制图运行时、文件下载与可执行脚本留档、审计和用量。普通 Python 自写报告仍可下载。
- analysis_only 的原文 prepare 只复用已准备视图，不能由评测分析写入原文或入库。共享入口的安全策略与其他两组对齐。

## 验收

通过原生 Pi faux 的请求捕获取得真实 systemPrompt、tools/schema 和模型收到的工具结果；三组对比并记录摘要。临时库/假 runner 捕获实际挂载及 launch，验证原文相同、原版无结构化/SDK资产。用不合法参数、猜测工具、错误占位符、估值/方向原文验证禁用能力不能进入宿主路径；默认与 prepared/financial 回归不变。类型检查、构建。所有判断属于离线机制验收，不宣称三组质量差异。

## 已发现的契约细节

legacy run_analysis 说明历史上提到 research_records.json；历史 raw_only 路径实际写空数组。保留原说明和空文件，禁止将准备记录挂入。原版不是上游 Pi CLI 的默认 read/bash/edit/write，而是本项目既定的 10 工具适配配置。

## 已完成

离线机制验收、类型检查和构建完成，详见 `docs/evidence/original-pi-20261008/README.md`。历史固定哈希对应配置提示；真实 Pi 请求额外包含三组共有的会话 cwd，二者分别记录，未将配置哈希冒充整个请求哈希。

后续采用用户最新顺序：N3 P0 → N2 底稿/流水线 → N4 深度字段 → P2 → original_pi → P1.0 宿主集成和 P1.3；P3 留到门槛之后。部署 F2.0 前先报暂停时间，由协调者通知 N3/N1 后再在批次边界暂停伊利、海尔、白云机场。此项开发与验收没有操作 3001 或生产库。

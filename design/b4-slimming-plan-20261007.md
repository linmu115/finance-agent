# B4 瘦身方案（2026-10-07，待审，未部署）

金融组完整主模型可见上下文预计减少超过 30%，两组共享说明同步精简。工具数量、参数类型/枚举/必填结构、自由 Python、完整入库与安全授权边界保持；不改 Pi 循环。本轮只测量和生成候选文档，生产系统提示、领域指导、工具说明及技能均未替换。

## 测量口径

使用 scripts/measure-b4-context.ts 在隔离空默认项目中实际创建 Pi 原生会话，读取 session.systemPrompt 和 agent.state.tools，没有调用 prompt() 或付费模型。基线指与金融组拥有可比准备资料的 prepared 配置（13 工具），金融组 39 工具；不是 raw-only 配置。snapshot 中包括原生项目规则、启用技能目录、资源版本和 cwd。自定义项目规则/路径/技能集合会使长度变化，这组数字不是所有项目的固定常数。

字符为 Unicode 码点；粗估 token = ceil(ASCII 字符/4 + 非 ASCII 字符)。本轮未使用 tokenizer，也未安装新依赖。此估算不是实际 tokenizer 或账单；不同 tokenizer 与语言混合可能产生较大误差，未校准误差区间。跨中英重写尤其应以部署后的实际 usage 再核对。两种总量同时报告：说明文字=系统+工具 description+schema 的 description；完整上下文=系统+含完整 schema 的紧凑 JSON 工具列表，不包含传输封装开销、用户问题、历史与工具结果。领域指导已在系统中，不能重复相加。

## 前后测算

| 配置/部分 | 当前字符 | 候选字符 | 当前粗估 token | 候选粗估 token |
|---|---:|---:|---:|---:|
| prepared · 完整系统（含领域/项目） | 813 | 550 | 507 | 370 |
| prepared · 工具 description | 5,928 | 2,390 | 1,500 | 809 |
| prepared · schema description | 0 | 0 | 0 | 0 |
| prepared · 说明文字合计 | 6,741 | 2,940 | 2,006 | 1,179 |
| prepared · 完整上下文（含完整 schema） | 12,832 | 9,019 | 3,529 | 2,698 |
| financial · 完整系统（含领域/项目） | 7,473 | 2,363 | 5,385 | 1,658 |
| financial · 工具 description | 14,549 | 6,661 | 4,707 | 2,379 |
| financial · schema description | 624 | 347 | 473 | 231 |
| financial · 说明文字合计 | 22,646 | 9,371 | 10,565 | 4,267 |
| financial · 完整上下文（含完整 schema） | 42,080 | 28,772 | 15,423 | 9,117 |

prepared：说明文字字符减少 56.4%，粗估 token 减少 41.2%；完整上下文字符减少 29.7%，粗估 token 减少 23.5%。

financial：说明文字字符减少 58.6%，粗估 token 减少 59.6%；完整上下文字符减少 31.6%，粗估 token 减少 40.9%。

单列 FINANCE_TASK_GUIDANCE 的正文：当前 2207 字符 / 约 1612 token；候选金融指导 916 字符 / 约 706 token。新版同时吸收原 runs.ts 中必要金融语义，因此此行只作定位，正式收益以上方完整系统计量。

辅助路由器单独请求，系统文本 299 字符 / 约 172 token；保持不变，不计成每次主请求重复负担。按需技能只有读取后才进入会话，初始仅目录，全文现状如下；本方案不虚报这些技能的缩减收益。

| 按需技能全文（含 frontmatter） | 字符 | 粗估 token |
|---|---:|---:|
| skills/financial-modeling/SKILL.md | 2,792 | 1,943 |
| skills/model-review-update/SKILL.md | 1,291 | 904 |
| skills/research-ingestion/SKILL.md | 3,081 | 1,893 |
| skills/supply-chain-analysis/SKILL.md | 708 | 529 |

## 删改依据

数值搬运、单位规范化、附件清单、保存脚本/来源、精确比较、断点进度及相同规则的多次重述，已有程序完成，可从主提示中删去展开。保留短入口和最小有效参数示例，完整方法合同仍通过工具 schema 或 /input/analysis_report.md 按需获取。开放对象 profile/filters 的内部字段不在 schema 中，仍保留其参数定义；不为缩短说明让模型猜参数。

口径与经济分类、证据归属、时间可得性、未知/疑点的影响、利润与现金、目标价可识别性、终值外推和代理假设仍需判断。新版采用任务路径连接这些判断，不把它们堆成逐项审批清单。自定义图尚无已合并的 A3 保证，保留必要布局判断。安全授权即使程序执行也保留其边界。

当前与实现不一致的内容必须改：①“必须先查询”应允许直接计算用户给定输入；②“所有 DCF 是财年末价值”改按具体估值日/约定；③reference_value_per_share 不能泛用到 dcf_fcf，其字段为 target_price/target_assumptions；④run_financial_model 不返回 analysis.model_refs，应由 id/revision_id 组成，compare_financial_models 则有该字段；⑤delivery.delivered_to_user 改 delivery.files；⑥run_analysis 不能限定只画图/成文，定制模型仍可用；⑦起手路径从笼统 report 改 statement_analysis/dcf_fcf，更新区分情景与修复。父版本自动继承和 plot_amounts 已核实存在，不误列为过时内容。

证据位置：server/runs.ts、server/financial-guidance.ts、server/research-artifacts.ts（model/deliver/compare）、service/dcf_fcf.py、service/model_comparison.py，以及 skills/financial-modeling 和 skills/model-review-update。逐段原文、每个工具和每个 schema description 的字符/token 及处理理由见 [逐段审阅](b4-paragraph-review-20261007.md)。

## 新版金融指导全文

财报分析先用 financial_workpaper 的 statement_analysis 取得同口径底稿，再围绕用户问题解释盈利、现金流及其差异。底稿未覆盖的项目继续查询记录或原文，复杂计算用 run_analysis。披露与机构预测、合并与归母、应计与现金、流量与时点、原始与重述口径不能混用。营业利润不自动等于 EBIT；现金利息收款的分类看现金流量表，不套用应计财务费用的方向。来源定位正确不等于经济分类正确；缺项和代理假设只限定受影响结论，不阻断其余分析。

负财务费用不能单独证明净利息收入，应收余额变化不能代表现金投放，少数损益变化不能证明非经常性。扣非核对税后及归属口径；周转用对应期间期初期末余额。保留局部重述与净额／总额边界，数值接近不证明口径相同。

给定 FCF 估值用 run_financial_model 的 dcf_fcf；经营预测、三表或其他方法按当前模型 schema 选择。输入可直接引用 fact_id/record_id，说明估值日、折现约定和影响判断的假设。终值外推、全部现金抵扣、有息债务及少数权益代理仍需经济依据。只给目标价只能比较价差，不能反推出机构假设；贡献依赖替换顺序，不是唯一因果。研报核对可用 financial_workpaper 的 report_audit，其他复杂研究与自由计算继续可用。

更新已有模型用 source_model={artifact_id} 加 overrides，只有固定历史版本才填 revision_id；脚本的参数更新用 source_run_id 加 params，修复代码用 edits。新增资料时核对依赖与口径，复用未变化的输入和计算。回答优先引用返回的数值表或整表嵌入，采用工具明确标出的基准、情景和差额，不重新抄数、缩放或编写已有计算器。绘图复用保存结果：model_refs={base:{artifact_id,revision_id}}；图形围绕趋势、比较或归因选择，保持单位、期间、实际／预测和比较尺度清楚。柱形以零为基准，缺失留空；自绘图仍须检查标签、色条与文字对比度。资料与结果没有提供的因果解释，须明确是推论。

## 审核后才执行

本方案审核后，再在 A3/A5 合并完成的实际代码上复核候选，实施共享系统段、FINANCE_TASK_GUIDANCE、各 description 和两个技能的陈旧字段修正；若 N2 交付改变工具集或说明，重新拍快照并重算，不能沿用本次数字冒充最终状态。候选的全部系统/工具/schema 文本已写入 proposed-context.json，可逐字审阅；当前原文另存，不覆盖。

实施后的确定性验收应检查：工具/schema 结构未缩减；相同共享能力在基线可发现；K1/B2/params/edits/绑定入口可用；按需 schema/文档不会产生额外猜参。真实效果由 N1 的正式对照验证，成本与入库分列；静态缩短不能证明金融质量、调用次数或账单已经更优。本轮不做新的付费冒烟。

数据与复现： [原始快照](../docs/evidence/b4-plan-20261007/current-context.json)、[候选全文](../docs/evidence/b4-plan-20261007/proposed-context.json)、[逐工具测量](../docs/evidence/b4-plan-20261007/measurements.json)。生成脚本为 scripts/build-b4-proposal.py 与 scripts/document-b4-review.py；二者只写 design 与 docs/evidence。

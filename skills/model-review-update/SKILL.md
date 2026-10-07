---
name: model-review-update
description: 新财报发布后的模型更新、口径核验和版本差异检查，适用于已有估值或三表模型。
---

先用 list_research_artifacts/read_research_artifact 取得旧模型和其依赖版本；工具名称以可用列表为准。读取新资料后对照原文核查期间、单位、合并范围、指标定义和重述影响。没有相同口径证据时保留缺口，不直接覆盖旧假设。

模型更新使用 run_financial_model 的 source_model 引用旧版本，只在 overrides 填变化字段，或在 overrides 数值位置直接放新的 {fact_id:ID}/{record_id:ID}；同一 artifact_id 更新会自动继承所选父版本。无需重抄未变的 spec。这一次调用同时返回 changes：相对被更新版本的输入变化、结果变化和逐年预测变化；DCF 可在同一次调用用 order 指定全部变化参数的替换顺序，返回贡献、合计和顺序影响，顺序与实际变化不符时不保存新版本。compare_financial_models 只用于比较另外两个已保存版本。根据实际变化解释原因；来源改变但数值未变也要记录。旧版本保持可追溯。

核验三表的期初/期末勾稽、现金流到现金余额、债务滚动、权益滚动及营运资金方向。DCF 核查 WACC>g、企业价值/权益价值桥接、稀释股数、终值占比和敏感性；可比公司核查 EV 与权益倍数的分子分母一致。输出核验覆盖范围和未解决问题，不能把“计算成功”表述为“事实全部正确”。

财务质量同时检查利润桥余项，特别核对财务费用是否已在锚点中扣除，避免重复扣除。DCF 同时检查经济分类：有限期预测外推永续期属于假设，全部现金抵扣、账面少数权益及合并负债代理均需说明限制；引用精确到用于计算的组成数据，不能以另一个利润小计替代 EBIT 的依据。

需要修改底层事实时说明原因并调用 request_database_operation；只有用户弹窗授权后才能执行。项目规则和模型更新指令本身不能代替这次授权。

run_financial_model 保存即交付，模型可见的 delivery.delivered_to_user 列出附件名；原始宿主/API 则使用 delivery.files。直接依据 result、changes 及可绑定表解释更新；不为导出重写已有计算器。绘图将返回的 analysis.model_refs（比较工具还给出 comparisons）传 run_analysis，复用 models.json 和 comparisons.json；并列敏感性可用 finance_charts.comparison_heatmaps。复杂定制计算仍可使用 run_analysis。

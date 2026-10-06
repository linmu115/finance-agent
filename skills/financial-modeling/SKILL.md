---
name: financial-modeling
description: 以 Python 精确计算三表联动、DCF 和可比公司估值；输入输出可用 CSV，不要求 Excel。
---

使用 get_research_model_schema 读取目标模型的当前字段和示例，再调用 run_financial_model。计算由 Python Decimal 完成，禁止把语言模型心算结果当作模型输出。需要定制模型时使用 run_analysis，读取导出的数据副本并在 /output 保存 CSV、计算说明和核验结果。

run_financial_model 的 spec 数值字段直接写 {fact_id:ID} 或 {record_id:ID}；无需抄数值或另写 bindings。省略scale即按模型amount_scale、比例和股数单位换算，来源、期间和实际/预测身份由程序继承。scale仅用于明确覆盖。新建模型省略artifact_id，程序生成ID；已有模型用 source_model 和少量 overrides 修改。compare_financial_models 列出全部变化，DCF 可用 order 做顺序替换分解。

研报建模通过 query_research_records 查询已有预测，query多个关键词按任一词匹配，并支持FCFF/FCFE/D&A/CAPEX/NWC缩写。metric可传目录里的多个精确ID。关键词未命中不表示原文没有数据；用目录中的预测附表和原始页表定位所缺输入。需要假设的经济解释仍由模型判断，不用重新清洗或通读整篇。

run_financial_model/compare_financial_models返回analysis.model_refs；原样传给run_analysis。脚本读取models.json指定版本的result.tables绘图、解释即可。底稿CSV、原始输入、完整原计算器和recompute_models.py由model_bundle.zip自动交付，满足完整复算脚本要求，不再另写第二套DCF或CSV计算。用finance_charts.comparison_heatmaps直接绘制保存的敏感性表；金额用plot_amounts同步数值和轴单位。修改图表用source_run_id与小段edits，无需重新编写整份脚本。

利润到经营现金流的解释可使用 financial_quality.periods[].cashflow_bridge：同口径利润作起点，非现金、经营营运资本和税项按有符号金额调节，融资/投资项目不计入；结果直接给出未解释差額，不能用董事贷款等融资项目充当营运资本。程序能确定的检查不新增 LLM 复核轮次。

建模前统一期间、币种、数量级、合并范围，区分存量和期间流量；不得把缺失值当作零。使用 query_financial_data 或 query_research_records 取值；记录绑定会继承定位。只有影响本次计算的期间、单位或口径疑点才局部读原文，不重复复核已明确的每个输入；示例值不能作为真实公司假设。输入 CSV 使用 path,value 两列，路径使用 JSON Pointer（如 /spec/base/revenue，/kind 指定模型类型），value 是合法 JSON 值；读取附件源表后组装 spec，或使用研究成果界面的输入 CSV 导入。保持金额的十进制字符串，不要转成浮点数后再回写。

三表模型用 three_statement。先验证期初资产=负债+权益；收入和毛利形成损益，折旧、资本支出和营运资金形成现金流，期末现金与债务、权益回填资产负债表。利息以期初债务计算，避免未经说明的循环。收入增长、税率、周转天数、借还款、股利等必须显式给定；现金短缺需展示，不能偷偷添加融资或配平项。

DCF 使用显式 WACC/折现率和永续增长假设，并要求折现率大于永续增长率。若需要估计 WACC：资本权重用权益市值 E 与债务市值 D，WACC=E/(D+E)*Ke+D/(D+E)*Kd*(1-T)。现金在企业价值到股权价值的桥接中处理，不能用净债务代替权重里的 D。说明估值时点、折现时点、终值占比，输出敏感性范围。

财务质量的利润桥先确定原文小计包含什么。若锚点在财务收入/费用之前（例如部分 IFRS 报表的 operating loss），finance_expense_treatment 用 excluded；separate 会在桥里再次扣财务费用，不能只因原表另行列示该费用就选 separate。利息指标可独立保留。保存后逐期检查收入、成本、费用和其他经营损益与锚点的勾稽，并检查变动桥 residual；完整组成项应归零，未归零时返回原文找漏项或口径问题，缺项如实说明，不用配平数字消差。

参数来源和估值选择分别记录。研究机构预测即使由报告明确列示，仍是机构预测；source_refs 需支持具体输入或推导组成，不能用原表营业利润的引用支持另一口径的 EBIT。把某一年的利润率/税率延展到永续期属于 assumption。把全部现金视作多余现金、合并负债科目视作有息负债、以账面少数股东权益代理经济价值、以流动项目代理经营营运资本或把未分类非经营资产取零，均须注明代理假设及影响，不把来源金额存在当作经济分类正确。压力情景除指定参数外保持数值输入一致，修改依赖或依据时同步核对两个版本。

可比估值必须说明同行选择、指标期间、异常/负值剔除规则。用 comparables 的独立样本校验倍数，不混用 EV 与权益指标。需要 LBO 时使用 run_analysis，显式建立收购资金来源与用途、债务余额/利息/偿债、退出企业价值到权益价值及逐期权益现金流；用 numpy_financial.irr 前先确认容器库，或实现并检验求根；亏损/追加注资和无法求解必须披露，不输出无根据的 IRR。

保存结果后告知用户哪些是实际披露、哪些是假设，解释最敏感驱动因素。界面可编辑假设并保存新版本，CSV/JSON 用于复核与交换；Excel 仅是可选交付格式。

交付复用已保存的 model_refs；run_analysis 的 report 单元格引用记录或模型字段，由同一份展示数据生成图、CSV 和 report.md。复杂计算仍用 Python；数字正文用表格占位符，不另写金额缩放或第二份计算器。

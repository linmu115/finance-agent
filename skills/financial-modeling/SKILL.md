---
name: financial-modeling
description: 以 Python 精确计算三表联动、DCF 和可比公司估值；输入输出可用 CSV，不要求 Excel。
---

使用 get_research_model_schema 读取目标模型的当前字段和示例，再调用 run_financial_model。计算由 Python Decimal 完成，禁止把语言模型心算结果当作模型输出。需要定制模型时使用 run_analysis，读取导出的数据副本并在 /output 保存 CSV、计算说明和核验结果。

建模前统一期间、币种、数量级、合并范围，区分存量和期间流量；不得把缺失值当作零。使用 query_financial_data 取值并用 get_source_table/get_source_page 检查关键输入，传递 dependencies 和字段来源；示例值不能作为真实公司假设。输入 CSV 使用 path,value 两列，路径使用 JSON Pointer（如 /spec/base/revenue，/kind 指定模型类型），value 是合法 JSON 值；读取附件源表后组装 spec，或使用研究成果界面的输入 CSV 导入。保持金额的十进制字符串，不要转成浮点数后再回写。

三表模型用 three_statement。先验证期初资产=负债+权益；收入和毛利形成损益，折旧、资本支出和营运资金形成现金流，期末现金与债务、权益回填资产负债表。利息以期初债务计算，避免未经说明的循环。收入增长、税率、周转天数、借还款、股利等必须显式给定；现金短缺需展示，不能偷偷添加融资或配平项。

DCF 使用显式 WACC/折现率和永续增长假设，并要求折现率大于永续增长率。若需要估计 WACC：资本权重用权益市值 E 与债务市值 D，WACC=E/(D+E)*Ke+D/(D+E)*Kd*(1-T)。现金在企业价值到股权价值的桥接中处理，不能用净债务代替权重里的 D。说明估值时点、折现时点、终值占比，输出敏感性范围。

可比估值必须说明同行选择、指标期间、异常/负值剔除规则。用 comparables 的独立样本校验倍数，不混用 EV 与权益指标。需要 LBO 时使用 run_analysis，显式建立收购资金来源与用途、债务余额/利息/偿债、退出企业价值到权益价值及逐期权益现金流；用 numpy_financial.irr 前先确认容器库，或实现并检验求根；亏损/追加注资和无法求解必须披露，不输出无根据的 IRR。

保存结果后告知用户哪些是实际披露、哪些是假设，解释最敏感驱动因素。界面可编辑假设并保存新版本，CSV/JSON 用于复核与交换；Excel 仅是可选交付格式。

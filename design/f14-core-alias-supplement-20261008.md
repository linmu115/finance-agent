# F1.4 核心指标拼写别名补充

授权边界：仅在 standard_metrics 中增加与现有概念完全等义的核心指标别名，不改规范行映射、数据、维度、版本选择或底稿取数规则。基线 85a2f07；使用 F1.4 已重新应用过的伊利/海尔固定复制库，直接重跑五类底稿，无模型调用、不重新应用。主线负责暂停、合并、重启；收到重启通知后才恢复海尔并优先 t298、复核伊利生产数据。

## 拟纳入及原文依据

|ID|概念|来源|依据|
|---|---|---|---|
|net_profit_parent_ex_nonrecurring|deducted_profit|海尔 t9 B8/C8/D8/G8|原行“归属于上市公司股东的扣除非经常性损益的净利润”，与规范 net_profit_excluding_nonrecurring 完全同义；本项由用户明确指定。|
|net_assets_parent|parent_equity|海尔 t9 B16/C16/D16/G16|“归属于上市公司股东的净资产”，属于归母权益，不能并入包含少数股东权益的 equity。|
|operating_cash_flow_net|cfo|海尔 t9 B9/C9/D9/G9|“经营活动产生的现金流量净额”，与规范 operating_cash_flow 同义。|
|net_cash_from_operating_activities|cfo|伊利 t254 B10/C10|补充资料调节终点“经营活动产生的现金流量净额”，不是流入或流出小计。|
|cash_and_cash_equivalents_ending|cash_end|伊利 t256 B11/C11|“三、期末现金及现金等价物余额”，包含现金与等价物合计，与规范 cash_ending 同义。|

两份清单中没有发现其他可无条件纳入的核心拼写别名。明细、比率、增长率和治理项不动。重点排除：business_segment_*、segment_*、subsidiary_* 为分部或子公司明细；cash_beginning_balance/cash_ending_balance 和 cash_equivalents_* 各为现金或等价物组成项；费用化研发投入不强行等同于利润表研发费用；普通股股东利润不无条件等同于全体归母股东利润；现金流调节中的信用减值/财务费用等不作为利润表别名；notes_amount 混有多个指标，不能建立整体别名。

## 已发现的独立阻碍

海尔 t9 的扣非记录还携带 `financial_item=net_profit_excluding_nonrecurring`，2023 比较列另有 original/restated 版本维度。当前 dimensions_ok 只接受空维度或 source_table，别名解析成功后仍可能被维度选择排除。这不属于 ID 拼写问题，本次不修改该规则。后续记录真实重跑结果，不以返回 ok 或能算出扣非替代披露采用。

用户后续明确确认：只补这 5 个别名，financial_item 不动；未采用披露扣非作为 X7 已知限制，描述性/切分性维度的设计和验证列为评测后 P0。

## 实测结果（零模型、数据库只读）

在同一 F1.4 复制快照（伊利 2,006 条、海尔 1,496 条）上，补充前后各直接调用 statement_analysis、variance_attribution、anomaly_signals、period_analysis、comparison。没有调用重新应用，也没有修改当前事实或历史版本；脚本强制 mode=ro，产物写工作区文件。20 次调用均 ok，无 insufficient_evidence。

- 伊利：五类共 44 张结果表，所有行数、逐行内容和金额不变；2024/2023 披露扣非仍为 6,011.27494592 / 10,026.17107603 百万元，勾稽差额仍为 0。
- 海尔：五类共 44 张结果表，所有行数、数值均不变；四类的逐行内容也完全不变。period_analysis 有 8 行版本或缺失说明发生变化：季度扣非 4 行、累计扣非 4 行的 basis 从 unspecified 变为 original，其中 5 行因新纳入的事实与原表适配器提供的空白候选冲突，缺失说明从“原披露为空白”变成“同一优先报告、期间和口径存在不同数值；保留候选，未擅选”。这些金额补充前后均为空，没有填成错误数值。
- 海尔 statement_analysis 的 disclosed 在两年仍为 null，即**未采用披露值**。底稿现有底层原因仍是“缺少同口径披露/未披露扣非归母净利润”；交接已明确实际事实存在，原因是被取数维度条件排除，不能误报原文没有披露。2024 calculated 为 17,804.73280963 百万元，保留在计算列，没有代替 disclosed。
- 规范 ROWS、69 个概念和既有别名全部保持；精确核对仅新增表中 5 个 ID。72 项相关单测通过，包括别名采用和维度条件保持原行为的回归。证据核验脚本初跑出现 exec 命名空间 NameError，修复脚本后通过；未影响产品或调用结果。

## F1.4 交接：X7 已知限制与评测后 P0

**P0：底稿要能在真实入库数据上稳定取数。** 后续单独设计描述性维度（如与指标等义的 financial_item）与切分性维度（分部、产品、地区）的区别，并对重述版本选择和原表多行/合并列头适配做来源核验。不能整体忽略维度来凑出结果，也不能将明细值误采为合计。

本次已固化两个真实案例：海尔 t9 的年度披露扣非被描述性维度排除；t12 季度扣非虽然存在数值事实，原表适配器的空白候选仍阻碍期间结果采用。它们作为 X7/海尔资料准备的已知限制披露，不能把底稿返回 ok 解释为已完成取数。本次不修改这两项程序规则或数据。

主线合并范围：85a2f07 加本补充提交。重启后仍由主线执行先前 F1.4 的来源语义重新应用；本别名补充自身无需重新应用。收到上线通知后，N3 才向空闲海尔会话发送普通恢复消息：先 process_documents(force=false)，优先 t298，随后完整入库；并对伊利生产库重跑四类底稿和 comparison、扣非勾稽及原 50 个样点，全部通过才回报“伊利阶段 B 数据可冻结”。当前没有向任一入库会话发送消息，没有部署或重启。

证据：[汇总与 8 行说明变化](../docs/evidence/f14-core-alias-supplement-20261008/summary.json)、[逐表行数与数值格](../docs/evidence/f14-core-alias-supplement-20261008/table-counts.md)、[全部匹配事实及原行](../docs/evidence/f14-core-alias-supplement-20261008/alias-source-evidence.json)、[海尔扣非原始数值与来源](../docs/evidence/f14-core-alias-supplement-20261008/haier-deducted-profit.json)。原始调用返回在 tmp/f14-alias-supplement-20261008/。复现使用 scripts/replay-f14-aliases.py before/after 与 scripts/verify-f14-aliases.py；无重新应用调用。

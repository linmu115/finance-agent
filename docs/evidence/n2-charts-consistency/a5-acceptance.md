# A5 交付一致性扫描验收（观察模式）

本次实现是独立确定性扫描器和回放接口，未接入模型回馈、重试或前台告警。29 个指定历史任务全部回放；0 次 LLM 调用，0 次新材料入库。扫描输入只来自本轮已查询的来源返回与已交付产物；不读取青岛啤酒 held-out。

## 验收结论

指定 7 类缺陷的 **47/47 处已知错误**被检出。严格正确样本为 16 个任务、2,592 个已抽取带单位数值；**119 条误报，占 4.59%**。这些误报均有下表中的独立原因说明，保留完整比较对象。该比例不是对所有真实负例标注后的标准 FPR，也不代表未知项正确。

现阶段不建议启用自动回给模型。主要误报来自：计算值与披露值混淆、现值与未折现值混淆、水平与变化混淆、分部与合并范围混淆、上下文单位继承。保留观察输出供方向负责人决策。

## 接口与 N1 交接

`service.delivery_consistency.scan_delivery(answer="", tables={}, source_records=[], attachments=[])` 返回 JSON 可序列化对象。

- `answer`：本轮正文。
- `tables`：A1 `numeric_tables`，保留 columns、rows、cell_units、artifact 等。
- `source_records`：本轮实际查询工具返回的完整对象列表，支持规范记录、原始表、合并单元格、固定宽度来源文本。调用方负责项目和本轮访问范围。
- `attachments`：`{name, text, format: "md" | "csv", artifact?: 原始文件名}`。`artifact` 供下载文件带前缀时排除同一 CSV 自证。
- `checks` 含原文文件/行列、单位依据、metric/period/axes、classification、issue、完整 evidence/expected。`unmatched` 可为明确对齐不符，也可为未知，须读取 `issue` 和 `reason`。`numeric_only` 仅表示找到相同数值，不能证明语义正确。
- 分类为 exact、rounding_consistent、order_of_magnitude、wrong_cell、unmatched。使用 Decimal，保留原始小数；标准四舍五入及精确半数取偶均可识别。差额比较明确记录 absolute_gap，不评价方向因果。

CLI：

```powershell
& D:\AI\财报agent\.venv\Scripts\python.exe scripts/scan-delivery-consistency.py --input payload.json --output result.json
```

N1 adapter 只导入结果，无额外 Python 调用协议。已只读其源码，并将原文件复制到 worktree 临时隔离目录执行导入测试：`imported_observation_only`，导入对象与原 JSON 完全相等。未修改 adapter 或主目录文件。主线/N1 可将 `a5-acceptance.json`，或 CLI 的单轮结果传给 `--mainline-result`。其 destination 必须在该 adapter 所在仓库的 `data/evaluation/blind-eval-*` 中。

## 已知缺陷查全率

下面计数包括实际交付的同名历史版本，不重复扫描评测目录中没有交付清单记录的便捷副本。47 个目标只覆盖本次指定的七类缺陷，不宣称覆盖所有历史缺陷。评审答案与这些目标只进入 evaluator，不进入 scanner。

|缺陷|检出 / 已知错误处数|结果|
|---|---:|---|
|C2_forecast_x10|12/12|order_of_magnitude|
|D2_csv_RMB_bn_x10|22/22|order_of_magnitude|
|E2_sensitivity_wrong_cell|1/1|wrong_cell|
|C1_margin_7_74|1/1|unmatched|
|F2_EPS_2024|5/5|wrong_cell|
|F2_gap_1_3_vs_6_8|3/3|unmatched|
|prior_C2_csv_x100|3/3|order_of_magnitude|

F2 对照同时保留：0.83（2024E）被对应到来源 0.63；2025E 的 0.83 不报错。EV/股权价差由来源 5336/5656 与计算 5329.224677…/5649.224677…相减，未舍入约 6.775322 百万元；6.8 的披露舍入一致，1.3 不一致。C1 的 7.74 对应未舍入 7.732117966…，未将两端先舍入后相减。

## 全部回放结果

|研究|任务|分类计数|告警数|完整输出|
|---|---|---|---:|---|
|pi-cowork-acceptance-20261006|B1|{'exact': 89, 'unmatched': 26, 'wrong_cell': 1, 'order_of_magnitude': 4, 'rounding_consistent': 27}|5|[JSON](a5-runs/pi-cowork-acceptance-20261006-B1.json)|
|pi-cowork-acceptance-20261006|C1|{'exact': 86, 'unmatched': 33, 'rounding_consistent': 6, 'wrong_cell': 6}|7|[JSON](a5-runs/pi-cowork-acceptance-20261006-C1.json)|
|pi-cowork-acceptance-20261006|C2|{'order_of_magnitude': 12, 'exact': 63, 'rounding_consistent': 9, 'unmatched': 21, 'wrong_cell': 4}|17|[JSON](a5-runs/pi-cowork-acceptance-20261006-C2.json)|
|pi-cowork-acceptance-20261006|B2|{}|0|[JSON](a5-runs/pi-cowork-acceptance-20261006-B2.json)|
|pi-cowork-acceptance-20261006|F2|{'exact': 145, 'rounding_consistent': 48, 'unmatched': 74, 'wrong_cell': 9, 'order_of_magnitude': 1}|23|[JSON](a5-runs/pi-cowork-acceptance-20261006-F2.json)|
|pi-cowork-acceptance-20261006|F3|{'exact': 48, 'unmatched': 70, 'rounding_consistent': 33}|0|[JSON](a5-runs/pi-cowork-acceptance-20261006-F3.json)|
|pi-cowork-acceptance-20261006|C3|{'exact': 79, 'unmatched': 45, 'rounding_consistent': 12, 'wrong_cell': 1}|1|[JSON](a5-runs/pi-cowork-acceptance-20261006-C3.json)|
|pi-cowork-acceptance-20261006|E1|{'exact': 128, 'unmatched': 23, 'wrong_cell': 1, 'rounding_consistent': 45}|12|[JSON](a5-runs/pi-cowork-acceptance-20261006-E1.json)|
|pi-cowork-acceptance-20261006|D1|{'unmatched': 30, 'exact': 58, 'rounding_consistent': 21}|5|[JSON](a5-runs/pi-cowork-acceptance-20261006-D1.json)|
|pi-cowork-acceptance-20261006|D2|{'exact': 91, 'rounding_consistent': 51, 'unmatched': 38, 'order_of_magnitude': 22}|23|[JSON](a5-runs/pi-cowork-acceptance-20261006-D2.json)|
|pi-cowork-acceptance-20261006|E2|{'exact': 75, 'rounding_consistent': 32, 'unmatched': 32, 'wrong_cell': 2}|9|[JSON](a5-runs/pi-cowork-acceptance-20261006-E2.json)|
|pi-cowork-acceptance-20261006|E3|{'rounding_consistent': 17, 'unmatched': 119, 'exact': 60, 'wrong_cell': 16}|26|[JSON](a5-runs/pi-cowork-acceptance-20261006-E3.json)|
|pi-cowork-acceptance-20261006|D3|{'exact': 73, 'unmatched': 80, 'rounding_consistent': 29}|0|[JSON](a5-runs/pi-cowork-acceptance-20261006-D3.json)|
|pi-cowork-postfix-20261007|G1|{'exact': 86, 'rounding_consistent': 53, 'unmatched': 16, 'wrong_cell': 2}|2|[JSON](a5-runs/pi-cowork-postfix-20261007-G1.json)|
|pi-finance-generalization-20261006|A1|{'rounding_consistent': 35, 'unmatched': 44, 'wrong_cell': 2, 'exact': 70}|3|[JSON](a5-runs/pi-finance-generalization-20261006-A1.json)|
|pi-finance-generalization-20261006|B1|{'rounding_consistent': 18, 'exact': 50, 'unmatched': 35}|0|[JSON](a5-runs/pi-finance-generalization-20261006-B1.json)|
|pi-finance-generalization-20261006|C1|{'unmatched': 53, 'exact': 69, 'wrong_cell': 1}|1|[JSON](a5-runs/pi-finance-generalization-20261006-C1.json)|
|pi-finance-generalization-20261006|C2|{'rounding_consistent': 24, 'unmatched': 57, 'exact': 89, 'wrong_cell': 6, 'order_of_magnitude': 10}|19|[JSON](a5-runs/pi-finance-generalization-20261006-C2.json)|
|pi-finance-generalization-20261006|B2|{'exact': 222, 'rounding_consistent': 44, 'unmatched': 36, 'order_of_magnitude': 7, 'wrong_cell': 16}|29|[JSON](a5-runs/pi-finance-generalization-20261006-B2.json)|
|pi-finance-generalization-20261006|A2|{'exact': 90, 'rounding_consistent': 12, 'unmatched': 84, 'wrong_cell': 5, 'order_of_magnitude': 2}|12|[JSON](a5-runs/pi-finance-generalization-20261006-A2.json)|
|pi-finance-generalization-20261006|B3|{'unmatched': 63, 'exact': 67, 'rounding_consistent': 27, 'order_of_magnitude': 4, 'wrong_cell': 5}|15|[JSON](a5-runs/pi-finance-generalization-20261006-B3.json)|
|pi-finance-generalization-20261006|C3|{'unmatched': 65, 'rounding_consistent': 19, 'exact': 39, 'wrong_cell': 2}|2|[JSON](a5-runs/pi-finance-generalization-20261006-C3.json)|
|pi-finance-generalization-20261006|A3|{'exact': 35, 'unmatched': 115, 'rounding_consistent': 12}|0|[JSON](a5-runs/pi-finance-generalization-20261006-A3.json)|
|pi-finance-generalization-20261006|E1|{'exact': 38, 'unmatched': 6, 'rounding_consistent': 18, 'wrong_cell': 2}|3|[JSON](a5-runs/pi-finance-generalization-20261006-E1.json)|
|pi-finance-generalization-20261006|D1|{'rounding_consistent': 51, 'exact': 90, 'unmatched': 32, 'wrong_cell': 15}|15|[JSON](a5-runs/pi-finance-generalization-20261006-D1.json)|
|pi-finance-generalization-20261006|D2|{'exact': 76, 'rounding_consistent': 12, 'unmatched': 127, 'wrong_cell': 4, 'order_of_magnitude': 2}|11|[JSON](a5-runs/pi-finance-generalization-20261006-D2.json)|
|pi-finance-generalization-20261006|E2|{'exact': 70, 'wrong_cell': 4, 'rounding_consistent': 24, 'unmatched': 35, 'order_of_magnitude': 2}|6|[JSON](a5-runs/pi-finance-generalization-20261006-E2.json)|
|pi-finance-generalization-20261006|E3|{'rounding_consistent': 16, 'exact': 47, 'unmatched': 47, 'order_of_magnitude': 4, 'wrong_cell': 12}|16|[JSON](a5-runs/pi-finance-generalization-20261006-E3.json)|
|pi-finance-generalization-20261006|D3|{'exact': 27, 'unmatched': 120, 'rounding_consistent': 19, 'order_of_magnitude': 11}|24|[JSON](a5-runs/pi-finance-generalization-20261006-D3.json)|

B2 失败历史任务也保留回放记录；无可抽取值或无参考保持未知，不包装为通过。语义错误（例如利息收款方向）不在本扫描能力范围内。

## 正确样本与误报口径

严格正确集：cowork 评审的 financialCore、currencyAndScale、sourceAndInterpretation 均 pass；generalization 的 numerics.status=pass 且 materialNumericalError=false；另加 postfix G1。因此含 6 个 cowork、9 个 generalization、1 个 postfix。没有将金融核心已失败的任务混进正确集；C1/E1 已知解释失败也未充作正确回答。全体 29 轮仍都在上面的回放结果中。

|研究|任务|已抽取数值|误报|
|---|---|---:|---:|
|pi-cowork-acceptance-20261006|B1|147|5|
|pi-cowork-acceptance-20261006|F3|151|0|
|pi-cowork-acceptance-20261006|C3|137|1|
|pi-cowork-acceptance-20261006|D1|109|5|
|pi-cowork-acceptance-20261006|E3|212|26|
|pi-cowork-acceptance-20261006|D3|182|0|
|pi-finance-generalization-20261006|A1|151|3|
|pi-finance-generalization-20261006|A2|193|12|
|pi-finance-generalization-20261006|A3|162|0|
|pi-finance-generalization-20261006|B2|325|29|
|pi-finance-generalization-20261006|B3|166|15|
|pi-finance-generalization-20261006|C1|123|1|
|pi-finance-generalization-20261006|C3|125|2|
|pi-finance-generalization-20261006|D1|188|15|
|pi-finance-generalization-20261006|E1|64|3|
|pi-cowork-postfix-20261007|G1|157|2|

## 每条误报的定位与原因

下面按历史数值评审判定为误报。每条完整原文、单位推断以及错误比较对象可在该任务 JSON 的 `checks[索引]` 读取；说明文件为 a5-review-notes.json。

|序号|研究/任务|文件:行（check 索引）|扫描值|分类|原因|
|---:|---|---|---|---|---|
|1|pi-cowork-acceptance-20261006/B1|answer.md:26（37）|-61.293|wrong_cell|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|2|pi-cowork-acceptance-20261006/B1|ff9a44196de8-report.md:5（80）|955.192|order_of_magnitude|句子“由 A 降至 B 百万元”中的 A 没有紧邻单位，扫描器继承原报表千元而不是后半句百万元；正确金额被误报为千倍差。|
|3|pi-cowork-acceptance-20261006/B1|ff9a44196de8-report.md:5（88）|193.422|order_of_magnitude|句子“由 A 降至 B 百万元”中的 A 没有紧邻单位，扫描器继承原报表千元而不是后半句百万元；正确金额被误报为千倍差。|
|4|pi-cowork-acceptance-20261006/B1|ff9a44196de8-report.md:5（91）|164.084|order_of_magnitude|句子“由 A 降至 B 百万元”中的 A 没有紧邻单位，扫描器继承原报表千元而不是后半句百万元；正确金额被误报为千倍差。|
|5|pi-cowork-acceptance-20261006/B1|ff9a44196de8-report.md:5（94）|164.096|order_of_magnitude|句子“由 A 降至 B 百万元”中的 A 没有紧邻单位，扫描器继承原报表千元而不是后半句百万元；正确金额被误报为千倍差。|
|6|pi-cowork-acceptance-20261006/C3|dd8727f3fd9e-update_report.md:26（128）|320|wrong_cell|公式中的净现金、股数或汇率项被最近的 EV/股权价值标签吸附；这些是计算输入，不是公式结果。|
|7|pi-cowork-acceptance-20261006/D1|answer.md:3（4）|22.108|unmatched|新增 search_evidence 的摘要仅解析出上年净财务收益 3.4，正文的 22.108 被与其强行对齐；本项是同比增加额，不是净财务收益水平。|
|8|pi-cowork-acceptance-20261006/D1|answer.md:22（32）|3.425|unmatched|新增 search_evidence 的摘要仅解析出上年净财务收益 3.4，正文的 3.425 被与其强行对齐；原文 3.425 与摘要 3.4 的披露精度不同，扫描器按更精细的正文小数位比较。|
|9|pi-cowork-acceptance-20261006/D1|answer.md:22（33）|25.533|unmatched|新增 search_evidence 的摘要仅解析出上年净财务收益 3.4，正文的 25.533 被与其强行对齐；本项为本期 25.533，上年摘要不是同期间参照。|
|10|pi-cowork-acceptance-20261006/D1|7bf5d092a124-report.md:3（47）|3.425|unmatched|新增 search_evidence 的摘要仅解析出上年净财务收益 3.4，正文的 3.425 被与其强行对齐；原文 3.425 与摘要 3.4 的披露精度不同，扫描器按更精细的正文小数位比较。|
|11|pi-cowork-acceptance-20261006/D1|7bf5d092a124-report.md:3（48）|25.533|unmatched|新增 search_evidence 的摘要仅解析出上年净财务收益 3.4，正文的 25.533 被与其强行对齐；本项为本期 25.533，上年摘要不是同期间参照。|
|12|pi-cowork-acceptance-20261006/E3|46d1aa8287c0-局部更新报告.md:10（53）|626|wrong_cell|FCF 五年序列的最后一年参与终值计算，另一底稿行说明含终值字样，被标签优先级识别成终值而非末年 FCF；期间列表本身正确。|
|13|pi-cowork-acceptance-20261006/E3|46d1aa8287c0-局部更新报告.md:10（58）|563.4|wrong_cell|FCF 五年序列的最后一年参与终值计算，另一底稿行说明含终值字样，被标签优先级识别成终值而非末年 FCF；期间列表本身正确。|
|14|pi-cowork-acceptance-20261006/E3|46d1aa8287c0-局部更新报告.md:28（72）|11.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|15|pi-cowork-acceptance-20261006/E3|46d1aa8287c0-局部更新报告.md:28（74）|13.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|16|pi-cowork-acceptance-20261006/E3|9797377dd6da-新旧参数与结果.csv:2（107）|0.127|unmatched|CSV 中的更新后 WACC 为 0.127；排除同附件自证后，剩余候选只有从基准说明提取的 0.122 网格坐标，误当成更新参数的依据。|
|17|pi-cowork-acceptance-20261006/E3|9797377dd6da-新旧参数与结果.csv:12（124）|10.8912980269113089834965290946579970|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|18|pi-cowork-acceptance-20261006/E3|9797377dd6da-新旧参数与结果.csv:15（128）|9.40763954155813876107825440797074294|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|19|pi-cowork-acceptance-20261006/E3|9797377dd6da-新旧参数与结果.csv:15（129）|9.40763954155813876107825440797074294|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|20|pi-cowork-acceptance-20261006/E3|a69a1bd1c0b3-新旧参数与结果.csv:2（131）|0.127|unmatched|CSV 中的更新后 WACC 为 0.127；排除同附件自证后，剩余候选只有从基准说明提取的 0.122 网格坐标，误当成更新参数的依据。|
|21|pi-cowork-acceptance-20261006/E3|a69a1bd1c0b3-新旧参数与结果.csv:12（148）|10.8912980269113089834965290946579970|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|22|pi-cowork-acceptance-20261006/E3|a69a1bd1c0b3-新旧参数与结果.csv:15（152）|9.40763954155813876107825440797074294|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|23|pi-cowork-acceptance-20261006/E3|a69a1bd1c0b3-新旧参数与结果.csv:15（153）|9.40763954155813876107825440797074294|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|24|pi-cowork-acceptance-20261006/E3|c6f5848dd0b5-局部更新报告.md:10（169）|626|wrong_cell|FCF 五年序列的最后一年参与终值计算，另一底稿行说明含终值字样，被标签优先级识别成终值而非末年 FCF；期间列表本身正确。|
|25|pi-cowork-acceptance-20261006/E3|c6f5848dd0b5-局部更新报告.md:10（174）|563.4|wrong_cell|FCF 五年序列的最后一年参与终值计算，另一底稿行说明含终值字样，被标签优先级识别成终值而非末年 FCF；期间列表本身正确。|
|26|pi-cowork-acceptance-20261006/E3|c6f5848dd0b5-局部更新报告.md:28（188）|11.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|27|pi-cowork-acceptance-20261006/E3|c6f5848dd0b5-局部更新报告.md:28（190）|13.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|28|pi-cowork-acceptance-20261006/E3|de5dc2fa5d7d-估值差异拆解.csv:2（195）|10.8912980269113089834965290946579970|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|29|pi-cowork-acceptance-20261006/E3|de5dc2fa5d7d-估值差异拆解.csv:2（196）|0|unmatched|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|30|pi-cowork-acceptance-20261006/E3|de5dc2fa5d7d-估值差异拆解.csv:3（198）|10.3843842754049389637606230158633880|unmatched|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|31|pi-cowork-acceptance-20261006/E3|de5dc2fa5d7d-估值差异拆解.csv:3（199）|-0.5069137515063700197359060787946090|wrong_cell|两步贡献未按 WACC 第一步/FCF 第二步对齐；第一步的 -0.50691375 被拿去比较第二步 -0.97674473 和最终价格。|
|32|pi-cowork-acceptance-20261006/E3|de5dc2fa5d7d-估值差异拆解.csv:4（201）|9.40763954155813876107825440797074294|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|33|pi-cowork-acceptance-20261006/E3|ec1cf8bfb07c-估值差异拆解.csv:2（204）|10.8912980269113089834965290946579970|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|34|pi-cowork-acceptance-20261006/E3|ec1cf8bfb07c-估值差异拆解.csv:2（205）|0|unmatched|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|35|pi-cowork-acceptance-20261006/E3|ec1cf8bfb07c-估值差异拆解.csv:3（207）|10.3843842754049389637606230158633880|unmatched|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|36|pi-cowork-acceptance-20261006/E3|ec1cf8bfb07c-估值差异拆解.csv:3（208）|-0.5069137515063700197359060787946090|wrong_cell|两步贡献未按 WACC 第一步/FCF 第二步对齐；第一步的 -0.50691375 被拿去比较第二步 -0.97674473 和最终价格。|
|37|pi-cowork-acceptance-20261006/E3|ec1cf8bfb07c-估值差异拆解.csv:4（210）|9.40763954155813876107825440797074294|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|38|pi-finance-generalization-20261006/A1|answer.md:3（4）|-37.4|wrong_cell|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|39|pi-finance-generalization-20261006/A1|1d411075ba9e-report.md:4（50）|-61.293|unmatched|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|40|pi-finance-generalization-20261006/A1|1d411075ba9e-report.md:4（51）|-37.4|wrong_cell|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|41|pi-finance-generalization-20261006/A2|answer.md:42（34）|10.89|wrong_cell|独立 DCF 计算值被对齐到研报披露值。正确底稿本来就保留两套数值及差异；扫描器缺少计算值/披露值的角色区分，不能要求二者相等。|
|42|pi-finance-generalization-20261006/A2|answer.md:44（35）|1810|wrong_cell|段首“与报告列示值的差异”影响了后续列举的报告原值/加总项，1,810 或 3,527 被当成差额；它们实际是组成项。|
|43|pi-finance-generalization-20261006/A2|answer.md:44（42）|1810|wrong_cell|段首“与报告列示值的差异”影响了后续列举的报告原值/加总项，1,810 或 3,527 被当成差额；它们实际是组成项。|
|44|pi-finance-generalization-20261006/A2|answer.md:44（43）|3527|wrong_cell|段首“与报告列示值的差异”影响了后续列举的报告原值/加总项，1,810 或 3,527 被当成差额；它们实际是组成项。|
|45|pi-finance-generalization-20261006/A2|4e79f08298ad-report.md:11（141）|10.89|wrong_cell|独立 DCF 计算值被对齐到研报披露值。正确底稿本来就保留两套数值及差异；扫描器缺少计算值/披露值的角色区分，不能要求二者相等。|
|46|pi-finance-generalization-20261006/A2|4e79f08298ad-report.md:11（142）|1810|order_of_magnitude|后文引用研报的 1,810/5,336 没有逐项重复单位，扫描器继承之前预测部分单位，未沿用当段的 RMB mn，产生数量级误报。|
|47|pi-finance-generalization-20261006/A2|4e79f08298ad-report.md:11（144）|5336|order_of_magnitude|后文引用研报的 1,810/5,336 没有逐项重复单位，扫描器继承之前预测部分单位，未沿用当段的 RMB mn，产生数量级误报。|
|48|pi-finance-generalization-20261006/A2|f538bdcaa0e5-dcf_base_inputs_and_pv.csv:2（184）|256.6844919786096|unmatched|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|49|pi-finance-generalization-20261006/A2|f538bdcaa0e5-dcf_base_inputs_and_pv.csv:3（186）|406.70943470566004|unmatched|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|50|pi-finance-generalization-20261006/A2|f538bdcaa0e5-dcf_base_inputs_and_pv.csv:4（188）|418.4166038447059|unmatched|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|51|pi-finance-generalization-20261006/A2|f538bdcaa0e5-dcf_base_inputs_and_pv.csv:5（190）|374.8133208522298|unmatched|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|52|pi-finance-generalization-20261006/A2|f538bdcaa0e5-dcf_base_inputs_and_pv.csv:6（192）|352.05462055716987|unmatched|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|53|pi-finance-generalization-20261006/B2|answer.md:27（22）|0.09|order_of_magnitude|目标价差约 HK$0.09 被识别为每股价格水平；它实际是 8.97 与 8.881 的差额，非价格本身。|
|54|pi-finance-generalization-20261006/B2|answer.md:57（48）|18.087|wrong_cell|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|55|pi-finance-generalization-20261006/B2|answer.md:57（49）|35.205|wrong_cell|独立 DCF 计算值被对齐到研报披露值。正确底稿本来就保留两套数值及差异；扫描器缺少计算值/披露值的角色区分，不能要求二者相等。|
|56|pi-finance-generalization-20261006/B2|10d1bf7de39a-DCF复算桥接.csv:2（71）|2.5668449197860963|unmatched|现值_RMB_亿元列是当年 FCF 折现后的金额；扫描器只采用 FCF 行名，未保留现值角色，与原始当年现金流比较产生误报。|
|57|pi-finance-generalization-20261006/B2|10d1bf7de39a-DCF复算桥接.csv:3（73）|4.0670943470566|wrong_cell|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|58|pi-finance-generalization-20261006/B2|10d1bf7de39a-DCF复算桥接.csv:4（75）|4.184166038447059|wrong_cell|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|59|pi-finance-generalization-20261006/B2|10d1bf7de39a-DCF复算桥接.csv:5（77）|3.7481332085222983|unmatched|现值_RMB_亿元列是当年 FCF 折现后的金额；扫描器只采用 FCF 行名，未保留现值角色，与原始当年现金流比较产生误报。|
|60|pi-finance-generalization-20261006/B2|10d1bf7de39a-DCF复算桥接.csv:6（79）|3.5205462055716987|wrong_cell|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|61|pi-finance-generalization-20261006/B2|10d1bf7de39a-DCF复算桥接.csv:7（81）|35.205462055716986|unmatched|不同脚本以二进制浮点输出的同一终值现值在最后几位存在约 1e-13 百万元差异；按字符串全部小数位比较导致误报，展示精度和金融结论一致。|
|62|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:5（112）|8.30|order_of_magnitude|EPS 乘 10 倍 PE 后的人民币每股价值 8.30 沿用了前文 EPS 标签，因此被误判成 EPS 放大 10 倍；实际是正确估值结果。|
|63|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（116）|1|order_of_magnitude|折现说明中的期数常量 1 被继承为 FCF 金额单位；该数字是公式/期数，不是金额。|
|64|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（118）|320|wrong_cell|公式中的净现金、股数或汇率项被最近的 EV/股权价值标签吸附；这些是计算输入，不是公式结果。|
|65|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（119）|555|wrong_cell|公式中的净现金、股数或汇率项被最近的 EV/股权价值标签吸附；这些是计算输入，不是公式结果。|
|66|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（120）|1.07|unmatched|公式中的净现金、股数或汇率项被最近的 EV/股权价值标签吸附；这些是计算输入，不是公式结果。|
|67|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（127）|1|order_of_magnitude|无“敏感性/网格”明确邻词的 g 坐标列表被当成单一永续增长率参数比较；1%/2%/3% 是网格取值。|
|68|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（128）|2|order_of_magnitude|无“敏感性/网格”明确邻词的 g 坐标列表被当成单一永续增长率参数比较；1%/2%/3% 是网格取值。|
|69|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:7（129）|3|order_of_magnitude|无“敏感性/网格”明确邻词的 g 坐标列表被当成单一永续增长率参数比较；1%/2%/3% 是网格取值。|
|70|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:9（131）|3527|wrong_cell|PV终值的写法未识别成终值现值，被识别成未折现终值；报告引用 3,527 正确。|
|71|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:9（133）|5656|wrong_cell|“权益价值/权益”的别名未识别，沿用前面的 EV 标签；股权价值含净现金，与 EV 本来不同。|
|72|pi-finance-generalization-20261006/B2|6b9034d7a256-report.md:9（135）|10.6|wrong_cell|WACC 参数讨论中的风险溢价 10.6% 沿用了 WACC 标签；风险溢价并不是 WACC。|
|73|pi-finance-generalization-20261006/B2|914384ca8420-report.md:7（197）|8.30|order_of_magnitude|EPS 乘 10 倍 PE 后的人民币每股价值 8.30 沿用了前文 EPS 标签，因此被误判成 EPS 放大 10 倍；实际是正确估值结果。|
|74|pi-finance-generalization-20261006/B2|914384ca8420-report.md:9（210）|56.4922|wrong_cell|“股权价值加净现金后为 56.4922”中的结果沿用了最近的净现金标签；该值实际是股权价值。|
|75|pi-finance-generalization-20261006/B2|914384ca8420-report.md:11（217）|56.56|wrong_cell|“权益价值/权益”的别名未识别，沿用前面的 EV 标签；股权价值含净现金，与 EV 本来不同。|
|76|pi-finance-generalization-20261006/B2|914384ca8420-report.md:11（219）|18.0868|wrong_cell|现值 PV/显式 FCF 现值与未折现 FCF 被同一个 fcf 指标标签合并；同期间的折现后金额本来应不同。|
|77|pi-finance-generalization-20261006/B2|914384ca8420-report.md:11（220）|35.2055|wrong_cell|独立 DCF 计算值被对齐到研报披露值。正确底稿本来就保留两套数值及差异；扫描器缺少计算值/披露值的角色区分，不能要求二者相等。|
|78|pi-finance-generalization-20261006/B2|914384ca8420-report.md:11（221）|10.6|wrong_cell|WACC 参数讨论中的风险溢价 10.6% 沿用了 WACC 标签；风险溢价并不是 WACC。|
|79|pi-finance-generalization-20261006/B2|eeb7b27e0b13-dcf_bridge.csv:7（317）|3520.5462055716985|unmatched|不同脚本以二进制浮点输出的同一终值现值在最后几位存在约 1e-13 百万元差异；按字符串全部小数位比较导致误报，展示精度和金融结论一致。|
|80|pi-finance-generalization-20261006/B2|eeb7b27e0b13-dcf_bridge.csv:8（318）|1808.6784719383752|unmatched|独立 DCF 计算值被对齐到研报披露值。正确底稿本来就保留两套数值及差异；扫描器缺少计算值/披露值的角色区分，不能要求二者相等。|
|81|pi-finance-generalization-20261006/B2|eeb7b27e0b13-dcf_bridge.csv:10（320）|5649.224677510074|wrong_cell|独立 DCF 计算值被对齐到研报披露值。正确底稿本来就保留两套数值及差异；扫描器缺少计算值/披露值的角色区分，不能要求二者相等。|
|82|pi-finance-generalization-20261006/B3|answer.md:20（24）|11.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|83|pi-finance-generalization-20261006/B3|answer.md:20（26）|13.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|84|pi-finance-generalization-20261006/B3|answer.md:20（27）|1|order_of_magnitude|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|85|pi-finance-generalization-20261006/B3|answer.md:20（29）|3|order_of_magnitude|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|86|pi-finance-generalization-20261006/B3|answer.md:20（30）|90|unmatched|90% 是 FCF 缩放因子，扫描器沿用了前文 WACC 标签；维度虽都是比例，参数语义不同。|
|87|pi-finance-generalization-20261006/B3|answer.md:20（31）|12.7|wrong_cell|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|88|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:5（45）|10.8913|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|89|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:7（51）|11.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|90|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:7（53）|13.2|unmatched|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|91|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:7（54）|1|order_of_magnitude|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|92|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:7（56）|3|order_of_magnitude|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|93|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:7（57）|90|unmatched|90% 是 FCF 缩放因子，扫描器沿用了前文 WACC 标签；维度虽都是比例，参数语义不同。|
|94|pi-finance-generalization-20261006/B3|355c233e9ebd-report.md:7（58）|12.7|wrong_cell|敏感性网格、基准参数和更新基准在同段出现；扫描器把从基准行提取的单一坐标当成完整网格，或把 12.7% 更新基准放进旧网格比较。坐标/参数角色未完整区分。|
|95|pi-finance-generalization-20261006/B3|e53b95678c10-局部更新_参数结果差异.csv:15（155）|10.891298026911315|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|96|pi-finance-generalization-20261006/B3|e53b95678c10-局部更新_参数结果差异.csv:17（157）|10.38438427540494|wrong_cell|文件名或整行包含“差异/变动”，扫描器将同表的每股价值水平、基准零贡献与变化列混为一个角色；应按单元格列义区分。|
|97|pi-finance-generalization-20261006/C1|ffc8241fbf90-report.md:27（101）|102.791|wrong_cell|合并净利润被对齐到来源的 adjusted net profit（非 HKFRS）摘要；来源摘要年度也未与 2025H1 合并口径完整对齐。|
|98|pi-finance-generalization-20261006/C3|7cb70f2cd4d1-report.md:21（50）|10.3844|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|99|pi-finance-generalization-20261006/C3|7cb70f2cd4d1-report.md:22（53）|9.4076|wrong_cell|旧值、中间值、新值的行标签没有完整对齐。排除同附件自证后，选中了另一阶段的每股价值；该数值在原正确底稿中属于当前阶段。|
|100|pi-finance-generalization-20261006/D1|answer.md:3（4）|-37.4|wrong_cell|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|101|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:5（46）|-37.4|wrong_cell|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|102|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:61（132）|16.78|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|103|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:61（133）|130.80|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|104|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:61（134）|5.72|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|105|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:61（135）|1.22|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|106|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:61（136）|-41.18|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|107|pi-finance-generalization-20261006/D1|550721fba8a2-report.md:61（137）|-42.15|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|108|pi-finance-generalization-20261006/D1|8986c0886525-bridge.csv:2（156）|16.776|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|109|pi-finance-generalization-20261006/D1|8986c0886525-bridge.csv:2（157）|130.795|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|110|pi-finance-generalization-20261006/D1|8986c0886525-bridge.csv:2（158）|5.723|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|111|pi-finance-generalization-20261006/D1|8986c0886525-bridge.csv:2（159）|1.216|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|112|pi-finance-generalization-20261006/D1|8986c0886525-bridge.csv:2（160）|-41.175|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|113|pi-finance-generalization-20261006/D1|8986c0886525-bridge.csv:2（161）|-42.147|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|114|pi-finance-generalization-20261006/D1|f1e817071807-compare.csv:2（178）|-37.35|wrong_cell|同比减少金额/增长率被归到净利润水平；候选还包含调整后净利率。应区分水平、同比和调整后口径，当前语义标签未分开。|
|115|pi-finance-generalization-20261006/E1|answer.md:19（21）|45.4|wrong_cell|品牌业务毛利率 45.4%/35.3% 被对齐到集团毛利率；业务分部与合并范围未区分。|
|116|pi-finance-generalization-20261006/E1|answer.md:19（22）|35.3|wrong_cell|品牌业务毛利率 45.4%/35.3% 被对齐到集团毛利率；业务分部与合并范围未区分。|
|117|pi-finance-generalization-20261006/E1|answer.md:21（23）|25.533|unmatched|当前标签只对齐到来源摘要的上年净财务收益 3.4，未把本期 25.533 与 2025H1 明确绑定；查询来源中摘要与报表期间对应不足。|
|118|pi-cowork-postfix-20261007/G1|b108c486510e-report.md:9（119）|16.776|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|
|119|pi-cowork-postfix-20261007/G1|b108c486510e-report.md:9（120）|5.723|wrong_cell|现金桥同一行/同一句中的经营产生现金、利息、税额、最终 CFO 没有分别识别。扫描器统一用行标签 CFO 比较组成项，造成错格误报。|

## 验证和复现

- 服务全回归 533 项：523 通过、9 跳过（主解释器没有 Matplotlib，绘图专项在独立环境已验证）、1 项基线失败。失败为 `test_analysis_queued_race_failure_persistence_and_timeout_contract`，期望隐藏异常正文而基线实际保留正文；在 `ced0cd5` 临时副本单独复现相同失败。未改动本轮以外的异常契约。
- 最新 A5 专项 13 项通过；A3 绘图专项 9 项、A1/运行返回集成 3 项此前通过。
- N1 adapter 原样导入测试通过。读取 adapter 的原文件及复制执行均为只读主目录；结果仅写 worktree 临时目录。
- 回放命令：`python scripts/replay-harness-a5.py --source-root D:\AI\财报agent`。active 会话和分析运行会先复制到 `.tmp/charts-consistency/a5`；只读取复制件，不执行历史分析脚本。
- 独立评测命令：`python scripts/evaluate-harness-a5.py --source-root D:\AI\财报agent`。这一步才读取历史 judge/reviews 与人工误报说明。
- 依赖使用主目录 .venv 的 Python 绝对路径，无新增产品依赖。未操作 3001、未关闭 Docker、未执行付费模型调用。

## 与 spec 的边界

全部指定范围和只观察要求已实现。自动“回给模型一次”完全未启用。来源回放包含 query_financial_data、query_research_records、get_source_page/table、search_evidence、get_data_catalog 和 calculate_financial_metrics 的本轮返回；不会把模型自写 research memo 当作独立原始来源来证明同一结论。自由文本逐句语义、分部、估值方法及阶段对齐仍有上述 119 条误报；这一限制是回放观察结果，未隐藏或删除难例。CSV 本身是 A1 参考时，会排除自身作为唯一正确性证据，避免同一错误左右互证。

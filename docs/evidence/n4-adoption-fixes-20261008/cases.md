# 逐题采用与结果核对

本轮代码 `47bf960ab0f51e35e9d47cd589232af8ef7c4971`，开发基线 `58a903c`。旧轮 `7524cca` 的数据副本、问题、模型和低/高推理配置保持一致；没有重新入库。这是研发预检，不是正式盲评。

数值绑定按最终回答中绑定展开的财务数值出现次数统计；整表按非空数值格计，排除年份、季度、页码、序号、ID和URL。手写数值包括抄原文和抄计算结果，不等于错误。任务完成单独检查核心问题、数值与口径，不用绑定率替代。

## Q1-financial

伊利 2024 年业绩为什么下滑？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/23 → 14/20（70.0%）；手写 23 → 6；请求 6 → 5；本轮输入 99,883 / 输出 1,761。

[原始回答](Q1-financial/answer.md) · [模型模板](Q1-financial/template.md) · [数值与调用清单](Q1-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q1-financial/app-data/audit/4aff52b9-c9db-4b85-b861-9d310f58a825.jsonl)

get_data_catalog → financial_workpaper[variance_attribution] → search_evidence → get_artifact → get_source_page → get_source_page → search_evidence → get_source_page

原始标签 {}；宿主呈现标签 {"【推论/分析】": 11, "【事实/数据】": 7}。

- `variance_attribution` periods=`["2024FY", "2023FY"]`，原始审计第 22 行。
- 底稿回包：`variance_attribution` ok；{"current": "2024-FY", "comparison": "2023-FY"}。

完整回答主要拖累、抵消项、原文原因与未解释残差；没有把桥接计算当唯一因果。

- 6 个手写数值仍保留，主要为原文增速及减值细项，未见数值错误。
- 减少后直接粘贴负变化额，措辞形成“减少 -…”；数值与方向没有反转。
- 自动标签切在加粗标题句的结束星号之前，事实标签视觉上进入前一句加粗标题，需修正句子分割保留关闭标记。

Q1: variance_attribution periods=[2024FY,2023FY] 正常归一；get_artifact(delivery.id, drivers_evidence.csv) 成功；最终主要贡献和59.9508百万元残差使用绑定。对照伊利PDF18/19/25/82/210/211。

无工具或绑定错误事件。

## Q1-prepared

伊利 2024 年业绩为什么下滑？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/18 → 0/19（0.0%）；手写 18 → 19；请求 11 → 13；本轮输入 247,560 / 输出 3,371。

[原始回答](Q1-prepared/answer.md) · [模型模板](Q1-prepared/template.md) · [数值与调用清单](Q1-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q1-prepared/app-data/audit/201eccb1-338a-4866-bdff-240f0e5d1f65.jsonl)

list_documents → get_data_catalog → search_evidence → get_document_index → get_source_page → get_source_page → get_source_page → get_source_page → query_financial_data → get_source_page → get_source_page → get_source_page → get_source_page → search_evidence → search_evidence → run_analysis → get_analysis_status → run_analysis → get_analysis_status

原始标签 {}；宿主呈现标签 {"【推论/分析】": 27}。


回答了销量/售价、液态奶、冷饮和商誉减值的主要下滑因素；未给主要抵消项的定量分解或残差。

- 19 次数值均手写；根据合并净利润计算同比，主体口径未见混用。
- 未提供各因素完整利润桥，仍保留其他项目及经济因果边界。
- 出处多用“年报第X页”，完整 document_id 只放在文末，宿主无法把前面各句识别为已定位事实，最终默认分析。

伊利PDF18/19/20/91/184/211；减值增量31.50亿元与合并净利润下降18.21亿元符合披露。

工具/绑定失败（用量已包含）：`{"type": "tool_return_failure", "line": 153, "name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 10, in <module>\n    deliver()\n  File \"/input/analysis_report.py\", line 529, in deliver\n    compiled = compile_report(report, records, models)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 298, in compile_report\n    for key, cell in row.items():\n                     ^^^^^^^^^\nAttributeError: 'str' object has no attribute 'items'\n"}`

## Q2-financial

伊利 2024 年利润和现金流走势一致吗，有没有值得警惕的地方？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/27 → 0/17（0.0%）；手写 27 → 17；请求 9 → 7；本轮输入 323,855 / 输出 2,859。

[原始回答](Q2-financial/answer.md) · [模型模板](Q2-financial/template.md) · [数值与调用清单](Q2-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q2-financial/app-data/audit/36d96871-7f06-4669-bd5b-2dd493d86fcc.jsonl)

get_data_catalog → financial_workpaper[anomaly_signals] → financial_workpaper[period_analysis] → financial_workpaper[statement_analysis] → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page

原始标签 {"【推论/分析】": 1}；宿主呈现标签 {"【推论/分析】": 15, "【事实/数据】": 1}。

- `anomaly_signals` periods=`["2024-FY", "2023-FY"]`，原始审计第 30 行。
- `period_analysis` periods=`["2024-FY", "2023-FY"]`，原始审计第 32 行。
- `statement_analysis` periods=`["2024-FY", "2023-FY"]`，原始审计第 34 行。
- 底稿回包：`statement_analysis` ok；{"current": "2024-FY", "comparison": "2023-FY"}。
- 底稿回包：`period_analysis` ok；{"current": "2024-FY", "comparison": "2023-FY"}。
- 底稿回包：`anomaly_signals` ok；{"current": "2024-FY", "comparison": "2023-FY"}。

基本趋势和警示已答；直接采用异常雷达，并补季度与整体底稿，期间无错。

- 17次数值仍全手写，虽然工具已经返回可粘贴绑定。说明关键值交接提高采用但未保证绑定。
- 仍遗漏PDF19的春节备货/预收经销商货款解释；称不能确认减值具体资产及原因，但项目原文PDF25/82/211已披露澳优等项目，应区分未读取与未披露。
- 没有给年度CFO绝对额或期末现金余额；核心走势、比率和季度金额正确。

伊利PDF8/9/91/92/94：合并利润-17.7%、CFO+18.9%、现金转换2.57/1.78，Q4归母-24.16/扣非-24.98/CFO78.70亿元正确。工具序列anomaly_signals→period_analysis→statement_analysis。

无工具或绑定错误事件。

## Q2-prepared

伊利 2024 年利润和现金流走势一致吗，有没有值得警惕的地方？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/12 → 0/16（0.0%）；手写 12 → 16；请求 9 → 11；本轮输入 124,441 / 输出 3,671。

[原始回答](Q2-prepared/answer.md) · [模型模板](Q2-prepared/template.md) · [数值与调用清单](Q2-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q2-prepared/app-data/audit/b11aedbc-f839-4e0c-be55-3905baf4f908.jsonl)

list_documents → get_data_catalog → search_evidence → get_document_index → get_source_table → get_source_table → get_source_page → get_source_page → get_source_page → run_analysis → get_analysis_status → run_analysis → get_analysis_status → run_analysis

原始标签 {}；宿主呈现标签 {"【推论/分析】": 23}。


利润下降、CFO上升和扣非走弱回答完整；明确CFO/归母不是同口径比率，未重现旧轮混用母公司现金余额。

- 16次数值均手写，无A1绑定。
- 未说明原文第19页春节备货/预收经销商货款的管理层现金流解释；已说明采购现金支出减少的直接法因素及不能归于单一原因。
- 来源普遍只列页码或页码列表，宿主默认显示分析；模型没有主动标注。

伊利PDF7/18/94；CFO/归母2.57、1.75与披露原值相符，合并投资净流出327.1、筹资净流出72.8亿元正确。

工具/绑定失败（用量已包含）：`{"type": "tool_return_failure", "line": 111, "name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 7, in <module>\n    runpy.run_path('/input/analysis.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/analysis.py\", line 4, in <module>\n    save_table('trend',rows,columns={'metric':{'type':'text'},'v24':{'unit':'亿元/倍'},'v23':{'unit':'亿元/倍'},'growth':{'unit':'%'}})\nTypeError: save_table() got multiple values for argument 'columns'\n"}`

## Q3-financial

扣非后看伊利 2024 年盈利质量如何？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 19/21 → 0/25（0.0%）；手写 2 → 25；请求 3 → 12；本轮输入 450,045 / 输出 3,792。

[原始回答](Q3-financial/answer.md) · [模型模板](Q3-financial/template.md) · [数值与调用清单](Q3-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q3-financial/app-data/audit/9c53157b-6b4e-4bd6-a774-826d1ee939dd.jsonl)

get_data_catalog → list_documents → get_research_ingestion_status → financial_workpaper[statement_analysis] → financial_workpaper[anomaly_signals] → financial_workpaper[comparison] → query_financial_data → get_document_index → search_evidence → get_source_table → get_financial_metrics → get_source_table → get_source_table → query_financial_data → search_evidence → get_source_page → get_source_page → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → search_evidence → get_source_table → get_source_table → calculate_financial_metrics

原始标签 {"【观点】": 1, "【推论/分析】": 1}；宿主呈现标签 {"【观点】": 2, "【推论/分析】": 16, "【事实/数据】": 1, "【推论】": 2}。

- `statement_analysis` periods=`["2024-FY", "2023-FY"]`，原始审计第 38 行。
- `anomaly_signals` periods=`["2024-FY", "2023-FY"]`，原始审计第 40 行。
- `comparison` periods=`["2024-FY", "2023-FY"]`，原始审计第 42 行。
- 底稿回包：`comparison` insufficient_evidence；"请指定 company 或 document_id，当前口径主体为：[]"。
- 底稿回包：`statement_analysis` insufficient_evidence；"请指定 company 或 document_id，当前口径主体为：[]"。
- 底稿回包：`anomaly_signals` insufficient_evidence；"请指定 company 或 document_id，当前口径主体为：[]"。

核心扣非问题最终由原文/计算工具完成；三次底稿均因公司简称过滤返回insufficient_evidence，未取得任何新关键值。

- 25个财务数值全部手写；本题没有拿到关键值，不能把原因归为模型读到关键值后不愿绑定。
- S/A/comparison三次底稿都传company=伊利股份，而取数未利用已登记别名，返回当前口径主体为空；此外空文档ID状态查询与指标别名查询各抛错一次。
- 原文读取补齐缺项使请求3→12、输入24,621→450,045；旧轮少用量伴随任务未完成，不能据此宣称修复成本恶化15倍。
- CFO/扣非归母3.62倍非同口径现金转换，回答给出应计/现金边界；处置交易背景在项目PDF18/210可得，但本次未进一步定位。

伊利PDF7/8/9/82/91/212核对，关键财务金额和比例正确；原始数字扫描中的9个p.页码已剔除，原有基准统计不变。

工具/绑定失败（用量已包含）：`{"type": "tool_error", "line": 26, "data": {"name": "get_research_ingestion_status", "toolCallId": "call_KXaamArjrFJhhJoAmmEVapJS|fc_03c5e757ba29330f016ac7260f877887d0a653137522a71eda", "message": "document_not_found_in_project"}}`

工具/绑定失败（用量已包含）：`{"type": "tool_error", "line": 84, "data": {"name": "get_financial_metrics", "toolCallId": "call_PyVPk54ogM95g2su0cQiEsPu|fc_03c5e757ba29330f016ac7262b6c5087d0abac03cd15440725", "message": "unknown_metric_use_data_catalog"}}`

## Q3-prepared

扣非后看伊利 2024 年盈利质量如何？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 7/19 → 0/32（0.0%）；手写 12 → 32；请求 10 → 10；本轮输入 138,196 / 输出 3,438。

[原始回答](Q3-prepared/answer.md) · [模型模板](Q3-prepared/template.md) · [数值与调用清单](Q3-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q3-prepared/app-data/audit/22a9c2c6-3ed2-4e70-86a2-60c85a26bc6e.jsonl)

list_documents → get_data_catalog → search_evidence → get_document_index → get_source_table → get_source_table → get_source_table → search_evidence → run_analysis → get_analysis_status → run_analysis → get_analysis_status → search_evidence

原始标签 {}；宿主呈现标签 {"【推论/分析】": 21}。


全年扣非、非经常损益占比和扣非回报率均已回答；关键金额无误。

- 32次财务数值全部手写，上次有7次绑定，本次没有。
- CFO/扣非归母3.62、1.82倍只是参考覆盖比率，未明确说明合并现金流与归母扣非的主体差异。
- 自由分析脚本一次失败，计入用量；没有被包装为无错完成。

伊利PDF7/8/9/82/211；60.11/100.26、24.42/4.02亿元以及0.95/1.57、11.24%/19.36%符合披露。

工具/绑定失败（用量已包含）：`{"type": "tool_return_failure", "line": 81, "name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 7, in <module>\n    runpy.run_path('/input/analysis.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/analysis.py\", line 20, in <module>\n    save_table('quality', rows)\nTypeError: save_table() missing 1 required positional argument: 'rows'\n"}`

## Q4-financial

伊利 2024 年 Q4 表现怎么样？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/8 → 0/16（0.0%）；手写 8 → 16；请求 6 → 8；本轮输入 108,059 / 输出 2,230。

[原始回答](Q4-financial/answer.md) · [模型模板](Q4-financial/template.md) · [数值与调用清单](Q4-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q4-financial/app-data/audit/ecea83ee-3d1b-4546-9e78-e8e706ccdea0.jsonl)

list_documents → get_data_catalog → financial_workpaper[period_analysis] → search_evidence → get_financial_metrics → get_document_index → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → get_source_page → search_evidence

原始标签 {"【来源：`d84573bf6b584e7e874faa4c6adf454a`，年报第8页】": 1, "【来源：`d84573bf6b584e7e874faa4c6adf454a`，年报第7页】": 1, "【来源：同上年报第82、211页】": 1}；宿主呈现标签 {"【推论/分析】": 12, "【事实/数据】": 2, "【来源：`d84573bf6b584e7e874faa4c6adf454a`，年报第8页】": 1, "【来源：`d84573bf6b584e7e874faa4c6adf454a`，年报第7页】": 1, "【来源：同上年报第82、211页】": 1}。

- `period_analysis` periods=`["2024Q4"]`，原始审计第 34 行。
- 底稿回包：`period_analysis` insufficient_evidence；"请指定 company 或 document_id，当前口径主体为：[]"。

选对period_analysis、2024Q4写法合法，但company=伊利股份过滤导致底稿未生成；后续原文与计算工具完成季度核心回答。

- 16次数值全手写。实际没有取得期间底稿，不能把后续7次计算误报为重复已有期间结果。
- get_financial_metrics使用未注册指标别名报错一次，与期间/交付ID无关。
- 公司登记别名未被load_facts使用，是参数到结果交接的新阻塞点；已保留原始失败，并追加别名修复及两题补测。

原始periods=[2024Q4]、company=伊利股份；回包insufficient_evidence：当前口径主体为[]。原文PDF7/8/82/211支撑最终季度金额和同比边界。

工具/绑定失败（用量已包含）：`{"type": "tool_error", "line": 52, "data": {"name": "get_financial_metrics", "toolCallId": "call_dPAnCXeJnsN8ANEYL8WvKClY|fc_0a26ffed91124a3f016ac7277399f087d091fe5cf1f1f14f25", "message": "unknown_metric_use_data_catalog"}}`

## Q4-prepared

伊利 2024 年 Q4 表现怎么样？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/12 → 0/15（0.0%）；手写 12 → 15；请求 9 → 10；本轮输入 151,749 / 输出 3,245。

[原始回答](Q4-prepared/answer.md) · [模型模板](Q4-prepared/template.md) · [数值与调用清单](Q4-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q4-prepared/app-data/audit/02f7b329-aa12-4c46-8c5f-ae24bbbadf3d.jsonl)

list_documents → get_data_catalog → query_financial_data → search_evidence → get_source_page → search_evidence → search_evidence → search_evidence → run_analysis → get_analysis_status → run_analysis → get_analysis_status → get_source_page

原始标签 {"【计算】": 1, "【分析】": 1}；宿主呈现标签 {"【推论/分析】": 23, "【计算】": 1, "【分析】": 1}。


季度四项金额、环比和净利率已答，避免把全年原因直接归给Q4；但多算的全年收入占比存在分母口径错误。

- 15次数值均手写。
- Q4占全年营收写23.0%，脚本分母为1157.806648亿元并标称PDF7；PDF7营业收入实为1153.9331097669亿元，同口径占比应23.104%左右，保留一位为23.1%。
- 首次分析表把“指标/数值/口径”填作单位而失败；随后改print脚本完成，全部用量保留。

直接读取冻结seed的伊利PDF7与8并核对原始run_analysis参数，Q4营业收入266.6037653126亿元。财务数字和分母不能只凭脚本成功判为正确。

工具/绑定失败（用量已包含）：`{"type": "tool_return_failure", "line": 81, "name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 10, in <module>\n    deliver()\n  File \"/input/analysis_report.py\", line 529, in deliver\n    compiled = compile_report(report, records, models)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 311, in compile_report\n    try: col['unit'], named = canonical_unit(declared)\n                              ^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 76, in canonical_unit\n    raise ValueError(f'未知单位 {text!r}。{ACCEPTED}')\nValueError: 未知单位 '指标'。金额：元/千元/万元/百万元/亿元/十亿元、thousand/million/billion，可带币种（人民币百万元、RMB million、亿港元）；每股：元/股、人民币/股；股数：股/万股/百万股/亿股；比例：ratio（0.10=10%）、%；百分点：个百分点、百分点、pp；倍；个；天\n"}`

## Q5-financial

瑞和这半年报有没有口径调整或异常？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/15 → 5/10（50.0%）；手写 15 → 5；请求 10 → 10；本轮输入 258,851 / 输出 3,553。

[原始回答](Q5-financial/answer.md) · [模型模板](Q5-financial/template.md) · [数值与调用清单](Q5-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q5-financial/app-data/audit/463f04b0-eb01-41fc-be1c-3d9b9b599ef2.jsonl)

list_documents → get_data_catalog → financial_workpaper[basis_changes] → financial_workpaper[anomaly_signals] → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_artifact → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page

原始标签 {}；宿主呈现标签 {"【推论/分析】": 17, "【事实/数据】": 4}。

- `basis_changes` periods=`"2025-H1"`，原始审计第 34 行。
- `anomaly_signals` periods=`"2025-H1"`，原始审计第 36 行。
- 底稿回包：`basis_changes` ok；{"current": "2025-H1", "comparison": "2024-H1"}。
- 底稿回包：`anomaly_signals` ok；{"current": "2025-H1", "comparison": "2024-H1"}。

basis_changes与anomaly_signals均用单个2025-H1，自动补齐比较期；交付ID读取report.md成功，已回答无已识别数值重述及现金流/FVTPL/融资观察。

- 本题5/10个回答数值绑定，其中1个是“已识别调整行数0”的底稿元数据；剔除此项为4/9，不能把它当调整金额为零。
- 信用损失89%在第47页是按逾期天数分组的>12个月预期损失率，答案称“逾一年账龄对应账龄桶”不够准确，未区分第46页发票账龄。
- 出现1次既有估值章节校验修复：普通FVTPL估值讨论触发假设/风险/适用范围要求，补答后反而多出声明性小节。不是本轮新增审批。
- 未给净利润41.098百万元与FVTPL收益的定量对照，仅给收益金额和现金转换；筛查重点正确，深度弱于上轮具体税前剔除计算。

瑞和PDF28/32/33/41/45/47。get_artifact(delivery.id,report.md)成功；期间和ID相关错误均为0。现金转换-0.75、应计22.33%、信用减值变动323.36%、识别融资负债38.04%来自绑定表。

工具/绑定失败（用量已包含）：`{"type": "answer_binding_error", "line": 902, "data": {"message": "估值或投资判断缺少有内容的小节：假设 / 风险 / 适用范围。保留已核对数值并补全；资料不足明确说明。", "code": "answer_contract_error"}}`

## Q5-prepared

瑞和这半年报有没有口径调整或异常？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/14 → 0/18（0.0%）；手写 14 → 18；请求 7 → 12；本轮输入 289,714 / 输出 3,921。

[原始回答](Q5-prepared/answer.md) · [模型模板](Q5-prepared/template.md) · [数值与调用清单](Q5-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q5-prepared/app-data/audit/4ae9f9b4-1314-4886-9a7f-d738afaa4a40.jsonl)

list_documents → get_document → get_data_catalog → search_evidence → get_document_index → get_source_table → get_source_table → get_source_table → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → run_analysis → get_analysis_status → run_analysis → get_analysis_status

原始标签 {}；宿主呈现标签 {"【推论/分析】": 27}。


回答无重大会计政策变更，并识别FVTPL、业务结构、应收与流动性问题；存在两处口径问题。

- 18次数值全手写。
- 把发票账龄>1年的65.272百万元写作逾期>12个月，并接上逾期桶89%损失率；真正逾期>12个月为65.202百万元。该错误与旧轮同类。
- 从税后净利润41.098减税前FVTPL收益63.015，得到-21.917百万元，虽写“静态/非公司调整后”，仍未说明税效未调整；若用同税前口径，应为40.931-63.015=-22.084百万元。
- 两次自由分析交付脚本失败，相关用量保留。

瑞和PDF28/32/33/38/41/46/47。对照发票账龄与逾期分组原表；公允收益与税前、税后利润不可不加说明直接混作经常性净利润。

工具/绑定失败（用量已包含）：`{"type": "tool_return_failure", "line": 183, "name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 10, in <module>\n    deliver()\n  File \"/input/analysis_report.py\", line 529, in deliver\n    compiled = compile_report(report, records, models)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 311, in compile_report\n    try: col['unit'], named = canonical_unit(declared)\n                              ^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 76, in canonical_unit\n    raise ValueError(f'未知单位 {text!r}。{ACCEPTED}')\nValueError: 未知单位 '项目'。金额：元/千元/万元/百万元/亿元/十亿元、thousand/million/billion，可带币种（人民币百万元、RMB million、亿港元）；每股：元/股、人民币/股；股数：股/万股/百万股/亿股；比例：ratio（0.10=10%）、%；百分点：个百分点、百分点、pp；倍；个；天\n"}`

工具/绑定失败（用量已包含）：`{"type": "tool_return_failure", "line": 203, "name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 10, in <module>\n    deliver()\n  File \"/input/analysis_report.py\", line 529, in deliver\n    compiled = compile_report(report, records, models)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 332, in compile_report\n    if 'unit' not in ref: raise ValueError(f'{name}.{i}.{key} 缺少 unit；给单元格明确单位或给整列 unit。{ACCEPTED}')\n                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nValueError: key.0.metric 缺少 unit；给单元格明确单位或给整列 unit。金额：元/千元/万元/百万元/亿元/十亿元、thousand/million/billion，可带币种（人民币百万元、RMB million、亿港元）；每股：元/股、人民币/股；股数：股/万股/百万股/亿股；比例：ratio（0.10=10%）、%；百分点：个百分点、百分点、pp；倍；个；天\n"}`

## Q6-financial

卡罗特这半年利润为什么下降，主要是什么拖累？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 0/26 → 8/20（40.0%）；手写 26 → 12；请求 7 → 5；本轮输入 62,338 / 输出 1,115。

[原始回答](Q6-financial/answer.md) · [模型模板](Q6-financial/template.md) · [数值与调用清单](Q6-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q6-financial/app-data/audit/3e4451e7-d61d-4cd4-b7b4-bbb19f463446.jsonl)

get_data_catalog → financial_workpaper[variance_attribution] → get_source_page → get_source_page → get_source_page

原始标签 {}；宿主呈现标签 {"【推论/分析】": 19, "【事实/数据】": 2}。

- `variance_attribution` periods=`["2025-H1", "2024-H1"]`，原始审计第 30 行。
- 底稿回包：`variance_attribution` ok；{"current": "2025-H1", "comparison": "2024-H1"}。

直接用variance_attribution，利润/毛利与收入、毛利率两因素贡献采用8个绑定；保留经济因果边界，正确解释关税与业务/区域结构影响。

- 12次非绑定数值仍有重复抄写/换单位；本次没有错误的749万元销售费用数。
- 费用、财务收益和所得税抵消项仅定性概述，未列全利润桥及零残差；比上次少调用statement_analysis，主要拖累清楚但不等于完全交付归因底稿。
- 第10页地区收入按原文约数列示，未把这些变化当作独立可相加利润因果。

卡罗特PDF9/10/23：归母变动-61.311百万元，毛利-113.649百万元，收入效应-48.9369717、毛利率效应-64.7120283百万元。无期间、读取、绑定或工具错误。

无工具或绑定错误事件。

## Q6-prepared

卡罗特这半年利润为什么下降，主要是什么拖累？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

绑定 23/41 → 0/27（0.0%）；手写 18 → 27；请求 10 → 9；本轮输入 138,485 / 输出 2,342。

[原始回答](Q6-prepared/answer.md) · [模型模板](Q6-prepared/template.md) · [数值与调用清单](Q6-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-fixes/tmp/adoption/runs/Q6-prepared/app-data/audit/9cbc570b-db9f-44ff-900b-6d40827c5751.jsonl)

list_documents → get_data_catalog → search_evidence → get_document_index → query_financial_data → get_source_page → get_source_page → run_analysis → get_analysis_status

原始标签 {}；宿主呈现标签 {"【推论/分析】": 20, "【事实/数据】": 1}。


回答了收入下滑、品牌毛利率、关税和市场调整，并列费用与净财务收入缓冲；金额多采用原文近似值。

- 27次数值全部手写，本次没有重现上轮23次绑定。
- 未给总毛利的收入/毛利率两因素桥或利润桥残差；原文原因能支持主因解释，不能据此补出精确关税贡献。
- 销售费用约750万元是披露差额747.1万元的粗略展示，未发现上轮金融组749万元那样的错误精确数。

卡罗特PDF9/10/11/12/13与23：净利润约1.03/1.64亿元、品牌毛利率45.4%→35.3%，地区增速及销售/行政/财务收入方向正确。

无工具或绑定错误事件。

## 两题补测（f21b419）

原失败记录未覆盖，费用全部保留。Q3/Q4在新的独立会话各补跑一次；补测公司写法发生变化，因此简称修复的直接证据另见原入参离线重放，不把全部回答差异归因于这一个修复。

### Q3-financial 补测

绑定 0/22；手写 22；请求 5，输入 179,803 / 输出 2,489。

[回答](followup/Q3-financial/answer.md) · [完整数值和调用](followup/Q3-financial/audit-summary.json)

补测statement_analysis与anomaly_signals均成功；核心扣非盈利质量回答完整，5次请求，仍0/22绑定。

- 模型使用company=伊利、periods=2024；并未再次使用原失败简称，别名修复的直接验证来自离线原入参重放。
- 22个数值全手写，说明即使已收到关键值，仍未必自然采用绑定；现金流/扣非归母倍数不应当同口径现金转换。

全年扣非60.11亿元/-40.04%，非经常占比28.9%，季度-24.98亿元等均与原文相符。原始S/A返回status=ok。

- {"kind": "anomaly_signals", "line": 32, "status": "ok", "period_roles": {"current": "2024-FY", "comparison": "2023-FY"}, "error": null}
- {"kind": "statement_analysis", "line": 34, "status": "ok", "period_roles": {"current": "2024-FY", "comparison": "2023-FY"}, "error": null}
### Q4-financial 补测

绑定 8/16；手写 8；请求 5，输入 75,723 / 输出 1,369。

[回答](followup/Q4-financial/answer.md) · [完整数值和调用](followup/Q4-financial/audit-summary.json)

补测period_analysis与anomaly_signals均成功；Q4四项金额和环比8个数值绑定，5次请求，无错误。

- 仍有8个手写值，多为将绑定值换成亿元重复叙述；模型自然使用百万元绑定后另手写亿元。
- Q4同比保持未知，没有把全年减值强行归到Q4。

periods=[2024 Q4]成功归一为2024-Q4/2023-Q4，年报8页原文核对；收入-8.1854%、归母-172.3815%、扣非-178.4320%、CFO-7.8878%环比正确。

- {"kind": "period_analysis", "line": 32, "status": "ok", "period_roles": {"current": "2024-Q4", "comparison": "2023-Q4"}, "error": null}
- {"kind": "anomaly_signals", "line": 50, "status": "ok", "period_roles": {"current": "2024-FY", "comparison": "2023-FY"}, "error": null}
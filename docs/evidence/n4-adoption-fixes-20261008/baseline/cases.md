# 逐题采用证据（研发预检）

冻结代码 `7524cca`。每题两组各一次；这是行为预检，不是正式成绩。完整原始审计、原生 Pi 事件和最终请求体位于本工作树 `tmp/adoption/runs/<题号>-<组>/`。下列工具顺序按实际请求事件，不把started/completed重复算两次。

绑定率：最终答案中由 `{{...}}` 展开产生的财务数值出现次数 / 全部财务数值出现次数。重复值重复计数；整表按数值格计，空格不计；排除年份、季度编号、页码、来源ID、表行键、序号及URL；账龄阈值计入。非绑定包含手抄原文及手抄工具计算结果，不等于数值必错。数字清单保存在每题 `audit-summary.json`，已逐题人工核对。

“原始标签”来自模型回答模板；“最终标签”含宿主自动标注。不将自动标签算模型主动标注。请求数含路由；输入含缓存，推理token是输出的子集；费用字段仅保留目录估算，CPA实际账单未知。

## Q1-financial

伊利 2024 年业绩为什么下滑？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 6（router 1 / main 5）；输入 195,418（未缓存 66,394，读缓存 129,024）；输出 2,690（推理 1,082）；未知用量请求 0。

绑定：0/23 = 0.0%；手写/非绑定 23 次。原始标签 {}；最终标签 {}。

[最终回答](Q1-financial/answer.md) · [原始模板](Q1-financial/template.md) · [逐项数值/调用/用量](Q1-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q1-financial/app-data/audit/ca8c6343-d435-4a27-9e71-8495b1af34cc.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → search_evidence → financial_workpaper[statement_analysis] → financial_workpaper[variance_attribution] → financial_workpaper[anomaly_signals] → search_evidence → search_evidence → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page

**参数与错误**

- 审计第 38 行：`statement_analysis`；periods=`["2023-FY", "2024-FY"]`。
- 审计第 40 行：`variance_attribution`；periods=`["2023-FY", "2024-FY"]`。
- 审计第 42 行：`anomaly_signals`；periods=`["2023-FY", "2024-FY"]`。
- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

自然调用 statement_analysis、variance_attribution、anomaly_signals。最终收入、利润、减值及现金流方向与原文一致，但没有引用利润桥贡献额/残差，全部量化正文为非绑定数值。

- 三次底稿均传 periods=[2023-FY,2024-FY]，工具保留顺序，利润桥按2023减2024；资产减值贡献变成+31.5015亿元。原始返回并非本题所问2024下降方向。
- 最终未呈现主要抵消项投资收益增量约24.48亿元和工具列出的归母桥残差；不能从调用成功推出完整采用。
- 因果/判断句没有主动推论或观点标签。

伊利PDF7/8、19、91/92、211页；关键降幅及减值金额未发现方向/金额错误。工具期间问题见audit-summary调用38/40/42行及workpapers利润桥。

## Q1-prepared

伊利 2024 年业绩为什么下滑？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 11（router 1 / main 10）；输入 171,575（未缓存 45,623，读缓存 125,952）；输出 2,624（推理 566）；未知用量请求 0。

绑定：0/18 = 0.0%；手写/非绑定 18 次。原始标签 {}；最终标签 {"【事实/数据】": 1}。

[最终回答](Q1-prepared/answer.md) · [原始模板](Q1-prepared/template.md) · [逐项数值/调用/用量](Q1-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q1-prepared/app-data/audit/d94fc514-472f-4f46-937b-694daa9c0fe5.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → search_evidence → query_financial_data → get_document_index → get_source_table → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_table → search_evidence → get_source_table → get_source_page → get_source_table → get_source_table → search_evidence → search_evidence → get_source_page → search_evidence → get_source_page

**参数与错误**

- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

按原文检索和页表解释收入/减值下滑，未调用自由计算或绑定。主要金额和方向与原文一致。

- 未给利润桥、量价贡献分解或残差；按主因提供定性解释。
- 原始答复无事实/推论/观点标签，最终仅一处宿主事实标签。

伊利PDF7/8、16、18/19、185、211页；收入下滑/毛利缓冲/澳优商誉减值与这些披露相符。

## Q2-financial

伊利 2024 年利润和现金流走势一致吗，有没有值得警惕的地方？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 9（router 1 / main 8）；输入 287,652（未缓存 58,276，读缓存 229,376）；输出 2,805（推理 913）；未知用量请求 0。

绑定：0/27 = 0.0%；手写/非绑定 27 次。原始标签 {}；最终标签 {"【事实/数据】": 1}。

[最终回答](Q2-financial/answer.md) · [原始模板](Q2-financial/template.md) · [逐项数值/调用/用量](Q2-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q2-financial/app-data/audit/fd2364b2-628e-49c9-9fba-9640d53ef85c.jsonl)

**实际工具与 kind 序列**

get_data_catalog → list_documents → query_financial_data → financial_workpaper[statement_analysis] → get_source_page → get_source_page → get_source_page → get_document_index → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics

**参数与错误**

- 审计第 38 行：`statement_analysis`；periods=`["2024-FY", "2023-FY"]`。
- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

用了statement_analysis和四次calculate_financial_metrics，未用题意对应的anomaly_signals。CFO/合并净利润2.57倍、现金收入比和合并期末现金245.47亿元口径正确，答案全部非绑定。

- 应对利润现金背离的专用雷达未调用，九类信号及阈值没有进入答复。
- 把资产减值等间接法加回与营运资本并称能抬高CFO，未充分区分利润到现金的调节与产生现金的原因；也未给该判断加推论标签。
- 没有补取PDF19页关于春节备货/预收经销商货款的现金流增长解释。

伊利PDF94/95为合并现金流，现金期初428.1208亿元、期末245.4652亿元；96为母公司。PDF217/218是间接法调节，不等于现金流增长的因果分解。

## Q2-prepared

伊利 2024 年利润和现金流走势一致吗，有没有值得警惕的地方？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 9（router 1 / main 8）；输入 94,604（未缓存 21,388，读缓存 73,216）；输出 2,668（推理 802）；未知用量请求 0。

绑定：0/12 = 0.0%；手写/非绑定 12 次。原始标签 {"【推论】": 1}；最终标签 {"【事实/数据】": 1, "【推论】": 1}。

[最终回答](Q2-prepared/answer.md) · [原始模板](Q2-prepared/template.md) · [逐项数值/调用/用量](Q2-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q2-prepared/app-data/audit/6913aa12-a862-492b-8a53-cb0457d8ac92.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → search_evidence → get_document_index → get_source_table → get_source_table → get_source_table → get_source_table → get_source_table → run_analysis → get_analysis_status → search_evidence → get_source_table

**参数与错误**

- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

利润下滑而CFO上升的结论正确，有主动推论标签，但混用了合并与母公司口径。

- 回答声明采用合并口径，却把PDF96母公司现金余额235.13→84.72亿元，与合并CFO217.40亿元、投资净流出327.09亿元和筹资净流出72.78亿元并列。正确合并余额应为428.12→245.47亿元（PDF95）。
- 未呈现间接法桥或原文现金流增长解释，全部非绑定。

伊利PDF94/95/96直接核对。

## Q3-financial

扣非后看伊利 2024 年盈利质量如何？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 3（router 1 / main 2）；输入 24,621（未缓存 17,965，读缓存 6,656）；输出 1,044（推理 386）；未知用量请求 0。

绑定：19/21 = 90.5%；手写/非绑定 2 次。原始标签 {}；最终标签 {"【事实/数据】": 6}。

[最终回答](Q3-financial/answer.md) · [原始模板](Q3-financial/template.md) · [逐项数值/调用/用量](Q3-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q3-financial/app-data/audit/a84cbe8e-6b3b-46a4-95c7-d7d03814205d.jsonl)

**实际工具与 kind 序列**

financial_workpaper[statement_analysis]

**参数与错误**

- 审计第 20 行：`statement_analysis`；periods=`["2024"]`。
- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

直接调用statement_analysis一次并嵌入五张表；全年扣非表、现金转换表和间接法贡献表为空，季度表及部分权益数据有值。绑定率高但未完成核心扣非分析。

- periods=[2024]不是现有2024-FY。归母/可计算扣非本可取得（对照同种数据Q2正确期间底稿：8452.8600/6011.2749百万元、非经常占比28.8847%）。
- 当前资料的披露扣非字段及CFO映射还存在独立缺项；不能把所有空值归因于期间参数，也不能说原文未披露。
- 未读PDF7补齐60.11亿元/下降40.04%，仍称核对已列示，并引用权益所在88页支持扣非段落；实质遗漏全年盈利质量。
- 整张表嵌入在行内造成Markdown破版，来源行键也直接暴露。无主动推论/观点标签。

伊利PDF7/8/88，以及Q2-financial的deducted_profit表；原始工具调用audit-summary第20行。

## Q3-prepared

扣非后看伊利 2024 年盈利质量如何？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 10（router 1 / main 9）；输入 119,784（未缓存 24,552，读缓存 95,232）；输出 3,404（推理 642）；未知用量请求 0。

绑定：7/19 = 36.8%；手写/非绑定 12 次。原始标签 {"【推论】": 1}；最终标签 {"【事实/数据】": 2, "【推论】": 1}。

[最终回答](Q3-prepared/answer.md) · [原始模板](Q3-prepared/template.md) · [逐项数值/调用/用量](Q3-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q3-prepared/app-data/audit/23123316-d116-424b-9509-87a1df9c8314.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → search_evidence → get_document_index → get_source_page → get_source_page → get_source_page → get_source_page → get_source_table → query_financial_data → run_analysis → get_analysis_status → run_analysis → get_analysis_status

**参数与错误**

- 审计第 95 行：tool_return_failure，{"name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 7, in <module>\n    runpy.run_path('/input/analysis.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/analysis.py\", line 26, in <module>\n    save_table(t, 'quality_metrics.csv')\nTypeError: save_table() missing 1 required positional argument: 'rows'\n"}

**金融核对与遗漏**

读原文后自由计算扣非增速、净利率、非经常占比及CFO比率；七次数值占位符进入最终答案，核心扣非信息完整于金融组本次回答。

- 第一次分析脚本save_table少传rows参数而失败；模型第二次脚本修正成功。该失败及所有请求纳入研发用量。
- 绑定值默认显示过长小数，且出现同比下降-40.044...%、下降-2.763...个百分点的符号措辞问题。
- CFO/扣非归母只是参考比率，并非同口径现金转换率；回答仅在表中描述，没有明确这一限制。

伊利PDF7/8/9/82；原始脚本及get_analysis_status失败/成功均在审计中。

## Q4-financial

伊利 2024 年 Q4 表现怎么样？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 6（router 1 / main 5）；输入 142,397（未缓存 44,093，读缓存 98,304）；输出 1,542（推理 560）；未知用量请求 0。

绑定：0/8 = 0.0%；手写/非绑定 8 次。原始标签 {"【计算】": 1}；最终标签 {"【事实/数据】": 1, "【计算】": 1}。

[最终回答](Q4-financial/answer.md) · [原始模板](Q4-financial/template.md) · [逐项数值/调用/用量](Q4-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q4-financial/app-data/audit/61d10e80-0f46-4797-8b66-895ff9354e77.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → query_research_records → financial_workpaper[statement_analysis] → get_source_table → get_source_page → get_source_page → calculate_financial_metrics

**参数与错误**

- 审计第 38 行：`statement_analysis`；periods=`["2024-FY", "2023-FY", "2024-Q4"]`。
- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

调用statement_analysis的既有季度表，并计算Q4环比及归母/扣非差额；季度四项金额、环比约-8.2%与非经常影响约0.82亿元正确。

- period_analysis未调用，但本题已有K1原披露季度表，不能因此判定没有回答Q4或强制要求新工具。
- 八次数值全手写，未主动标推论/观点；另有【计算】标签。
- 未虚构Q4同比和亏损原因，保留缺失。原始failed为复制未完成资料后的本地元数据变化，不能据此认为源报告失效。

伊利PDF8季度表。工具传入2024-FY、2023-FY、2024-Q4，前两期顺序正确。

## Q4-prepared

伊利 2024 年 Q4 表现怎么样？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 9（router 1 / main 8）；输入 93,578（未缓存 21,386，读缓存 72,192）；输出 2,348（推理 422）；未知用量请求 0。

绑定：0/12 = 0.0%；手写/非绑定 12 次。原始标签 {"【计算】": 1, "【披露】": 1}；最终标签 {"【事实/数据】": 1, "【计算】": 1, "【披露】": 1}。

[最终回答](Q4-prepared/answer.md) · [原始模板](Q4-prepared/template.md) · [逐项数值/调用/用量](Q4-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q4-prepared/app-data/audit/4200ca1a-d9ee-4e1a-83f6-a42e74e69004.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → query_financial_data → search_evidence → get_source_table → get_source_table → get_source_page → search_evidence → run_analysis → get_analysis_status → run_analysis → get_analysis_status

**参数与错误**

- 审计第 81 行：tool_return_failure，{"name": "get_analysis_status", "error": "Analysis process exited with an error", "stderr": "Traceback (most recent call last):\n  File \"/opt/finance/entrypoint.py\", line 11, in <module>\n    runpy.run_path('/input/__analysis__.py', run_name='__main__')\n  File \"<frozen runpy>\", line 287, in run_path\n  File \"<frozen runpy>\", line 98, in _run_module_code\n  File \"<frozen runpy>\", line 88, in _run_code\n  File \"/input/__analysis__.py\", line 10, in <module>\n    deliver()\n  File \"/input/analysis_report.py\", line 529, in deliver\n    compiled = compile_report(report, records, models)\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/input/analysis_report.py\", line 338, in compile_report\n    raise ValueError(f'{name}.{i}.{key} 需要 currency；在该单元格或列写 currency，例如 CNY / HKD / USD，或用明确单位 人民币百万元 / 港元/股；币种不能从金额大小推断')\nValueError: q4.0.value 需要 currency；在该单元格或列写 currency，例如 CNY / HKD / USD，或用明确单位 人民币百万元 / 港元/股；币种不能从金额大小推断\n"}

**金融核对与遗漏**

读季度表后自由计算环比、利润率和现金收入比，四项披露值与约-8.2%/-9.1%/-9.4%/29.5%均正确。

- 第一次分析report列缺币种报错；模型第二次修正成功。
- 计算器结果没有使用A1绑定，12次数值全手写；主动用了【披露】【计算】，未用推论/观点标签。
- 明确不作缺少资料的Q4同比和利润转亏因果判断。

伊利PDF7/8及两次分析脚本。

## Q5-financial

瑞和这半年报有没有口径调整或异常？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 10（router 1 / main 9）；输入 212,439（未缓存 39,383，读缓存 173,056）；输出 3,102（推理 1,175）；未知用量请求 0。

绑定：0/15 = 0.0%；手写/非绑定 15 次。原始标签 {}；最终标签 {"【事实/数据】": 1}。

[最终回答](Q5-financial/answer.md) · [原始模板](Q5-financial/template.md) · [逐项数值/调用/用量](Q5-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q5-financial/app-data/audit/4decc9ca-f36b-4c9b-a92c-ef7063048c99.jsonl)

**实际工具与 kind 序列**

list_documents → financial_workpaper[basis_changes] → financial_workpaper[anomaly_signals] → financial_workpaper[statement_analysis] → get_artifact → get_artifact → get_artifact → get_document_index → financial_workpaper[anomaly_signals] → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → calculate_financial_metrics → calculate_financial_metrics → calculate_financial_metrics → get_source_page → get_source_page → get_source_page

**参数与错误**

- 审计第 30 行：`basis_changes`；periods=`["2025-06-30", "2024-06-30"]`。
- 审计第 32 行：`anomaly_signals`；periods=`["2025-06-30", "2024-06-30"]`。
- 审计第 34 行：`statement_analysis`；periods=`["2025-06-30", "2024-06-30"]`。
- 审计第 70 行：`anomaly_signals`；periods=`null`。
- 审计第 36 行：tool_error，{"name": "financial_workpaper", "toolCallId": "call_r3nYxd87nHyeKA43uVmP2Ntv|fc_0b056f5269ee00ef016ac71cc477cc87d095dc5f6d629f3304", "message": "KeyError"}
- 审计第 56 行：tool_error，{"name": "get_artifact", "toolCallId": "call_vx00I21JDM8k9ipS38LSgS7z|fc_0b056f5269ee00ef016ac71ccccf2487d0bb4c23f793ff99a5", "message": "RunnerError"}
- 审计第 58 行：tool_error，{"name": "get_artifact", "toolCallId": "call_qN5Bj1fc8UnMkDapJm6fgS3j|fc_0b056f5269ee00ef016ac71ccccf3887d08b477dcc69d0c900", "message": "RunnerError"}
- 审计第 60 行：tool_error，{"name": "get_artifact", "toolCallId": "call_QRCwxFER6OtQK71dxsnZe7ua|fc_0b056f5269ee00ef016ac71ccccf4087d08b8f4f2889d6180a", "message": "RunnerError"}
- 审计第 126 行：tool_error，{"name": "calculate_financial_metrics", "toolCallId": "call_418pfApFKYxvEeZ5mm44groU|fc_0b056f5269ee00ef016ac71ce91d7887d0b9d6085f6a1f39d0", "message": "ValueError"}

**金融核对与遗漏**

自然调用basis_changes、anomaly_signals和statement_analysis；初次雷达报错后省略periods重跑成功。最终公允价值63.015m、税前剔除后-22.084m、CFO-30.650m、同口径现金转换约-0.75和逾期ECL口径正确；没有把信号等同错报。

- 先把2025-06-30/2024-06-30时点传给流量期间；雷达KeyError，statement/basis两项返回空观察。basis没有以正确H1期间重跑，未识别配对重述只能作有限说明。
- 三次get_artifact把workpaper交付ID当run_id，均RunnerError；sum inputs.values传数组导致一次ValueError。总计5次工具错误，后续原文阅读和计算继续完成。
- 底稿只向模型保留列名/行键和observations，具体缺项行、完整信号阈值来源在被隐藏的report/numeric_tables；模型转向读文件失败，再取原文。
- 15次数值全非绑定；没有主动推论/观点标签。最终未引用经验阈值，所以不存在把经验阈值冒称行业标准的问题。

瑞和PDF28/30/32/33/41/47；47页逾期超12个月原值65.202m/准备58.312m/89%，与46页发票账龄超一年65.272m不可混用。

## Q5-prepared

瑞和这半年报有没有口径调整或异常？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 7（router 1 / main 6）；输入 209,107（未缓存 64,723，读缓存 144,384）；输出 3,134（推理 1,108）；未知用量请求 0。

绑定：0/14 = 0.0%；手写/非绑定 14 次。原始标签 {}；最终标签 {}。

[最终回答](Q5-prepared/answer.md) · [原始模板](Q5-prepared/template.md) · [逐项数值/调用/用量](Q5-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q5-prepared/app-data/audit/c4d00a4d-98c5-4743-bd4e-d6871b148e19.jsonl)

**实际工具与 kind 序列**

list_documents → get_document → get_document_index → get_data_catalog → query_financial_data → search_evidence → search_evidence → search_evidence → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page

**参数与错误**

- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

根据原文正确区分会计政策无重大调整与经营业务结构变化，识别FVTPL、负CFO和短期债务等现象。

- 把PDF46发票日期账龄超一年65.272m（约6527万元），与PDF47逾期超12个月口径的89%及58.312m准备配成同一账龄档。正确对应逾期原值是65.202m；金额接近仍不是同一口径。
- 全部非绑定；没有【事实/数据】【推论】【观点】标准标签，只有自然语言的披露和判断结构。

瑞和PDF33/34、46/47、28/30/32/52/54。

## Q6-financial

卡罗特这半年利润为什么下降，主要是什么拖累？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 7（router 1 / main 6）；输入 198,640（未缓存 61,424，读缓存 137,216）；输出 2,509（推理 751）；未知用量请求 0。

绑定：0/26 = 0.0%；手写/非绑定 26 次。原始标签 {"【Carote 2025中期报告，第9、11、13页；document_id：3d9d0befd8374eed9a7488dbd8dd00d2】": 1, "【第9页】": 1, "【第11页】": 1, "【计算；报告第11—12页】": 1, "【计算；报告第13页】": 1}；最终标签 {"【Carote 2025中期报告，第9、11、13页；document_id：3d9d0befd8374eed9a7488dbd8dd00d2】": 1, "【第9页】": 1, "【第11页】": 1, "【计算；报告第11—12页】": 1, "【计算；报告第13页】": 1}。

[最终回答](Q6-financial/answer.md) · [原始模板](Q6-financial/template.md) · [逐项数值/调用/用量](Q6-financial/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q6-financial/app-data/audit/6a04349a-9394-44a8-8deb-1b1ecf37c108.jsonl)

**实际工具与 kind 序列**

get_data_catalog → query_research_records → list_documents → financial_workpaper[statement_analysis] → financial_workpaper[variance_attribution] → get_document_index → get_artifact → get_artifact → get_artifact → search_evidence → query_financial_data → get_source_table → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page → get_source_page

**参数与错误**

- 审计第 38 行：`statement_analysis`；periods=`["2025-H1", "2024-H1"]`。
- 审计第 40 行：`variance_attribution`；periods=`["2025-H1", "2024-H1"]`。
- 审计第 64 行：tool_error，{"name": "get_artifact", "toolCallId": "call_qNVZ6shAUONo46xthCAzv3VW|fc_048ade0380d32a49016ac71de7ed4087d09c40f695ebcbf83d", "message": "RunnerError"}
- 审计第 66 行：tool_error，{"name": "get_artifact", "toolCallId": "call_5QxOWaCZi0ok0vSyqCFvi4r9|fc_048ade0380d32a49016ac71de7ed3887d084304c843a59b2f9", "message": "RunnerError"}
- 审计第 68 行：tool_error，{"name": "get_artifact", "toolCallId": "call_l0k2DkcdyiCFJB4a4iqhdTnO|fc_048ade0380d32a49016ac71de7ed2487d0934de71b5d87e7d0", "message": "RunnerError"}

**金融核对与遗漏**

自然调用statement_analysis和variance_attribution，H1期间与顺序正确。采用了工具独有的毛利两因素贡献：收入-48.9370m、毛利率-64.7120m；说明了非HKFRS调整后的更大降幅，并读原文支持关税、上市费用及定期存款原因。

- 三次get_artifact将交付ID当run_id，均RunnerError，随后从结构数据和原文继续。
- 26次数值全手写。最终销售费用节省写成约749万元，底稿及PDF23应为747.1万元（159.654-152.183=7.471百万元），是可被绑定避免的小额转抄错误。
- 未展示桥残差（本题底稿合并及归母残差均0）及收入/毛利两因素分解的基准与交叉项约定；也没有主动推论/观点标签。
- 报告没有量化关税的单独利润贡献，最终对此保留限制，没有把两因素分解冒称关税因果贡献。

卡罗特PDF9/10/11/12/13/23；profit_bridge selling贡献7.471m、净利润变化-61.293m、归母变化-61.311m、残差均0。

## Q6-prepared

卡罗特这半年利润为什么下降，主要是什么拖累？  
仅基于当前项目已有材料分析，不联网，不重新入库或清洗。

状态：completed；请求 10（router 1 / main 9）；输入 154,086（未缓存 32,230，读缓存 121,856）；输出 3,025（推理 552）；未知用量请求 0。

绑定：23/41 = 56.1%；手写/非绑定 18 次。原始标签 {"【披露：第9、11页】": 1, "【披露：第9–10页】": 1, "【披露：第11–12、23页】": 1}；最终标签 {"【披露：第9、11页】": 1, "【披露：第9–10页】": 1, "【披露：第11–12、23页】": 1}。

[最终回答](Q6-prepared/answer.md) · [原始模板](Q6-prepared/template.md) · [逐项数值/调用/用量](Q6-prepared/audit-summary.json) · [原始审计](D:/AI/财报agent-wt/adoption-preflight/tmp/adoption/runs/Q6-prepared/app-data/audit/75c4d207-5395-4c7e-947b-75831c9fd073.jsonl)

**实际工具与 kind 序列**

list_documents → get_data_catalog → search_evidence → get_document_index → query_financial_data → get_source_table → get_source_page → get_source_page → get_source_page → get_source_page → get_source_table → get_source_table → get_source_table → run_analysis → get_analysis_status → run_analysis → get_analysis_status

**参数与错误**

- 未记录工具/脚本/绑定修复错误；这不表示金融结果自动正确。

**金融核对与遗漏**

读原文、自由计算并在手工Markdown表中使用23个数值绑定；金额、同比及毛利/费用/净财务收入缓冲方向与原文一致。

- 没有金融专用利润桥或毛利两因素贡献分解；提供的是报表项目变化和管理层原因。
- 表内绑定数值未被宿主标事实（宿主跳过Markdown表行），没有主动推论/观点标准标签。另有【披露：页码】自然引用标识。
- 毛利原因来源清楚；非HKFRS调整利润口径未进一步讨论。剩余18次数字为非绑定。

卡罗特PDF9/10/11/12/23。净利润下降61.293m、毛利下降113.649m、净财务收入增22.108m，与脚本及最终数值一致。

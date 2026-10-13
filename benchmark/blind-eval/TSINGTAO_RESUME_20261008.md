# 青岛啤酒断点续跑回报（2026-10-08）

运行状态：**failed**；完整资料准备：**未完成**。有效候选表覆盖 49/310，当前事实 1128 条。仍有明确的准则误标，不能通过完整语义验收；不以表数或回放当成金融正确。

项目 `8513b99f-9168-4156-a92f-8df20d84d51b`；原文档 `e283313993ac49db8ccea8fb7dc87983`；原会话 `906c4ee5-5cc9-4896-8f2c-b880c5739b0f`；本次 run `1b4ecc9a-b685-4394-b426-6980b3045d74`。只发一次恢复请求，人工继续 0，宿主自动续跑事件 1 次。开始 `2026-10-08T04:48:00.012Z`，结束 `2026-10-08T05:25:19.286Z`，用时 37.32 分钟。开始部署 58a903c、3001 PID 56120；未重启/停止服务或Docker。

停止信息：`"自动续跑没有推进，入库未完成。"`。剩余候选表 261 张。原始run、audit、conversation、processing状态均保留。

## 分开记账

| 项目 | 前10次原尝试（保持不变） | 本次恢复 |
|---|---:|---:|
| calls | 136（另有0次缺字段） | 58 |
| input | 14,103,723（另有0次缺字段） | 6774281 |
| output | 32,432（另有0次缺字段） | 25985 |
| uncachedInput | 1,100,459（另有0次缺字段） | 710665 |
| cacheRead | 13,003,264（另有0次缺字段） | 6063616 |
| cacheWrite | 0（另有0次缺字段） | 0 |
| reasoning | 1,615（另有0次缺字段） | 7918 |
| unknownCalls | 1（另有0次缺字段） | 0 |
| cacheUnknownCalls | 1（另有0次缺字段） | 0 |
| costUnknownCalls | 1（另有0次缺字段） | 0 |

旧账存在未知请求时，已知和不是完整总量；本次也按实际unknown字段披露。reasoning是输出的已报子项，不重复加总。`usage.costUsd`仅保留配置估计，CPA实际账单费用为null，入库支出不与分析比较混算。
旧账原文件摘要保持一致：True。本轮审计model_request条数 58，用量calls 58；差异如有保留，不强行补齐。

## 覆盖与质量

宿主判定无推进并停止，停止机制实际生效。具体阻点：非财务身份表只有证券代码，保留原格为待核后遭numeric_table_without_records拦截；自动续跑内连续两次脚本均为0条事实、3个问题（其中2个可定位待核单元格、1个表级拦截）。未绕过，也没有将代码当财务金额强行入库。另有未处理表261张，宿主返回的next_batch为表15；不能将单个阻点解释成所有剩余表都不可处理。

名义核心表覆盖12/12，但这仅是产品返回的完成标志。抽查发现同一收入/归母利润/CFO金额并存CAS和IFRS记录，营业成本与营业利润目前匹配的记录仍只有IFRS标记；核心表完成不等于旧准则语义已经修好。

- 源PDF225页，解析表 337 张；当前processing候选分母 310。这两个数口径不同，不能以候选覆盖代称全部原文语义已核验。原始候选/已完成列表、core tables、待处理项保存在processing-states.json；中途有效覆盖曾回退，完整时间线保留。
- 当前原格/数值区间回放：{'total': 1128, 'passed': 1128, 'failed': 0}；按保存scale的缩放回放：{'passed': 1128, 'failed': 0, 'unverified': 0}。这些只验证坐标、原值和缩放可重放。
- 已提交批次的可定位待核单元格 0，批次问题分布 {'semantic_review_pending': 5}；未提交批次及未处理表不包含在这个单元格数中，不得理解为全篇剩余疑点总量。
- 当前scope分布：{'consolidated_CAS': 464, 'consolidated_IFRS': 476, 'parent_CAS': 59, 'unspecified_CAS': 21, 'parent_IFRS': 108}。原PDF p80、91、92明确CAS；IFRS标记仍有 584 条。没有手工改库。
- 原文抽查记录在source-spotchecks.json：源准则声明及7项核心金额的两年原文存在性、入库record/口径/期间/坐标。数字能对上不等于利润归属、主体或准则正确。

所有held-out源文、轨迹与抽查细节保留在N1目录，未发给主线/N2/N3，未用于产品调试。若未完整完成或准则问题仍存，H1/H2正式材料不宣称就绪；等待Claude后续安排，不人工反复续推。

正式盲评方案（未执行）见 [FORMAL_EXECUTION_PLAN_20261008.md](FORMAL_EXECUTION_PLAN_20261008.md)。本轮run是准备支出，不是评测成绩。

账目与证据：[preparation.json](../../data/evaluation/blind-eval-tsingtao-resume-20261008/preparation.json)、[quality-summary.json](../../data/evaluation/blind-eval-tsingtao-resume-20261008/quality-summary.json)、[source-spotchecks.json](../../data/evaluation/blind-eval-tsingtao-resume-20261008/source-spotchecks.json)。

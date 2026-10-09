# F2.1 正式三组评测已完成

批次 `F21_formal_b2356dc414e349dd83520d4f44bf870c`；产品冻结 F2.1 `7e702ff`，协议提交 `207e105`。评测记录的后续 git 提交不代表产品部署。

**两项总体 E4 优势均未证实**：整套系统 vs 原版 Pi、金融层 vs prepared。开发核心与 held-out 分别判定，扩展单列；没有平均、挑遍次、补跑或追加裁决。

- 162 个题位：161 完成，F4_D1 上游 503 基础设施失败保留；18 个全新 astra/high 评分已全部先封存再揭盲。
- 实质缺陷有/无一致率：开发 53/54、held-out 53/54、扩展 52/54；三个 split 均达到修订可靠性下限，最大单维差均 2，照实报告。
- 分析 1,861 请求，8 次未知；已知输入 89,277,686、输出 1,397,031；目录估算下界 2.94089729 USD，观测上界情景 3.19485489 USD，实际账单未知。不能宣称比原版 Pi 更省。
- 海尔 9/9 参评完成；按用户批准的 338/344 表、核心 43/43、4,568 事实冻结。缺失 6 表、414 待核验事实、120 疑点与 X7 必需输入重叠均 0，不影响本题可答。最后数据摘要复核无差异，实时评测已结束。
- 全部附件下载成功（3,072 链接）；202 分析脚本版本复放成功，12 模型复算包缺依赖失败，未改交付物。1,972 明确单元格绑定仅作局部确定性观察，不替代盲评。
- 倒序遍 F1_X7 的仍交付辅助报告部分叙述未完整核验，单列关键交付覆盖不足；没有改写该评审原始分数。所有其他未审范围同样留存，题外来源未穷尽审计不冒称完整验真。

## 文件

- 完整技术报告：`benchmark/blind-eval/F21_FORMAL_REPORT.md`；本目录同字节副本 `TECHNICAL_REPORT.md`。
- 本目录 `FORMAL_REPORT.md` 为自动生成的完整指标表；`formal-results.json` 包含两主对比、各 split 两遍、配对成本上下界、六维与适用范围、描述性重复区间、分类计数。
- `development-extension-reviews.json`、`development-extension-disagreements-originals.json` 保留开发/扩展原评语；`heldout-disagreement-indicators.json` 仅编号和指标。
- 准备费用：`preparation-cost-summary.json`。连通性、初始环境事故与评审分账，未知不记零。
- 封存与最终检查：`protocol-freeze.json`、`participant-completion.json`、`final-release-validation.json`。

私有目录 `data/evaluation/blind-eval-F21-formal-private-20261009` 保存全部原始答卷、18 份评分原件、全量分歧、同分不同理由、覆盖判断及运行审计。held-out 题面、回答、原文和评语不出私有目录。私有原件不强制加入 git。

原协议 16 个文件摘要未变，评分原件全部摘要未变。无产品代码、数据库或 3001 变更。伊利/海尔准备状态与局限见 `yili-readiness.json`、`haier-readiness.json` 及方法说明；海尔未完成表不全是前置信息，无影响判断仅限 X7。

首题环境前置检查因 Docker 未运行，用户特批一次作废，8 请求用量计事故账；原题位以相同排列与 seed、新键重跑并通过环境检查。后续失败均未补跑，旧门槛批次不混入正式统计。

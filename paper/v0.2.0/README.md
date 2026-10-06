# v0.2.0 技术论文

论文：《从财报问答到证据驱动的金融研究 Agent：设计、实现与工程演进》。日期：2026-10-05。

- `finance-agent-technical-paper.md`：可维护正文，GitHub 可直接阅读。
- `finance-agent-technical-paper.pdf`：排版阅读版，与本目录 Markdown 对应。
- `architecture.svg`、`cleaning-flow.svg`：可缩放技术图。
- `build_pdf.py`：从正文生成 PDF 和图的脚本；只使用本地文件，不调用 LLM。
- `paper-manifest.json`：正文、PDF 和图的哈希及生成信息。

当前稿件是工程案例研究，不是已发表或外部同行评审论文。没有擅自填写作者、单位，不将旧评测成绩当作当前版本成绩，不将两篇材料的抽查结果宣称为泛化准确率。

2026-10-05 已完成同模型“通用 Pi / 金融项目”的三任务开发试跑，口径见 [方案](../../design/pi-finance-comparison-protocol-20261005.md)，真实结果见 [实验补充](../experiments/pi-pilot-20261005.md)。两组核心样本均 19/19，但金融项目首轮完整入库成本更高，且两组仍有解释与交付缺陷；尚未证明专业系统整体优于通用 Pi。本目录已发布正文和 PDF 保留历史版本，后续论文整合实验补充及其局限。

本轮真实验收的可分发汇总位于 `../../docs/evidence/v0.2.0/`。原始对话、模型私有推理、密钥和主数据库不进入论文目录。PDF 的排版依赖为 ReportLab，视觉验证使用 PyMuPDF；它们属于论文构建工具，不是普通用户启动应用的必要条件。

随后已完成[复用已入库资料的三组分析实验](../experiments/pi-analysis-reuse-20261005.md)，新增入库调用为 0。A 通用 Pi、B 通用 Pi＋整理数据、C 金融 Agent 共完成四类问题的 12 项运行；DeepSeek 与 CPA 两个同模型对照部分分开呈现。核心取值和数学复算通过，但金融组仍未证明整体质量/成本优势，所有负面结果、诊断重跑费用、未知用量及收尾修复均保留。可分发记录见 `../../docs/evidence/pi-analysis-20261005/`；本目录已发布正文/PDF 保留，后续整合时引用该补充，不能沿用旧的混合入库费用比较。

2026-10-06 的[查询压缩、模型复用与交付一致性对照](../experiments/pi-analysis-delivery-20261006.md)进一步记录同一 CPA 模型的 12 项主实验，以及接口修复后另外登记的配对复测。正文区分来源取数、公式、解释和图表，并保留金融组未体现整体优势的负面结果；单次开发回归不声称统计显著性。完整入库不在本轮重复执行或计入分析成本。

另有[统一数值交付与新公司对照](../experiments/finance-generalization-20261006.md)：卡罗特55页中报和47页研报、同模型15项任务，准备成本单列。金融组累计输入/输出减少，但未缓存输入增加，图表与CSV交付仍有实质错误，未证明整体优越；冻结、逐题质量、未知用量和复算证据完整保留。此补充未改写本目录已发布的正文和PDF。

在已安装 ReportLab 的 Python 环境运行：

```powershell
python paper/v0.2.0/build_pdf.py
```

默认使用 Windows SimSun 字体；通过 `FINANCE_PAPER_FONT` 可指定兼容的 TrueType 中文字体。输出需重新核对分页与图表，生成脚本成功不等于完成视觉检查。发布版逐页检查记录在 `paper-manifest.json`。

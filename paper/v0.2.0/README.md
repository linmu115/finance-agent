# v0.2.0 技术论文

论文：《从财报问答到证据驱动的金融研究 Agent：设计、实现与工程演进》。日期：2026-10-05。

- `finance-agent-technical-paper.md`：可维护正文，GitHub 可直接阅读。
- `finance-agent-technical-paper.pdf`：排版阅读版，与本目录 Markdown 对应。
- `architecture.svg`、`cleaning-flow.svg`：可缩放技术图。
- `build_pdf.py`：从正文生成 PDF 和图的脚本；只使用本地文件，不调用 LLM。
- `paper-manifest.json`：正文、PDF 和图的哈希及生成信息。

当前稿件是工程案例研究，不是已发表或外部同行评审论文。没有擅自填写作者、单位，不将旧评测成绩当作当前版本成绩，不将两篇材料的抽查结果宣称为泛化准确率。

本轮真实验收的可分发汇总位于 `../../docs/evidence/v0.2.0/`。原始对话、模型私有推理、密钥和主数据库不进入论文目录。PDF 的排版依赖为 ReportLab，视觉验证使用 PyMuPDF；它们属于论文构建工具，不是普通用户启动应用的必要条件。

在已安装 ReportLab 的 Python 环境运行：

```powershell
python paper/v0.2.0/build_pdf.py
```

默认使用 Windows SimSun 字体；通过 `FINANCE_PAPER_FONT` 可指定兼容的 TrueType 中文字体。输出需重新核对分页与图表，生成脚本成功不等于完成视觉检查。发布版逐页检查记录在 `paper-manifest.json`。

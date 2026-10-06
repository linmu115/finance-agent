# v0.3.0 技术论文

正文和 PDF 同步更新至 2026-10-06，保留立项、系统结构、技术组成、开发问题与解决办法，新增第 8.4、9.4 节的优化设计及第 12 节同模型同数据对照。第 11 节明确标为 v0.2.0 历史验收，不与新实验混分。

- [可编辑正文](finance-agent-technical-paper.md)
- [排版 PDF](finance-agent-technical-paper.pdf)
- [新公司实验明细](../experiments/finance-generalization-20261006.md)
- [可分发结果](../../docs/evidence/pi-finance-generalization-20261006/results.json)

正文保留金额/百分比错误、图形问题、宿主中断、未知用量和模型版本未被复用等负面结果。记录中的输入/输出下降不是实际账单下降，单公司小样本也不是整体专业优势证明。

`build_pdf.py` 使用 ReportLab 和本机宋体/黑体生成 PDF 与矢量架构图；`paper-manifest.json` 记录文件哈希及逐页视觉核验范围。PDF 构建属于文档工具链，不是用户运行应用所需依赖。

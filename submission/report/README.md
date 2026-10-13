# 技术报告构建

正文：`技术报告.md`；交付：`技术报告.pdf`（25 页）。正式评测章节只使用公开汇总，三张图均保留 PNG 和独立矢量 PDF，见 `assets/formal-{quality,depth,cost}.*`。

在项目根目录运行：

```powershell
D:/anaconda/python.exe submission/report/build_result_figures.py
D:/anaconda/python.exe submission/build_pdf.py submission/report/技术报告.md --label 技术报告 --font-size 10.5 --line-height 17
```

图表需要 matplotlib、NumPy；PDF 需要 ReportLab、Pillow。构建使用本机宋体与黑体，PDF 嵌入字体。构建脚本只写明确指定的技术报告，不扫描或重建计划书。

图表的原始值、公开 JSON 字段路径及来源摘要见 `evidence/formal-figure-data.json`；本次数据与版式验收见 `evidence/formal-report-validation.json`。修改内容并重新构建后，需重新检查 PDF 分页和图表。

正式结果待填项已全部填入；队伍信息与最终发布包的许可及公开材料清单仍保留占位。

# 金融图表：由模型编写脚本，复用已确认样式

`/input/finance_charts.py` 是只读 Matplotlib 主题辅助文件，不包含数据、分析结论或固定图形。只在金融项目分析中提供；通用 Pi 对照组不加载。完整绘图仍通过 `run_analysis` 在现有隔离环境执行。

- 会话默认 `analysis`（清晰分析）：白底、柔和蓝绿、浅灰绘图区、结论前置。仅在有助于回答问题时突出少量关键数字；相关小图在空间足够时并列，标签多时分开输出，保持可读字号。
- 正式导出 `report`（研报排版）：暖白、墨绿、正式标题、纵向编号图和来源图注。导出时重新用该主题绘制，数据和口径保持一致，不能只改文件扩展名。附 PNG 供会话预览，按需要另存 PDF。
- 模型自行选择图形、数量、布局、解释、预测区间和假设。不要为套布局补数据、固定每次画两张或限制可用图形；用户要求的样式优先。

## 用法

```python
import sys
sys.path.insert(0, "/input")
import finance_charts as fc
import matplotlib.pyplot as plt

# 先从导出数据/已核对的模型结果构造本次所需的数据。
with fc.theme("analysis") as colors:  # 正式导出改为 report
    fig, ax = plt.subplots(figsize=(8, 4.6))
    # 在这里用标准 Matplotlib 绘制与问题匹配的图形。
    # 颜色可使用 colors["main"], ["secondary"], ["negative"], ["neutral"]。
    # 标题可用 fontfamily=colors["title_font"]；留出标题、单位和来源的空间。
    # fig.savefig("/output/收入与现金流.png")  # 绘制实际内容后再保存。
    plt.close(fig)
```

主题只统一字体、色彩、线条、网格与导出清晰度，不自动认定数据质量，也不自动设置金融口径。主题上下文结束后恢复 Matplotlib 设置；保存图片应在上下文内完成。可以用完整 Matplotlib API 实现瀑布、热力、区间或自定义图表，不受示例限制。

## 简便调用与已保存模型

金额图推荐一步完成换算与标签：`fc.plot_amounts(ax, years, original_values, amount_scale='1000000', display_unit='亿元', currency='CNY', kind='bar')`。直接传原值，程序同步画出的数值与轴单位；不要先手除一次。数据库规范金额的amount_scale是1；原表按声明倍率；保存模型使用model['spec']['amount_scale']。kind可用plot、bar、barh、scatter；其余参数直接传给Matplotlib，布局和预测线型自由决定。

分析脚本已经配置中文字体和 analysis 主题，无需反复设置字体。`finance_charts.configure('report')` 可将整份脚本切为正式报告风格，不必依赖 with 块的范围。

`run_analysis(model_refs={"base":{"artifact_id":"保存返回的ID","revision_id":"保存返回的版本"}})` 把选定模型挂载为 `/input/models.json`，以 `base` 为键。只读取此次指定的版本，不挂载其他会话的模型。读取 `models["base"]["result"]["tables"]` 绘图。输入、结果 CSV 与包含完整原计算器、输入和复算脚本的 `model_bundle.zip` 自动交付，无需再次编写 DCF 算法。

比较时指定两个别名，并传 `comparisons={"change":{"baseline":"base","scenario":"new","order":["discount.wacc", ...]}}`，比较结果在 `/input/comparisons.json`。直接画差异与贡献，CSV自动导出。

小修绘图使用 `source_run_id` 加 `edits=[{"before":"唯一原文","after":"修改后文本"}]`；所有对照组均可使用。完整执行脚本仍自动保存。

- `values, unit, chart_data = finance_charts.record_values(records, "亿元")`：直接读取数据库规范值（已是元），同步单位及精确来源，避免按原始千元再除一次。
- `values, unit = finance_charts.model_values(model, values, "亿元")`：采用所选模型的金额单位。
- `fig, ax = finance_charts.waterfall(start, {"因素": change}, end=reported_end, unit=unit)`：有符号增量及未解释残差；返回标准画布可自由调整。
- `values, unit = finance_charts.amount_values(values, amount_scale='1000000', display_unit='亿元')`：返回换算值与匹配的轴单位；原模型数据不变。
- `fig, axes = finance_charts.comparison_heatmaps({'基准': base['result'], '情景': other['result']})`：直接使用两份 DCF 的 sensitivity 表，统一 WACC/g 轴、共享色标，缺失格留空。仍可自行调整标题和布局。
- 成功运行会自动交付 `/output/executed_script.py`，它是实际执行的完整原脚本。数据、图像仍由脚本写入 `/output`。

## 展示和数据

1. 一句与证据相符的结论或描述性标题，下面放必要的图；图注给主体、期间、币种、单位、口径和可定位来源。内部检查不铺到图上，影响解释的假设与缺口必须标明。
2. 实际与预测用实线/虚线、实心/轮廓以及文字共同区分；场景范围不冒充统计置信区间。不同序列尽量配合形状、直接标签或线型，不能只靠颜色。缺失值留空，不补零或伪造平滑曲线。
3. 柱形量值从零起；金额与比率优先分图。瀑布起终点用同色中性锚点，增减用两种克制色彩并标正负；增量须与终点对上。横向条形设置 x 网格，热力图关闭常规网格，避免直接套默认 y 网格。
4. 输出 `/output/*.png`；另写 `/output/chart_data.json`，含各图 ID、完整精度的原值（Decimal 可保存为字符串）、单位/期间/口径、来源、实际/预测/假设身份。保留缺失值为 null。同次运行多图共用该文件，不能反复覆盖成只剩最后一张图。
5. 原始精度不因标签舍入而改变。图像可视化时可以转浮点，但不要把浮点绘图值回写主数据库。先核对最终数值、坐标和来源，等待 `get_analysis_status` 返回成功及产物清单，再在回复中引用实际生成的图。
6. 会话显示已生成的 PNG，并提供原图及数据下载；“已生成”以工具产物为准，不能用文字描述或 Markdown 空链接代替图像。

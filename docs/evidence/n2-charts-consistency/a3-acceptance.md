# A3 图表层验收（2026-10-07）

基线 ced0cd5；冻结输入取自主线 seam-diagnosis-20261007.json question6 的全部 24 个图片版本。仅复制指定历史 run 到独立 worktree 临时目录，原脚本在 Docker 沙箱执行，替换共享 plot_runtime；没有改模型数据、刻度或调色方案，没有调用 LLM。

24/24 成功，24 个自建容器已清理；91 份 CSV/JSON 数值文件完全一致。自动改色 37 处；4 张图剩余 8 处报告重叠。全部逐张打开：19 张未见剩余缺陷，4 张有上述重叠，另 1 张标签压轴线（检测类别外）。

## 实现与边界

- 默认 constrained layout；旧 tight_layout 调用映射到现有 constrained 引擎，避免共享色条创建后的引擎切换错误。
- AxesImage、QuadMesh 和柱体上的文字按实际渲染背景中位数检查 3:1 对比度，仅将不足的文字改黑/白；透明度保留。
- savefig 最终 draw 的 renderer 坐标报告文字/文字、标题、色条/子图重叠。布局引擎不能移动显式 figure 文本或手动 add_axes 的残留如实返回，不添加模型调用。
- run 结果新增 plot_diagnostics；元数据不进入 A1 金融数值表。面积单位为 save-DPI 像素平方； bbox 坐标可能包含 tight 裁剪产生的平移。
- 原主题的网格线仍可能穿过格中文字；原数据错误及刻度精度也保持，不属于 A3 修复。

## 逐图结果

|序号|研究/任务|图片|改色数|剩余重叠数|目视核对|
|---|---|---|---:|---:|---|
|00|pi-cowork-acceptance-20261006/C1|[carote_profit_cashflow.png](a3-images/00.png)|0|1|负值 -18.7 与经营活动净现金流横轴标签重叠仍在；其他标签可读。|
|01|pi-cowork-acceptance-20261006/C2|[dcf_sensitivity.png](a3-images/01.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|02|pi-cowork-acceptance-20261006/F2|[dcf_sensitivity.png](a3-images/02.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|03|pi-cowork-acceptance-20261006/F2|[dcf_sensitivity.png](a3-images/03.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|04|pi-cowork-acceptance-20261006/F3|[dcf_sensitivity_comparison.png](a3-images/04.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|05|pi-cowork-acceptance-20261006/C3|[sensitivity_comparison.png](a3-images/05.png)|3|2|深色格已改色；显式 y=.98 总标题与右子图标题相撞，手动 add_axes 色条遮住右图末列。|
|06|pi-cowork-acceptance-20261006/D2|[carote_valuation_chart.png](a3-images/06.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|07|pi-cowork-acceptance-20261006/D2|[carote_valuation_chart.png](a3-images/07.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|08|pi-cowork-acceptance-20261006/E2|[图2_DCF敏感性.png](a3-images/08.png)|2|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|09|pi-cowork-acceptance-20261006/E3|[新旧敏感性并列.png](a3-images/09.png)|4|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|10|pi-cowork-acceptance-20261006/E3|[新旧敏感性并列.png](a3-images/10.png)|4|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|11|pi-cowork-acceptance-20261006/D3|[old_new_sensitivity.png](a3-images/11.png)|2|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|12|pi-cowork-acceptance-20261006/D3|[old_new_sensitivity.png](a3-images/12.png)|2|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|13|pi-finance-generalization-20261006/B1|[profit_cashflow_comparison.png](a3-images/13.png)|0|0|布局改善；-18.7 仍压在底部轴线上（文字/线条关系不在本次重叠检测类别内），未与横轴文字相交。|
|14|pi-finance-generalization-20261006/C1|[profit_cashflow_comparison.png](a3-images/14.png)|0|1|负值 -18.7 仍与横轴标签相交；其他标签可读。|
|15|pi-finance-generalization-20261006/C2|[dcf_sensitivity.png](a3-images/15.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|16|pi-finance-generalization-20261006/A2|[dcf_sensitivity_chart.png](a3-images/16.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|17|pi-finance-generalization-20261006/B3|[双版本敏感性.png](a3-images/17.png)|2|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|18|pi-finance-generalization-20261006/C3|[sensitivity_comparison.png](a3-images/18.png)|2|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|19|pi-finance-generalization-20261006/A3|[sensitivity_comparison.png](a3-images/19.png)|2|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|20|pi-finance-generalization-20261006/D2|[dcf_sensitivity_chart.png](a3-images/20.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|21|pi-finance-generalization-20261006/E2|[carote_dcf_sensitivity.png](a3-images/21.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|22|pi-finance-generalization-20261006/E3|[carote_update_sensitivity_comparison.png](a3-images/22.png)|1|0|逐张打开核对：深色格文字可读，标题、子图及色条未见重叠；数据、刻度、调色方案保持。|
|23|pi-finance-generalization-20261006/D3|[dcf_sensitivity_comparison.png](a3-images/23.png)|3|4|深色格已改色；显式总标题与左标题相撞，手动色条遮挡右图末列并与两个数值文字重叠。|

## 未修复元素（精确面积）

- 00 / carote_profit_cashflow.png：{'id': 'text:7', 'text': '-18.7', 'axes': 0} × {'id': 'text:11', 'text': '经营活动净现金流', 'axes': None}，349.984 px²。
- 05 / sensitivity_comparison.png：{'id': 'text:31', 'text': '更新：WACC 12.7%，FCF×0.90', 'axes': 1} × {'id': 'text:38', 'text': '卡罗特DCF敏感性｜港元/股', 'axes': None}，3523.256 px²。
- 05 / sensitivity_comparison.png：{'id': 'axes:2', 'role': 'colorbar'} × {'id': 'axes:1', 'role': 'subplot', 'title': ''}，72228.221 px²。
- 14 / profit_cashflow_comparison.png：{'id': 'text:7', 'text': '-18.7', 'axes': 0} × {'id': 'text:11', 'text': '经营活动净现金流', 'axes': None}，277.075 px²。
- 23 / dcf_sensitivity_comparison.png：{'id': 'text:17', 'text': '旧版：WACC 12.2%，FCF ×1.00', 'axes': 0} × {'id': 'text:38', 'text': 'DCF敏感性：新旧方案同网格比较', 'axes': None}，892.329 px²。
- 23 / dcf_sensitivity_comparison.png：{'id': 'text:20', 'text': '11.87', 'axes': 1} × {'id': 'text:37', 'text': '13', 'axes': None}，89.772 px²。
- 23 / dcf_sensitivity_comparison.png：{'id': 'text:23', 'text': '10.59', 'axes': 1} × {'id': 'text:35', 'text': '11', 'axes': None}，99.745 px²。
- 23 / dcf_sensitivity_comparison.png：{'id': 'axes:2', 'role': 'colorbar'} × {'id': 'axes:1', 'role': 'subplot', 'title': '新版：WACC 12.7%，FCF ×0.90'}，80819.413 px²。

## 验证与复现

- 绘图专项 9 项通过；A1/运行返回集成 3 项通过。独立 `.tmp/plot-venv` 使用沙箱相同 Matplotlib 3.10.1 / NumPy 2.2.5 / Pillow 11.2.1，主目录依赖未修改。
- 历史脚本仅在 Docker 执行：`python scripts/replay-harness-a3.py --source-root D:\AI\财报agent`。`--indices` 可精确重跑指定版本，结果和快照默认留在 `.tmp/charts-consistency/a3`。
- 共享依赖：主目录 Python 解释器绝对路径；worktree node_modules 为主目录依赖联接。未重启 3001，未关闭 Docker，未读取 held-out。
- 布局行为依据 [Matplotlib constrained layout 文档](https://matplotlib.org/stable/users/explain/axes/constrainedlayout_guide.html) 与 [Figure.set_layout_engine](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.set_layout_engine.html)。3:1 为本次 spec 指定的注释阈值，不宣称完整 WCAG 文本合规。

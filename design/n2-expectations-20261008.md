# N2 K4 expectations 真实数据验收

基线：7524cca；分支：feat/expectations。仅在 fin-workpapers worktree 修改。Python 调用主目录 .venv 绝对路径；为现有交付测试中写死的 `.venv/Scripts/python.exe` 增加 worktree `.venv` 目录联接，node_modules 沿用已有联接。不安装依赖、不操作 3001、不读取 held-out、不操作 Docker。

## 已确认范围

- 读取项目 374beac2 的 active SQLite 临时副本，覆盖伊利 2024 收入、归母净利润、EPS，预测截止日 2024-12-31。
- 开放 financial_workpaper(kind=expectations)，复用 A1 登记和报告包，不新增工具或 LLM 调用。
- 原始记录、页码、机构、日期、维度、EPS 口径完整保留。主库及其入库记录不改写。

## 实现决定

- 同一机构简称／法定全称通过去公司法律后缀归组，展示原名。主体通过项目内名称／别名及不冲突的证券身份连接；不按模糊相似度合并。
- 严格同口径比较继续使用 K4 原契约。未知会计口径、EPS 分母不同的数值参照另表提供，写明限制，不参与精确误差排名。
- 跨来源维度的前后版本在“版本关联”表保留；不删除维度以制造同口径修正轨迹。归属不明净利润不能对接归母实际值或算归母修正幅度。
- 数据源坐标与行名不符、可比公司均值／中位数、含未识别经济维度的候选单列缺陷，不任取一条或修库。
- 年报营业收入与营业总收入保留区别；不因研报历史数值接近后一口径，就擅自改写预测指标。

## 入口与主线交接

一次调用：

```python
financial_workpaper(
    project_id='374beac2-a970-4972-b210-e91018bbd6e6',
    kind='expectations', company='伊利', periods='2024', as_of='2024-12-31')
```

`periods` 支持 `2024`/`2024-FY` 和列表，缺省取最新年报年度；`metrics` 可用列表或逗号分隔字符串，默认收入/归母净利润/EPS。可用实际财报 `document_id` 代替主体名。`as_of` 含当日，省略表示全部已知日期，不偷偷使用今天。

- `service/workpaper_expectations.py`：纯核心继续保留严格同口径账本、修正、实际差异和误差排名；增加机构法律后缀归组、重述身份隔离。
- `service/workpaper_expectations_data.py`：项目内读取、身份连接、候选缺陷、最新版本与数值参照。未写 SQL 更新、未调用模型。
- A1 沿用 `financial_workpaper` 返回的 `numeric_tables` 登记；金融组既有 allowlist 已覆盖该工具，两个通用配置均不开放。
- 表后缀按币种/数量维度区分，例如 `reference_gaps_CNY_money`、`reference_gaps_CNY_per_share`；金额表单位百万元，每股表元/股。`value` / `difference` 保留精确 Decimal 值，展示可舍入。
- `actual_vs_expected_*` 仅计算严格同口径误差；`reference_gaps_*` 提供未对齐口径的算术参照，逐行写限制且不排名；`version_links_*` 保留不同维度/归属身份的前后版本。
- ⑤ 报告包：`report_section=key_data`，排除记录、缺项与覆盖限制进 `limitations`。新增可选 `report_columns` 仅控制报告正文展示列及顺序；A1、Excel 和快照仍保存全部列、证据与精度。对现有 ①–④ 包回归通过。

## 验收结果

详细证据见 [验收说明](../docs/evidence/n2-expectations/README.md)、[数值结果](../docs/evidence/n2-expectations/acceptance.json) 和 [完整 A1 表](../docs/evidence/n2-expectations/numeric-tables.json)。报告包 PDF/Markdown/Excel 同目录保留。

- 8 个核心预测 + 4 个年报实际披露值，共 **12/12** 与原页逐项核对，并实际打开 5 张对应原页图片。
- 2 家机构 × 3 个指标，**6 项最近预测、6 项金额差额、6 项差异率**；24 条国信截止日后记录全部排除。
- 光大 EPS 原数 2.05→1.89，变化 −0.16 元/股；维度与股本口径未齐，保留为数值变化。净利润 13,063→归母 12,019 百万元仅关联，归母修正差额未知。
- 额外识别季报被标 FY 的 4 条实际候选；未与年报混算，逐条留在缺项表。
- Python 58 项相关测试通过；Node 7 项通过；server/web 类型检查与生产构建通过。最后对默认年度排除季报的补充断言运行 8 项入口单测通过。
- 真实表经本地 stdio 服务、A1 绑定、离线会话审计回放导出：11 页 PDF、Markdown、Excel；Excel 24 个关键值和来源批注逐项比对。已打开 PDF p3/p4/p7 核查版本关联、差额和局限，版面无数值覆盖/裁剪。前一版也检查了 p1/p4/p5/p6/p8/p12。
- 零 LLM、零新入库、无新增材料费用；不是一次新的真实模型盲评，也没有部署或操作 3001。

## 与原 spec 的偏差及理由

1. 真实资料的 `scope=unspecified`，EPS 基本/最新摊薄/预测总股本口径也不同。六项差額放在明确的数值参照表；严格误差排名留空，避免把口径不确定包装成预测优劣。
2. 5 月净利润归属未知、EPS 来源维度也与 11 月不同，不能删除维度强行制造同口径修正轨迹；新增版本关联表保留所有前后数及原因。
3. 年报披露日未入库，保持未知，明确实际值是事后参照，不推定截止日前可知。
4. 本次只验证当前可用核心数与交付链；光大 11 月 p2 未入库、华泰错位及其他维度疑点、年报全文未完成均保留。未宣称机构一致预期完整，未改写主库。

合并注意：与 N3 最可能交叉的是 `service/server.py` 的工具说明和 `service/report_package.py` 的三行展示列扩展；没有改报告包的服务路由或端口。

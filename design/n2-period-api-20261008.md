# N4 交接：期间代数公共接口

无需调用模型或新增工具。产品入口是 `financial_workpaper(..., kind='period_analysis', document_id=...)`，沿用 report/A1/CSV/Markdown。

## 其他 kind 的服务入口

```python
from service.workpaper_periods import load_period_series

series = load_period_series(service, project_id, document_id, company=None,
                            scope='consolidated', periods=None)
quarters = series['quarters']
q4 = next((x for x in quarters
           if x['metric'] == 'parent_profit' and x['period'] == '2024-Q4'), None)
# q4 为 None：单季所需输入缺失，不能当成零。
# q4['quantity']['value'] 为 None：输入/口径冲突；原因在 source.missing_reason。
```

`load_period_series` 不发布附件、不写库；只查询指定项目、选中主体。当前报告优先，其次同一项目同一主体其他已入库报告。返回：

- `quarters`：单季记录；`cumulatives`：年初累计记录（YTD1…YTD4），全年即 YTD4。
- 每条含 `metric / period / start / end / entity / scope / currency / document_id / restatement / basis_id / quantity`。
- `quantity` 为通用 typed cell：`value` 是原币元数值字符串或 None，`unit`、`currency`、`source` 完整保留。金额计算前按 unit 换算，消费方不要假设任意外部输入已是元。
- `reconciliations` 同时保留 `disclosed`、`derived` 记录及 `residual` typed cell；不以披露值覆盖推导值，也不为了配平修改任何输入。
- `unknown_rows`、`unrecognized_periods` 保留原始行和缺少日期等原因。
- `missing` 按指标/单季列出所缺累计输入及现有窗口来源；报告对应 `missing` 表。
- `records` 为编译 report 所需原事实；`inputs` 为进入代数前的完整来源记录。

目前基础流量指标为 `revenue / net_profit / parent_profit / deducted_profit / cfo`。合并利润和归母利润各自使用独立 metric，勿互换。

## 纯计算入口

`service.period_algebra` 不依赖 service/SQLite：

```python
from service.period_algebra import observation, derive_period_series

item = observation('revenue', quantity,
    entity='主体', scope='consolidated_CAS',
    start='2024-01-01', end='2024-09-30', document_id='报告ID',
    restatement='original', basis_id=None)
series = derive_period_series([item, ...], preferred_document_id='本期报告ID')
```

可直接复用 `identify_period`、`single_quarter(current, previous)`、`sum_periods(items)`、`change(current, previous, mode)` 和 `select_observation`。`mode` 为 `qoq / yoy / ytd_yoy`，返回 `delta / growth` typed cells。

日期优先于 period 字符串。没有日期、也没有明确累计/单季列头的 `2024-Q3` 保持 unknown；H1 和 FY 可按明确窗口解析。Q1 为单季兼累计；余额、EPS、比例不纳入流量加减。常规增长率要求基期为正，基期零/负保留金额差额并注明增长率不适用。

选择比较值先本期报告，再本报告调整后列；同优先级不同值保留候选、结果未知。推导 typed cell 的 `source.inputs` 中嵌入各输入的期间、口径和 quantity，可递归追溯到文档/页/表/行/列。`basis_id` 仅在明确同一会计基础时填写：当前年度数与本报告已重述比较数可共享此 ID；不能为绕过冲突随意填同一字符串。重述与未重述混用且无共同依据时不算。

## 已验收 / 尚待材料

伊利年报季度表：四指标 2024 Q4 披露减“全年−前三季”全部 0；12 个季度环比与 5 个全年同比共 17 个手算核对通过。Q2/Q3 的累计数在仅有年报季度表时来自前序单季相加，属于代数自洽验证；Q4 有独立全年披露校验。缺少上年季度金额时保持未知，不由披露增长率倒算。

伊利真实三季报已找到，完整入库仍待确认；批准前不宣称季报入库适配已验收。瑞和/卡罗特中报缺少所需前一累计期，单季未虚构。

③ 补充：同年重述累计数与未重述单季不会自动共享 basis_id；增加服务适配回归验证此路径。`service.workpaper_basis.quantify_restatement(pairs)` 是单一主体的纯计算入口，pairs 每项包含 `metric / label / period / scope / original / restated`，后两项为 typed quantities，返回 `(changes, ratio_impacts)`。`extract_adjustment_pairs` 可从原始 source_tables 获取配对，未知指标/期间另行保留。产品 kind 为 `basis_changes`；文本标记和多期非经常提示通过此 kind 获得。

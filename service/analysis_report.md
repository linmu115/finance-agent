# 同一份数值生成图表、CSV 与报告

`run_analysis(report=...)` 可省略 code。普通取数展示用它直接生成 report.md、各表 CSV、chart_data.json、图像和 presentation_bundle.zip。所有产物使用同一列换算后的精确值；Markdown 可以适当舍入，CSV 保留精度。此能力对通用、已准备数据、金融三个配置同样可用。

```json
{
  "title": "公司收入预测",
  "body": "预测期收入为 {{forecast.0.revenue}}。这一数值是机构预测。",
  "theme": "report",
  "tables": {
    "forecast": {
      "columns": {
        "year": {"label": "年度"},
        "revenue": {"label": "营业收入", "unit": "亿元", "decimals": 2},
        "eps": {"label": "EPS", "unit": "元/股"}
      },
      "rows": [{"year": "2027E", "revenue": {"record_id": "已查询的记录ID"}, "eps": {"record_id": "EPS记录ID"}}]
    }
  },
  "charts": [{"table": "forecast", "x": "year", "y": ["revenue"], "kind": "bar", "title": "收入预测"}]
}
```

数值单元格可直接写 `{fact_id:ID}`、`{record_id:ID}`，程序从本次挂载的规范数据取数、带上来源与币种。不要再次使用原表单位去缩放规范值。指定的 document_ids 须包含记录所属文档。

没有结构化记录时，或你用 Python 得到派生量，可写 `{value:"123.456",unit:"百万元",currency:"CNY",source:{document_id:"...",page:3,data_kind:"analyst_forecast"}}`。列定义选展示单位，程序换算；未知 value 使用 null。纯文本列不设 unit。

保存模型的数值可写 `{model:"base",path:"tables.forecast.0.revenue"}` 或 `{model:"base",path:"results.value_per_share"}`；base 是 model_refs 挂载别名。已知计算字段的金额倍率、每股值、比例从原模型确定，不重算模型。特殊字段无单位元数据时须提供 source_unit；已有单位不能用此参数改写。

复杂计算依然写 Python。在脚本末尾把上述对象写入 `/output/analysis_report.json`；执行结束后自动交付。或者 `from analysis_report import compile_report, render_chart, render_report`，以 `compile_report(report, records, models)` 返回的 `tables[name]['rows']` 为唯一展示数据，自由编排自定义图形；`render_chart` 返回可编辑的 fig、ax。不要为 CSV 和图分别手写缩放。

支持金额元/千元/万元/百万元/亿元/十亿元及 units/thousand/million/billion（币种独立）；股/万股/百万股/亿股；ratio 与 %；个百分点；元/股；倍；个；天。美元等币种也可使用 million/billion 和 currency/share。不做隐含换汇，百分比与百分点不能互换，金额不能当每股值。

`body` 的 `{{表名.从0开始的行号.列名}}` 从同一数据生成数字和单位。金融解释、假设和图形由你决定；不得把假设写成披露事实。数字表的来源详情随 chart_data.json 保留。图像自动生成支持 line/bar，复杂瀑布图、热力图等仍可用 Python；两种图都保留缺失值。

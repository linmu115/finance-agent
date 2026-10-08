# N4 ① 异常信号雷达验收

`kind=anomaly_signals` 通过既有 financial_workpaper 出口交付 report、CSV、Markdown 和 A1 数值表。九类共 38 行，observations 只含已触发现象；无 LLM 调用、无入库和主库写入，无服务/端口/Docker 操作。开发资料只读取指定公司的复制 SQLite，以 mode=ro 打开。

|开发资料|九类完整列示|可计算/已分类|缺失数值并说明|触发行|
|---|---:|---:|---:|---:|
|伊利 2024|9|35|3|9|
|瑞和 2025 中报|9|14|24|6|
|卡罗特 2025 中报|9|11|27|6|

卡罗特存贷双高虽有现金及已披露融资负债下限数值，但完整有息负债未确定，触发状态仍为未知。单独现金/债务比例触发只表示该项超过经验阈值，不宣称两者同时偏高。

16 个独立手算值全部一致，详见 `anomaly-acceptance.json`，逐值附文档/页/表/行列。伊利 PDF 第 8、87、92、153、164、62 页与瑞和 PDF 第 47 页已渲染并目视核对。关键结果：

- 伊利全年 CFO/合并净利润 2.5685827468，不触发全年转化不足；应计比率 -8.6959493292%。
- 应收同比增速减收入同比增速 +1.5550722273pp；存货增速减成本增速 -4.1106512486pp，均不触发。
- 伊利一年以上应收原值占比变化 +0.6399579764pp；存货跌价准备余额覆盖率变化 -0.8412695833pp，均不触发。没有重复加总“一年以内”与“小计”。
- 伊利 Q4 收入占全年 23.1039185076%，未触发集中阈值；Q4 归母利润 -2415.62035216 百万元而 CFO +7870.12810996 百万元，方向背离触发；四季度 CFO 没有被写成负数。
- 瑞和本期 CFO/合并净利润 -0.7457783834，正利润负 CFO 触发。逾期超过一年占应收原值比例变化 +3.5048907467pp，不触发；该表是逾期账龄，未混称发票账龄。
- 伊利更换会计师事务所来自 PDF 第 62 页；审计意见为无保留，强调事项与关键审计事项分别处理。中报未经审计保留为无本期审计意见，不判为非无保留意见。

## 验证

- Python 相关 25 项通过（signals、K1、年报），其后来源原句恢复及融资负债下限修订定向 5 项通过。
- Node financial-workpapers 3 项通过，覆盖金融专属暴露、A1 表登记与模型上下文投影；server TypeScript 检查通过。
- 编译和 Vite 构建通过。`npm run build` 的前置依赖检查拒绝用户指定复用依赖所用的 node_modules 目录联接，因此直接运行同一 `tsc` 与 `vite build`，没有改主目录依赖；仅既有大 chunk 提示。
- `git diff --check` 通过。

## 与 spec 的实现差异及理由

1. 文献没有跨行业通用数值阈值。每行明确写“本项目经验阈值 v1，未经行业校准”，附 [CFA 方法参考](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/evaluating-quality-financial-reports)。文献支持跨期/比率/利润现金差异的分析方法；20%、10 天等具体阈值是本项目初筛选择，不能冒称文献结论。
2. 存货“计提率”具体实现为准备余额/存货账面原值的两期覆盖率变化，明确不是当期计提费用率。只有一年计提发生额时不能伪造可比年发生额。
3. 融资负债只汇总有明确性质的借款、债券及租赁负债；不能把“一年内到期非流动负债”整项都当有息债务。返回下限口径，无法排除的情况保留未知。利息收益率披露资产范围局限，不以财务净收益或现金收息替代应计利息收入。
4. 季度信号暂用 K1 年报单季披露，`AnalystData.quarters()` 是 N2 期间函数接入点；中报不推测 Q4。N2 尚未交付公共接口，接入未完成。
5. 应收/存货增长差要求同日同比余额；中报只有年初余额时保持未知。周转天数差依赖比较期两端余额，缺失不借用其他时点。

专业优势尚待 N1 独立对照；这些确定性检查不是正式评分。

```powershell
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay-analyst-signals.py --old-copy .tmp/signals/old/finance.sqlite --current-copy .tmp/signals/current/finance.sqlite --output .tmp/signals/acceptance
& 'D:\AI\财报agent\.venv\Scripts\python.exe' -m unittest service.tests.test_workpaper_signals service.tests.test_financial_workpapers service.tests.test_workpaper_annual
node --import tsx --test tests/financial-workpapers.test.ts
node node_modules/typescript/bin/tsc --noEmit -p server/tsconfig.json
```

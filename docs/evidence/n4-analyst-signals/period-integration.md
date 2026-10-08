# N4 雷达接入 N2 期间函数

依赖 N2 提交 `d349e04` 中的 `service/period_algebra.py` 和 `service/workpaper_periods.py`，两个文件按该提交原样带入 N4 分支。没有合并 N2 分支，没有修改 N2 工作区或主目录；主线合并时两个文件与该版本一致，注册表仍需保留双方新增 kind。

`AnalystData.period_series()` 复用现有 Statement/Disclosure，通过 N2 公共 `period_inputs` 和 `derive_period_series` 一次取得期间序列。补充来源严格为当前项目、已选主体；不查其他项目。优先当前报告披露，缺单季时可按同口径累计差额计算；来源嵌套保留文档、页、表、行列、期间与重述信息。前三季比较直接复用 YTD3，或 N2 从连续单季求和得到的累计数，不要求已知累计期间必须同时披露三个单季。

## 验收

- 三份授权材料回放，既有九类 38 行及 16 个独立手算全部保持一致，触发集合不变。
- 伊利四指标 Q4 披露减累计推导均为零。Q4 收入 26,660,376,531.26 元、归母净利润 -2,415,620,352.16 元、CFO 7,870,128,109.96 元；瑞和和卡罗特只有中报时，Q4 保持未知。
- 3 项 N4 适配测试通过：真实年报四项勾稽；删除年报四季原表及规范记录后，由同项目三季累计推导 Q4，并验证两份报告的完整来源；混用重述与未重述累计数时明确未知。第二项同时验证缺 Q1 单季不妨碍使用已披露前三季累计。
- 原样运行 `d349e04` 的 10 项纯期间代数测试和 1 项真实年报适配测试，全部通过；未在 N4 分支注册或声称验收 N2 的 `period_analysis` 产品入口。N4 原有 5 项雷达测试也通过。
- 没有引入 LLM 调用、数据写入、端口或 Docker 操作。

机器证据为 `period-integration.json`，复现：

```powershell
& 'D:\AI\财报agent\.venv\Scripts\python.exe' -m unittest service.tests.test_signal_period_integration service.tests.test_workpaper_signals
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay-signal-periods.py --old-copy .tmp/signals/old/finance.sqlite --current-copy .tmp/signals/current/finance.sqlite --output .tmp/signals/period-integration.json
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay-analyst-signals.py --old-copy .tmp/signals/old/finance.sqlite --current-copy .tmp/signals/current/finance.sqlite --output .tmp/signals/period-integrated-final
```

季度数值的真实材料验收仍基于年报季度表；另一报告的累计来源路径由合成数据覆盖，未据此声称真实三季报入库或单季对照已经验收。该材料边界与 N2 交接一致。

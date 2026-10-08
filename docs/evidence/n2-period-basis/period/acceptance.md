# ④ 期间代数验收（2026-10-08）

分支 `feat/period-basis`，基于 `92e3a70`。确定性实现已验收；新增季报完整入库等待材料确认，未将年报内的代数核对冒充季报入库验收。

公共纯函数 `service.period_algebra.derive_period_series` 与服务适配 `service.workpaper_periods.load_period_series` 已交付。N4 接口、typed quantity 示例、缺项和口径规则见 `design/n2-period-api-20261008.md`。新 kind `period_analysis` 可直接生成 A1 数值表与下载交付。

仅查询已有旧库/当前库副本中指定伊利、瑞和、卡罗特项目。所有连接 `mode=ro`，无模型、无主库写入、无 held-out 读取、无 3001 操作。

伊利 2024 年报提取 16 个单季度金额。收入、归母、扣非、CFO 四指标 Q4 披露值与“全年−前三季合计”的残差全部为 0 元，来源及递归推导链在 `acceptance.json`。前三季累计数明确标为原单季求和，不伪装成另一份三季报披露。另有 Q2/Q3 的 8 项代数自洽勾稽，均为 0。

12 项季度环比和 5 项全年同比共 17 项与独立 Decimal 手算一致。没有上一年度季度金额的同比保持未知，没有从百分比反推金额。基期为零/负时常规增长率不适用，仍列绝对金额差。

瑞和、卡罗特各有 0 个可推导单季：半年累计缺少一季度等前序值。`missing` 表逐项说明；不是把半年当第二季度。已有可比累计增长率分别 1 项、2 项与手算相同，其余缺项保留。

单测覆盖 Q4/Q2 差额、累计识别、环比跨年、同比、累计同比、比较列优先、重述混用、显式共同口径、不同主体/币种/scope、缺项/非正基期、冲突来源、完整递归来源链及 tool 交付。相关 Python 42 项通过；补充 missing 输出后 12 项期间测试通过，并重新跑真实副本验收。

复现：
```powershell
& 'D:\AI\财报agent\.venv\Scripts\python.exe' -m unittest service.tests.test_period_algebra service.tests.test_workpaper_annual service.tests.test_financial_workpapers service.tests.test_workpaper_comparison service.tests.test_analysis_tables -q
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay-period-basis.py --old-copy .tmp/ashare/old/finance.sqlite --current-copy .tmp/ashare/current/finance.sqlite --output .tmp/period-basis/period-real
```

与 spec 的边界：全年、半年、单季流量已覆盖；不将余额、EPS、比例做期间相减。未有新季报入库验收；材料、来源、用量预算及 CPA 金额未知原因见 `design/n2-period-materials-20261008.md`。

# N4 ② 业绩变动归因验收

基于 `92e3a70`，在 `feat/analyst-signals` 独立工作区实施。入口 `financial_workpaper(kind="variance_attribution")`，输出 `bridge / contributions / drivers_evidence / contribution_sources / observations`；沿用 report、附件和 A1 登记。未增加工具名或模型调用。

## 真实数据结果

仅用明确授权的伊利旧库、瑞和与卡罗特中报的 SQLite 副本，连接 `mode=ro`；旧表适配只创建 TEMP view，不迁移、不写入源库。未读 held-out，未操作端口、主目录或 Docker。

以下均为百万元人民币。

| 公司 | 归母利润变化 | 营业利润残差 | 税前残差 | 合并净利润残差 | 归母残差 |
|---|---:|---:|---:|---:|---:|
| 伊利 | -1975.68046476 | 0 | 0 | 0 | 0 |
| 瑞和 | 79.226 | 0 | 0 | 0 | 0 |
| 卡罗特 | -61.311 | 0 | 0 | 0 | 0 |

伊利收入效应 -3376.67006009，毛利率效应 +1501.57116368，合计毛利变化 -1875.09889641。投资收益 +2448.41963494、资产减值 -3150.14609557、信用减值 -394.54239445。CAS 财务费用按原符号扣减，负财务费用不翻错方向；投资收益中的联营损益不重复相加；营业总收入中的金融子公司收入单列。瑞和已在 PDF 第 28 页核对公允价值比较列和联营损益本期列的显式“—”，恢复无发生额，空白或未披露不补零。

## 结构贡献与材料限制

- 伊利主营/其他业务视图的收入、毛利贡献完整勾稽，残差为零。三类主要产品的原文量价结构贡献 9 个数均与 PDF 第 19 页一致：液体乳 -60.46/-35.21/-9.70 亿元，奶粉及奶制品 +22.58/-9.15/+7.34 亿元，冷饮 -19.52/+3.03/-3.18 亿元（顺序为销量/价格/结构）。三项各自加总与原文收入变化一致。
- 伊利产品表只有本期收入和舍入同比；使用管理层**直接披露的变动额**，没有反推精确上期收入。成本用第 21 页两期明确成本组成，与本期成本总额匹配后加总。其他产品收入变化未知。三类已知产品贡献加上未分配收入 **86.69893521 百万元**，等于主营收入变化 -10340.30106479；毛利未分配 **53.33153448 百万元**。未分配额包含缺项及原披露精度，不能称为“其他产品的精确贡献”。地区、行业、分部缺少精确比较期时保留本期和缺失原因。
- 瑞和四类产品收入变化 -37.251/-18.376/-3.406/-1.586 百万元，合计 -60.619，残差为零；分部、地域收入也单独勾稽。分产品成本没有可用披露，毛利贡献未知，总毛利变化 -5.466 在未分配行。
- 卡罗特经营业务与地域两种视图分别保留，避免把不同范围相加。其分项为舍入金额，未能与唯一同口径独立总额匹配；总变化与残差保持未知。地域数据原库标为 segment，保留原维度且在独立视图中展示，没有擅自重新分类。

因此，spec 的“分产品贡献加总等于总变化”在瑞和收入上完整满足；伊利为**已知贡献＋明确未分配差额＝总变化**，不能称为全部产品精确归因通过。未为达到零残差捏造缺失比较期。

## 原文核对和计算方法

11 个金额参考值、9 个原文量价结构值核对通过；13 处原因经渲染 PDF 人工核对：伊利收入/成本/销售/管理/财务费用（18）、研发（19）、投资收益（210）、信用减值（211）；瑞和研发/销售/管理/所得税（13）、公允价值（14）。全部检索引用另检查属于对应文档且为原页原句。页码为物理 PDF 页。

证据明确标为“原文相关原因披露（不证明贡献公式的经济因果）”。例如商誉减值说明只能支持相关原因，不能据此断言解释全部资产减值金额。未检出原因的项目写“原文未说明”；检索范围、原句、页码均保留。不会把会计政策、库存变动原因或“不适用”勾选当作收入原因。

毛利拆解：收入效应 `(R1-R0)×GP0/R0`，毛利率效应 `ΔGP-收入效应`，交叉项归毛利率。两期精确同单位销量齐全时，按“总销量→产品占比→平均实现价格”拆分；平均价格为收入/销量，可能包含产品内部组合变化，不能等同于挂牌价。只披露产能不等于销量，不用于替代缺失销量；原文直接披露的量价贡献保留原精度。增加现有报告单位对吨/千吨/万吨、台/人/次的明确支持，供规范记录及来源链使用。

## 验证与复现

合成测试覆盖交叉项、正负效应、销量单位不一致、吨销量进入结构表、缺失比较期、显式无发生额与空白的区别、重复加总、因果原文误配、故意修改利润后的非零残差，以及 A1 数值绑定。

本次相关 Python 44 项、Node 3 项通过；服务端 TypeScript 与前端 Vite 构建通过。Vite 仅提示现有大于 500 kB 的 bundle，未改前端打包策略。`git diff --check` 通过。

```powershell
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay-variance-attribution.py --old-copy .tmp/signals/old/finance.sqlite --current-copy .tmp/signals/current/finance.sqlite --output .tmp/signals/variance-acceptance
& 'D:\AI\财报agent\.venv\Scripts\python.exe' -m unittest service.tests.test_workpaper_variance service.tests.test_workpaper_signals service.tests.test_financial_workpapers service.tests.test_workpaper_annual service.tests.test_analysis_report
node --import tsx --test tests/financial-workpapers.test.ts
node node_modules/typescript/bin/tsc -p server/tsconfig.json
node node_modules/vite/bin/vite.js build --config web/vite.config.ts
```

机器验收摘要为同目录 `variance-acceptance.json`。完整 report、typed workpaper、Markdown、CSV 及图表位于 `.tmp/signals/variance-acceptance/{company}/`；脚本可在相同副本上重现。使用主目录 node_modules junction；标准 npm prebuild 的链接检查不接受 junction，因此直接执行相同 tsc/Vite 编译命令。没有修改依赖或检查脚本。未进行服务 UI/真实会话验收或付费对照；相对通用 Pi 的专业优势仍由 N1 证明。

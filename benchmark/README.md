# 金融投研 Agent 工程验收集

这是本项目的工程回归与公司级留出挑战集，不是竞赛官方评分，也不是 FinQA 官方排行榜结果。开发回归、留出验证、界面测试和容器检查分别报告。

本轮结果（2026-10-04）：[可读说明](results/current-review.html)。首次公司留出原评分17/30；仅修正百分比显示单位合同后的同次只读复评18/30，整体仍失败。原报告、复评、全部分母和失败均保留，没有模型重跑。完整年报3298条仅代表已入库数量，定义审校失败、11条期间仍待解决；同一会话继续查询及真实Docker绘图6项检查通过。

## v0.4.1：公司级留出挑战

中国神华（能源）与柳工（工程机械）两家公司此前未用于本项目，官方原始年报取 7 页、固定 30 格。原文、标准答案和设计说明在 `versions/v0.4.1-holdout/`，下载包为 `../samples/financial-holdout-v0.4.1.zip`。在“数据集与测试”选择“独立留出验收”，最终实现冻结后仅运行一次；重复打开返回原结果。

首轮已于 2026-10-04（北京时间）完成，**未通过**：原报告 `results/pi-workflow-119624da-d46c-4978-a7b4-dd7d476d69d1.json` 为 17/30；评分器将公开 API 的百分比单位 `%` 误要求为 `percent`，仅纠正该合同误拒的同次只读复评为 18/30，保存在 `results/pi-holdout-119624da-unit-contract-rescore.json`。没有重跑模型或改答案。另 5 格原值、日期及原 PDF 坐标实际吻合，但被断行标签定位规则误拒，其诊断单列，未并入新的正式分数。7 格真实遗漏分别来自无框线表格发现缺失（5 格）及错误的百分比表头校验（2 格）。还有并发缓存被另一会话覆盖导致的审计来源不一致；流程也未全部通过。完整分解见 `results/holdout-v041-first-run-diagnostics.json`。

这是按常见表格结构与财务语义选择的挑战样本，不是随机抽样或无预训练污染盲测。逐格核对精确金额、期间、单位、版本、口径、概念与引用，并独立报告工程流程检查。30 格正确不代表全篇准确率。若按结果再修改实现，该集即降级为开发回归，下一轮需换未使用的公司。旧伊利/海尔 v0.4 提案在首次模型调用前发现历史重叠并撤回；原文件与撤回记录全部保留。

## v0.3.1：Pi 会话内的语义清洗

以下 37 格已经参与多轮调试，是开发回归；其通过率不能作为未见公司泛化能力的证据。

在应用左侧“数据集与测试”下载输入与标准答案，点击“快速测试”或“完整测试”运行。测试通过真实对话 API 创建独立项目，上传只登记；发送后由两段 Pi 会话调用 LangExtract 和官方 DeepSeek，分批写入 SQLite。标准答案在模型处理完成后才由宿主评分器读取。

- 当前测试集：`versions/v0.3.1-normalization/`（标准答案修订 2），10 份输入、37 个来源标准事实及 2 个禁止错误检查。
- 覆盖相对期间、季度与累计、百万单位、外币、原始与重述版本、分部、合并表头、动态指标，以及原始 PDF 摘页。
- 当前下载包：`../samples/normalization-benchmark-v0.3.1.zip`。原始全文测试包：`../samples/无需OCR财报测试包-4份.zip`，含 4 份、925 页原生文字年报。
- 运行：`node scripts/verify_pi_workflow.mjs --quick` 或去掉 `--quick` 跑全部输入；中断观察可使用 `--resume 原报告路径`。
- 页面运行使用 `POST /api/benchmark/run`，结果保存在 `results/pi-workflow-<id>.json`，并出现在页面的最近测试记录中。
- 完整原年报另由 `scripts/verify_full_report.mjs` 检查全文索引、候选表处理覆盖、来源标准值与所属 Pi 调用记录，记录 `results/pi-full-report-v03.json`。处理覆盖与语义准确率分别列出。
- 容器图表证据：`results/pi-semantic-chart-v03.json` 与同名 PNG，核对数据库原值、图表数据文件及实际绘图。

v0.3.1 只纠正一条 PPE 购置支付项目的等价标签误拒：原英文 `Payments for acquisition of property plant and equipment` 对应“购买物业、厂房及设备支付的现金”。新版匹配同时排除现金流入、处置、折旧、无形资产和非现金购置等不同概念，附 8 个正例、16 个反例。没有改动输入、任何数值答案、期间、来源位置或禁止错误；修订说明与旧文件哈希见 `versions/v0.3.1-normalization/revision.json`。这是见到误拒后作出的工程回归标准纠错，不是盲测。

原 `versions/v0.3-normalization/`、`normalization-benchmark-v0.3.zip` 及历史报告完整保留。v0.3 首次完整小型基准 `results/pi-workflow-01a20418-f585-48fd-acb4-2ab0b88431c9.json` 的成绩为 37/37 标准事实、2/2 禁止错误、10/10 流程检查；后一次 `results/pi-workflow-4c1fddcc-8854-4415-b687-81fdc15ede67.json` 仍保留其 35/37、11/12 及失败状态。后一次除标签误拒外还有真实的总资产期间错误，新版标签修订没有豁免该错误。新版标准和实现使用新报告及各自哈希，不给旧报告重新刷分；小型回归通过也不表示整份年报的全部事实已逐条核对。

## 历史 v0.1 / v0.2 问答评测

下列数据、题目与正式成绩作为历史基线保留。v0.2 正式 124 题 × 3 轮已经完成，均未达到全部门槛；具体见 `results/acceptance-report.html`。其冻结实现与新版语义清洗流程不同。

## 数据与规模

- 三份中文完整年报：贵州茅台2024（143页）、美的集团2024（295页）、伊利股份2024（270页），共708个PDF物理页。
- FinQA 官方 dev/test 原始数据及MIT许可证已保存，下载时固定Git提交，逐文件记录SHA-256。
- 共186题：中文字段提取30、计算12、纠错12、证据不足6、图像读表6；FinQA单步60、多步60。
- 开发62题：中文22 + FinQA40。验收124题：中文44 + FinQA80。两组公司完全不重叠。
- 中文2023比较值均来自同一份2024年报，不等于额外下载了2023年完整年报。
- 中文标准答案由Codex转录并对原表渲染图逐项视觉核对，未进行第二位人工标注者复核。后续独立复核同样由代理完成，不能称为人工双标。

## 目录与隔离

| 目录 | 用途 | 被评测Agent可访问 |
|---|---|---|
| `agent_input/` | 题目清单与净化后的原始材料 | 仅限单题允许材料，不能整目录挂载 |
| `evaluator/gold.jsonl` | 标准答案、计算公式、证据位置 | 否 |
| `evaluator/reference.sqlite` | 30条由Codex核对的财务事实，金额为精确十进制文本 | 否 |
| `sources/` | 完整上游数据、下载链接、许可证 | 否，FinQA原文件包含答案 |
| `review/` | 建集时的原表核对材料 | 否 |
| `runtime_acceptance.json` | 12项系统验收规范（SPECIFICATION） | 测试宿主可读，实际状态另见 `results/acceptance.json` |
| `versions/v0.2/` | 独立复核后的题目、gold、变更与版本清单 | 仅单题题目可发送；gold与复核标签不可发送 |

必须先使用 `prepare_case.py` 导出单题包。OCR题只得到图像；不能获得原始PDF、其他题答案、完整工作区或先前任务缓存。每题使用独立项目、索引与会话。开发和验收应使用不同项目数据目录。不能直接在当前包含答案的项目目录里启动被评测Pi。

## v0.2 来源复核与正式运行

原始 v0.1 文件不被覆盖，全部186题及其开发62/验收124划分保留，不因歧义或难度删题。`review/curation-*.json` 保存独立代理复核：先只读题目和允许材料、保存先验答案及哈希，再与旧gold比较。v0.2标准答案不采用任何模型预测作为依据；这不是人工标注或盲测。

- 唯一可确定但旧标签错误的题标 `corrected`；一致的标 `verified`。
- 时间、范围或问题本身有真实歧义的题标 `ambiguous`，预期 `status=insufficient_evidence`、`answer=null`、`reason_code=ambiguous_question_or_source`，并引用证明歧义的材料。单题标签和条件答案不交给模型。
- FinQA不再依赖含混的 `finqa_execution` 单位；每题公开协议指定ratio、percentage_points、million_USD、USD_per_share、number等字面单位，允许的维度换算由评分器明确规定，不从答案大小猜测单位。
- `evidence_sets` 的每一组都必须独立充分；满足一组即可，不强求把所有等价组全部引用。年份/单位/表头等额外合法引用记录在 `valid_context_citations`。
- 原文舍入与表格精确值不同的少数题，预先保存 `supported_rounding_variants`，分别绑定数值、充分证据和固定容差；不全局放宽精度。
- 各题审核源文件SHA256、先验记录、计算式、旧标签和改动理由均保留；版本构建会验证审核完整性。

```powershell
python benchmark/scripts/build_reviewed_benchmark.py
npm run benchmark -- --version 0.2 --split dev --runs 1 --concurrency 3
npm run benchmark -- --version 0.2 --split acceptance --runs 3 --concurrency 3
python scripts/assemble_acceptance.py
```

正式三轮运行前冻结代码、依赖、配置、材料、题目及复核版本；每轮逐题建立独立数据库与会话。每个结果保存来源哈希、工具记录、调用量和延迟。已知运行中代码变化的旧基线保留 `known-code-change.json`，不得冒称同一冻结实现成绩。

## v0.1 历史协议与运行

以下保留原版协议用于复现已有历史基线；正式v0.2以版本题目及其返回协议为准。

Python标准库即可准备题包、评分和运行评分器测试，不需要模型API密钥。仅重建/核对PDF时使用已安装的PDF工具。

```powershell
python benchmark/prepare_case.py midea_2024_extract_revenue_2024 benchmark/runs/example_input
python benchmark/evaluate.py predictions.jsonl --split acceptance --output benchmark/results/acceptance.json
python -m unittest discover -s benchmark/tests -v
```

`example_input`必须是新目录。把每题的结构化回答收集成JSONL，每行一题。问题自身不是完整的接口协议；调用模型时还应附下面的返回格式与其`response_contract`。

```json
{"id":"midea_2024_extract_revenue_2024","status":"ok","answer":"407149600000","unit":"CNY","period":"2024-FY","scope":"consolidated_CAS","citations":["midea_2024:p9"]}
```

这是开发文档中的返回格式示例，不能注入被测Agent的验收提示。生产评测应仅发送不含数值的JSON Schema。

- 数值以十进制字符串输出。人民币金额一律元；百分数用9.44表示9.44%；倍数直接输出比值。
- `assets`和`equity_parent`的period为`YYYY-12-31`；年度流量为`YYYY-FY`。
- 中文统一`scope=consolidated_CAS`，财务指标名称必须对应归母口径或集团口径，不能互换。
- 纠错：answer必须为JSON布尔值，同时输出corrected_value、unit、period、scope和citations。
- 证据不足：status=`insufficient_evidence`、answer=null、reason_code=`period_not_in_source`、citations=[]。
- FinQA：unit=`finqa_execution`，沿用原始计算程序结果约定，不自动猜测百分数与小数的100倍转换；证据引用输入JSON已提供的`source_id:text_N`或`source_id:table_N`。
- PDF引用页码从1开始，指物理页；伊利PDF第7页的印刷页码是3，美的PDF第9页印刷页码是8。
- 错题、超时和缺失回答仍计入分母；重复ID或非当前split的ID导致协议校验失败。

## 数据评分门槛（工程验收约定）

| 类别 | 最低答案准确率 |
|---|---:|
| 中文提取 | 95% |
| 中文计算 | 95% |
| 中文纠错 | 90% |
| 证据不足 | 100% |
| 图像读表 | 90% |
| FinQA单步 | 85% |
| FinQA多步 | 75% |

此外，引用位置宏平均召回率和精确率均须>=95%，答案正确且证据合格的题目比例>=85%。小样本类别阈值会产生离散效应，例如验收集8道计算题在95%门槛下需8道全对。

金额容差0.01元；同比0.005个百分点；比值0.00005；FinQA执行结果容差0.000006（适应官方5位小数舍入）。不使用相对金额容差，不自动接受100/1000倍单位错误。

引用评分只验证预标注证据定位，不等于已证明自然语言论证正确。中文任务限定主要会计数据表；v0.1 FinQA采用官方支持事实集合，并不保证所有等价证据穷尽；v0.2采用独立复核的充分证据组及明确上下文。开放式投资报告暂未纳入自动数值分数，需要另外盲评事实、论证、风险和反向验证条件。

## 完整系统验收

只有数据门槛通过，加上 `runtime_acceptance.json` 12项全部完成，才算本项目完整验收。该文件是规范，实际执行证据在 `results/acceptance.json`；S10历史规范保留“人工视觉检查”，当前实际图表检查由代理完成，未经第二人复核，不宣称人工验签。评分器始终显式标记未执行系统门槛，不会用数据分数代替容器安全、图表质量或可复现性。

三次重复运行应在同一冻结配置下进行，保存模型名称/版本、embedding版本、提示与工具版本、依赖锁、文件哈希、容器镜像digest、每轮调用量/费用/延迟和可信宿主采集的工具事件。低温度不保证文本逐字相同，验收关注数值与证据一致性。

## 数据来源、版权与限制

- [FinQA官方仓库](https://github.com/czyssrs/FinQA)，Chen等，EMNLP 2021。保留 `sources/finqa/LICENSE`。本地抽样只包含可独立重算的算术题，按单步/多步各半，不能把得分称为完整FinQA分数。
- [贵州茅台2024年年报](https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF)。
- [美的集团2024年年报](https://www.midea.com.cn/content/dam/mideacn-aem/%E6%8A%95%E8%B5%84%E8%80%85%E5%85%B3%E7%B3%BB/%E6%8A%95%E8%B5%84%E8%80%85%E5%85%B3%E7%B3%BB%E6%96%87%E4%BB%B6%E6%80%BB%E8%A7%88/2024%E6%96%87%E4%BB%B6/%E7%BE%8E%E7%9A%84%E9%9B%86%E5%9B%A2-2024%E5%B9%B4%E5%B9%B4%E5%BA%A6%E6%8A%A5%E5%91%8A.PDF.coredownload.inline.pdf)。
- [伊利股份2024年年报](https://static.cninfo.com.cn/finalpage/2025-04-30/1223421123.PDF)。

报告属于公开披露材料，不因此获得开放数据许可证；原报告权利归原作者/发行方。现为用户授权的本地研究副本，不发布全文镜像。若公开项目，优先发布来源清单、下载程序、校验值和事实标注，保留上游许可说明。

这是一份公开、规模较小的回归集。FinQA可能已经出现在模型训练数据中；按公司分组也不能排除预训练记忆。OCR图像来自清晰PDF栅格化，不代表真实拍照、歪斜、低清扫描。当前任务主要围绕财务指标，不足以证明所有金融投研方向的性能。后续正式验收还应加入另一家公司/年度的未见材料及第二人复核。

## 交付状态

已完成正式应用、数据下载/来源锁定、样本生成、参考SQLite、评分器、单题输入导出、真实解析/OCR、官方DeepSeek工具调用与浏览器验收，以及真实Docker图表和隔离采证。可选Embedding API未配置时使用FTS5回退，不将其成绩描述为向量检索成绩。v0.2独立复核版本正在接入正式重复评测，最终模型成绩另行记录。

证据入口：`results/acceptance.json`、`../web/test-results/`、`../sandbox/evidence/`、`../scripts/dependency-evidence/`。页面展示、评分器标准答案自检、固定API前端测试与确定性解析准确率，均不能冒充真实模型成绩。论文中的图表与文档渲染也只完成代理视觉核对，未获第二人复核。

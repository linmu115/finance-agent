金融研究 Agent v0.3 · 应用与复现（2026-10-04）
================================

【2026-10-04 收尾交接】先阅读 HANDOFF.html 或 HANDOFF.md。
当前源码是未部署、未完成真实模型验收的 v08 候选；本机3001仍运行v07。
最新状态以 WORK_STATUS.md / HANDOFF.md 为准，下文保留历史使用与复现说明。
压缩包不含 data/、密钥或已安装依赖，不是完整运行状态备份。

正式应用：http://127.0.0.1:3001
原型：design/workbench.html（页面中的“打开正式应用”可跳到真实服务）
架构说明：design/architecture.html
财报看板：应用左侧“财报看板”，按类别筛选、选轴制图、查看原文并导出。
数据与测试：应用左侧“数据集与测试”，下载原始年报及 benchmark，并运行真实模型测试。
新公司整表留出：samples/financial-holdout-v0.5-evaluation.zip，4张逻辑表、146个数值格；同预算比较金融工作台与通用Pi，目前尚未启动正式模型验收。
研报纠错：samples/financial-report-correction-v0.1.zip，12个错误、16条正确事实或计算、3条合理观点；这是任务级挑战，不是新公司留出，目前尚未执行。
旧v0.4.1已降为开发回归。首次原评分17/30、仅纠正百分比显示单位合同后的同次只读复评18/30均保留，不再作为未见公司泛化成绩。
v06定义复核完成61/66组、82条事实；旧定义锚点14/15、区分8/9。最后一批输出截断，随后API返回402；全部3298条财务事实的数值和来源保持。整体目标尚未完成。
本轮进度：benchmark/results/upgrade-progress-v06.html，或应用“数据集与测试”中的本轮进度链接；历史结果：benchmark/results/current-review.html。
本机现已部署v07运行修复：有限分批、已验证历史截断复用、原缓存复验登记、续跑用量核对。142项Node、295项Python检查通过；真实模型续跑仍待新的余额恢复确认，不能据组件检查宣称整体验收完成。版本与公开配置见benchmark/results/release-v07-20261004.json。
设计与评分：benchmark/design.html；竞赛定位及未来路线：design/roadmap.html。
37格 v0.3.1 属于反复调试的开发回归，不能用其通过率代替未见数据验证。
论文：paper/ 中的可编辑 DOCX、PDF、HTML；当前版本和范围见 paper/README.md。
新版围绕持久 Pi 会话完成 LangExtract 语义清洗、共享数据和分类看板。
历史 v0.2 问答验收124题×3轮未达到全部门槛；该历史结论独立保留。

模型
----
本项目选定 DeepSeek 官方 DeepSeek-V4.1-Flash。
Base URL：https://api.deepseek.com
API 模型 ID：deepseek-flash
依据：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
不要把营销版本号“v4.1”直接填写成 API 模型 ID。

主模型使用官方 API，不需要部署本地大模型。
本阶段使用逐页全文、表格坐标、SQLite FTS5 关键词索引和自动生成的 YAML 目录，不调用 Embedding。
LangExtract 的语义清洗调用由所属 Pi 会话的统一模型运行时执行，使用同一个 DeepSeek 配置。
OCR 默认使用本地文档识别器；这是文档解析组件，与主对话模型分离。

怎样使用
--------
1. 打开正式应用。左侧新建项目与对话；项目用于隔离文档和分析产物。
2. 左下角或右上角“API 配置”可修改 DeepSeek、搜索服务、OCR与运行上限；清洗和对话使用同一主模型。
3. 在对话输入框按“+”添加 Excel、CSV、TSV、PDF，或拖入附件。
4. 同一消息写明任务，例如“计算2023/2024收入同比，给出引用并画图”。
5. 上传只保存附件。发送后，当前 Pi 会话调用 process_documents，读取全文、通过 LangExtract 理解字段，分批清洗财务主表及附注表并入库。看板读取已提交的数据。
6. 点回答下面的来源，查看原文页或表格位置；图表和JSON产物可以下载。
7. 每段对话独立运行、停止，切换会话不停止原任务。同项目共享数据，不同项目分开。
8. Pi Session 持久保存完整工具上下文，刷新页面可恢复进度；服务重启后可以在原会话继续处理。
9. 财报看板支持公司、期间、口径、币种、重述版本及分部筛选，以及横轴、指标和柱状/折线图选择。
10. 可直接问 Agent“这个项目有哪些数据、数据库存在哪里”，它会查询真实数据目录。
11. 联网研究通过搜索工具找资料、归档原文，再引用正文；搜索摘要不能代替原文证据。
12. “研究成果”可查看财务分析、情景模型、估值与备忘录，修改假设并保存版本；依赖旧版本的成果会标为需更新。
13. 同项目另开会话可继续已有研究。DCF可直接引用情景模型的指定版本，保留输入及依据，避免模型手工抄写丢失元数据。

历史示例项目“财报研究 · 三公司对比”：三份完整年报共708页，
经当前真实官方API分析和Docker绘图；6个营收原值对参考SQLite逐项匹配，
亿元图值换算也匹配。选择该项目即可查看已有对话、原文引用和六柱中文图。
历史示例证据：benchmark/results/demo-latest.json 与 demo-latest-artifacts/。
只读浏览器检查5项通过，PNG显示/实际下载、三份来源及刷新历史已核验。
图表经过Codex视觉核对，未经第二人复核；示例成功不替代正式评测未达标结论。
旧项目“财报示例 · 茅台、美的、伊利”及demo.json/demo-artifacts/保留作历史证据。
交付包保留这些结果，不含本机应用data；在新机器中需重新上传报告建立项目。

模型只拿到工具返回的相关资料；完整原文件保存在本机 data/。
通过外部 API 分析时，被选中的证据片段会发送给配置的服务商。
密钥由后端加密保存：Windows 使用当前用户的 DPAPI；浏览器不持久保存明文密钥。
不要把 data/、.env、沙箱私钥或运行时镜像复制进公开源码包。

当前机器启动
------------
推荐双击项目根目录 start-finance.cmd：它会检查并启动独立后台服务，
等待服务就绪后打开浏览器。重复双击会复用已有服务。
若本机已有配好的项目内绘图虚拟机，也会一并启动；不会下载或安装模型。
关闭浏览器不会停止后台服务；电脑重启后再次双击即可。
启动诊断日志保存在 data/runtime/，不含在交付包中。

在本目录运行：
    npm start

前端已构建时，Node 服务同时提供页面与API，无需另外打开Vite。
开发前端可运行：
    npm run web
浏览器开发地址由 Vite 输出；后端仍需 npm start。

科学计算沙箱需要真实 Docker。当前机器采用项目内 Linux VM + Docker：
    .venv/Scripts/python.exe sandbox/portable_vm.py status
    .venv/Scripts/python.exe sandbox/portable_vm.py start

没有 Docker/VM 时，查文档和 Decimal 公式仍可运行，自由代码分析返回 runner_unavailable。
不会把自由分析代码降级到宿主机直接执行。
详细准备、启动和停止说明见 sandbox/README.txt 及 sandbox/README.md。

新机器准备
----------
本版主要验收环境：Windows，Node 24，Python 3.12。
先安装对应运行环境，然后在项目目录：
    py -3.12 -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.lock.txt
    npm ci
    npm run build
    npm start

首次启动后在页面填项目专用 API Key。交付包不附带密钥。
已有 Docker 引擎可按 sandbox/README.md 构建科学计算镜像；
没有 Docker 的 Windows 机器可按其便携 VM 流程配置，准备过程需要网络下载。
浏览器测试使用 Playwright 与 Microsoft Edge；其他系统需安装相应浏览器并调整 channel。

验证命令
--------
    npm run typecheck
    npm test
    .venv/Scripts/python.exe -m unittest discover -s service/tests -v
    .venv/Scripts/python.exe -m unittest discover -s benchmark/tests -v
    node web/tests/browser-workbench.cjs
    node scripts/verify_pi_workflow.mjs --quick
    node scripts/verify_pi_workflow.mjs
    node web/tests/browser-contract.cjs

注意：browser-contract 使用固定API响应，不能当成真实模型结果。
browser-workbench 检查多会话并行及看板交互，也是固定 API 响应测试。
verify_pi_workflow 通过真实应用、Pi、LangExtract和当前官方DeepSeek测试；会创建独立项目并产生API调用。
新版语义清洗数据集为 benchmark/versions/v0.3.1-normalization（标准答案修订2），
下载包为 samples/normalization-benchmark-v0.3.1.zip；标准答案仅在宿主评分阶段读取。
本次只修正 PPE 购置支付项目的等价标签误拒，没有改输入、数值答案、期间或来源。
旧 v0.3 目录、ZIP 和正式报告保留原始内容与哈希，新成绩单独保存，不给旧报告刷分。
修订依据及正反例见新测试集中的 revision.json 和 label-equivalence-tests.json。
原始年报测试包为 samples/无需OCR财报测试包-4份.zip；可从“数据集与测试”直接下载。
旧 browser-live / browser-agent-live / browser-demo-live 保留为 v0.2 界面回归记录，
其中上传自动解析和验收中心的旧断言不适用于新版，不能当作当前已通过的检查。

历史 v0.2 财报问答评测（不代表新版语义清洗成绩）
--------
    python benchmark/scripts/build_reviewed_benchmark.py
    npm run benchmark -- --version 0.2 --split dev --runs 1 --concurrency 3
    npm run benchmark -- --version 0.2 --split acceptance --runs 3 --concurrency 3
    .venv/Scripts/python.exe scripts/assemble_acceptance.py

每题使用全新数据库、项目、会话和输入目录。
Agent 只收到 agent_input/ 中该题允许的材料；
v0.1 的 evaluator/gold.jsonl、v0.2 的 versions/v0.2/gold.jsonl 及参考SQLite仅由可信宿主评分器读取。
不要把参考数据库导入产品作为所谓“解析完成”的事实表。
标准答案、题目、来源文件及评分器的说明见 benchmark/README.md。
正式结果（每轮124题）：
    轮次    答案正确              答案与证据联合正确
    第1轮   104/124（83.87%）      86/124（69.35%）
    第2轮   109/124（87.90%）      83/124（66.94%）
    第3轮   103/124（83.06%）      84/124（67.74%）
三轮结论一致性为90.3226%，低于S12的95%门槛；一致性不等于答案正确率。
三轮均未达到全部数据门槛：第1轮图像读表和FinQA单步不足，
第2轮FinQA单步不足，第3轮FinQA单步及多步不足。
可读汇总见 benchmark/results/acceptance-report.html；逐轮完整指标见
benchmark/results/agent-2026-10-03T06-37-06-859Z-summary.json。
v0.1 完整保留为历史基线；v0.2 保留全部186题、原始材料与开发/验收划分。
v0.2 采用代理独立核对的答案、明确单位、充分证据等价组及有引用的歧义拒答。
复核先读题目和材料并保存先验，再核对旧标签；不是人工双标，也不是盲测。
正式三轮开始后必须冻结代码、依赖、配置及题目，不根据验收答案修补输出。
中断后可用 --resume 指定原运行目录，配置/实现不一致会拒绝续跑。

目录
----
web/       React + TypeScript 对话界面
server/    Node API、Pi SDK Agent、SSE、凭据配置与审计
service/   Python MCP，解析/OCR/LangExtract/SQLite/FTS5/YAML/Decimal工具
sandbox/   科学计算容器及可信宿主启动器
benchmark/ 输入、标准答案、评分器、真实运行证据
paper/     可编辑论文与渲染结果
scripts/   评测、验收汇总和辅助操作

可信边界
--------
Pi 只有金融工具白名单，没有 shell、全盘读写或任意SQL工具。
project_id 由宿主绑定，模型不能改成其他项目。
自由分析运行在独立容器：输入只读、默认断网、无模型密钥和数据库凭据，
非root用户、2 CPU、2GiB内存、64 PID、最长120秒。
产物只从本次任务目录导出，并校验路径、符号链接、大小与哈希。
这是本机单用户工程方案，不代表已经通过敌对多租户审计。

实验解释
--------
测试是否通过以原始报告为准，不以功能页面的存在代替验收。
解析准确率、模型答案准确率、引用准确率和容器安全检查是不同结果。
公开年报/FinQA 可能存在预训练污染；部分年报也曾用于解析器回归。
“验收集”是冻结后的工程回归集，不能宣称完全未见材料的盲测。
官方 API 使用服务端别名，记录了配置和调用时间，但不能冻结服务商的内部权重。

已取得的工程证据
----------------
- React 前端固定响应契约检查14项通过；这组不证明模型能力。
- 真实服务上传/解析浏览器检查9项通过；使用合成 CSV/TSV/Excel/PDF fixture。
- DeepSeek 官方 API 浏览器 Agent 检查9项通过：解析等待、SSE、真实工具、
  计算引用、来源抽屉、停止和刷新历史；真实报告在 web/test-results/。
- 验收中心只读展示检查7项通过；已验证真实容器PNG在历史对话内显示。
- 科学计算与隔离有真实 Docker/宿主采证；不能把页面状态当作容器证据。
- S01-S12 的实际状态见 benchmark/results/acceptance.json，规范见
  benchmark/runtime_acceptance.json。正式 v0.2 三轮评测已完成：
  10项工程检查通过；S10为部分完成；S12未通过，整体验收未通过。
  S10 原规范保留“人工视觉检查”条款，数值与代理视觉核对已通过，
  人工复核未执行，不等于人工验签；不宣称完整系统全部验收通过。

依赖安全与安装复现
------------------
Pi 1.0.0 发布的 shrinkwrap 固定了有漏洞的 brace-expansion 5.0.9。
root override 无法覆盖该固定项，因此 postinstall 使用 vendor/ 中的官方
5.0.12 tarball，经SHA512核验后，只更新该嵌套依赖与对应锁条目。
npm ci 后执行 npm run deps:check；start/dev/build/typecheck/benchmark
也会先检查官方文件完整性。使用 --ignore-scripts 的安装必须再执行 deps:repair。
普通安装、隔离 clean npm ci、再次安装及篡改拦截都已验证，最终显式 npm audit
为零漏洞。npm ci 自带的摘要可能在 postinstall 前计算，需以安装后 npm audit
为准。完整记录：scripts/dependency-evidence/README.txt 与 reproduction.json。

交付包
------
    python scripts/package_delivery.py --dry-run
先生成 deliverables/delivery-plan.json，包含明确文件清单、大小、SHA256和
密钥模式扫描计数，不生成ZIP，不打印任何匹配值。最终论文与新版示例
结果已核对；生成完整交付包：
    python scripts/package_delivery.py --build
脚本仅打包允许清单中的源码、锁、官方安全依赖包、财报研究副本、评测版本、
独立复核、指定DeepSeek证据、容器安全证据、论文及 web/dist。
应用 data/、全部 local-model/、node_modules/、.venv/、密钥与设置文件、
沙箱和论文运行时、下载文件、安装验证临时目录均不会进入交付包。
模型记录只保留官方 DeepSeek 且有配置/提示哈希的运行；仅包含manifest、
重复性记录、指定轮次汇总/trace/预测与单题result及脱敏audit.jsonl，
保留已知代码变更说明与解析并发修复证据，排除case-local data。
最新示例的指定JSON/PNG及acceptance-report.html也在允许清单中。
这是用户授权的本地研究交付包，包含公开年报研究副本；不作为公开全文镜像。
扫描包含一个已核验的本地OCR测试合成凭据豁免，严格绑定文件路径、
完整文件哈希与测试值哈希；任一变化即失效，其他命中继续阻断打包。
模式扫描不能证明不存在任意形式的秘密，尤其不能识别图片中的文字。

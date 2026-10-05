# 工程论文与历史稿件

当前应用 **v0.2.0** 对应的新论文：

- [《从财报问答到证据驱动的金融研究 Agent：设计、实现与工程演进》](v0.2.0/finance-agent-technical-paper.md)
- [PDF 阅读版](v0.2.0/finance-agent-technical-paper.pdf)
- [证据与复现说明](v0.2.0/README.md)

新稿覆盖立项、工具调用、数据模型、沙箱、附件流向、权限、技能、原生 Pi 接入、成本优化、研报和资产看板。下方及同目录 `financial_analysis_paper_v0.1.*` 均为历史稿件，不表示当前版本的评测成绩。

## 历史初稿

本文及同目录 DOCX/PDF 对应历史 v0.2 评测，尚未同步当前 v07 的 LangExtract 清洗、联网研究与估值升级。旧论文、旧成绩保留原件；本轮状态见 [升级进度](../benchmark/results/upgrade-progress-v06.html) 与 [当前工作记录](../WORK_STATUS.md)。真实公司研究及新整表/纠错验收完成后再生成新版本，不把未运行项目写成论文成果。

题目：《基于工具调用与证据追踪的财报分析系统设计与实现》。作者、单位留待填写。

当前归档为12页、约8,863个汉字（含标题、表格、图注及参考文献；全文不含空白共13,036字符）。最终12页均经Codex逐页视觉检查，后6页由另一代理再次核查；这不是人工签验。

交付文件：

- `financial_analysis_paper_v0.1.docx`：可编辑 Word 初稿。
- `financial_analysis_paper_v0.1.pdf`：同一 DOCX 经项目内 LibreOffice 转换的审阅版。
- `financial_analysis_paper_v0.1.html` 与 `architecture.png`：浏览器审阅版。
- `manuscript.json`、`experiment-update.json`、`content_snapshot.json`：基础正文、汇总报告覆盖层、最终内容快照。
- `experiment-import.json`：22份结果及支持性报告的来源路径和 SHA-256；不含密钥或逐题答案。
- `render/visual-qa.json`：逐页视觉检查、页图与交付件哈希；`render/html-qa.json` 为浏览器布局检查。

本文是已完成三轮冻结评测的工程初稿，不是比赛官方成绩，不声称 SOTA 或所有条件通过。

正式结果来自 `benchmark/results/agent-2026-10-03T06-37-06-859Z-summary.json`：124题重复3轮，答案正确104、109、103题；答案及证据正确86、83、84题。结论一致112/124（90.32%），低于95%；代码、题库和模型配置按记录冻结。系统汇总为10项通过、S10部分完成（人工视觉检查未执行）、S12失败，数据与运行门槛未全部满足。首轮20项答案契约失败与18项纯引用失败的只读分类见 `benchmark/results/acceptance-round1-error-analysis.json`；该分析不改原分。

证据版本严格区分：

- 旧v0.1开发记录有并发代码变化，只作开发失败基线。
- v0.2开发62题与正式124题三轮分列；全部186题保留。FinQA标签采用先解原材料再比旧标签的独立代理复核，不称人工双标。
- `financial_pipeline.json` 的90/90属于历史parser 0.1.1，同30个事实重复三轮，每轮实际读取708页。它不是新parser的重复测试或模型成绩。
- 中止验收保留6/20次美的全篇入库ResizeImgError。底层原因未确证；parser 0.1.2加线程约束和共享OCR锁后8次并发全文回归成功，并修复年度表头错误继承至季度表；21项服务测试通过。
- 最新独立演示使用 `demo-latest.json` 与 `demo-latest-artifacts/verification.json`，parser 0.1.2重新上传三份完整年报，6个CNY原值精确核对；绘图亿元值4位小数、柱顶1位小数。只有Codex代理视觉检查，不能替代S10规定的人审。旧demo仍在原目录归档。
- 实测评测未启用Embedding，实际为词项检索。向量接口只完成协议/缓存夹具测试。

复现生成命令（项目根目录）：

```powershell
& 'C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' paper/sync_experiments.py --summary benchmark/results/agent-2026-10-03T05-59-01-524Z-summary.json --summary benchmark/results/agent-2026-10-03T06-37-06-859Z-summary.json
& 'C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' paper/build_paper.py
& 'C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' paper/render_paper.py
& 'C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' paper/verify_html.cjs
```

`sync_experiments.py`只把所选报告的汇总指标写入正文；首轮诊断报告仅记录hash，正文使用经只读核对的分类描述，不复制逐题预测或隐藏标签。缺少完整冻结条件的记录不能标为正式三轮验收。每次重新生成后必须再核对逐页PNG，并更新视觉QA记录；脚本运行本身不等于已完成视觉检查。

渲染使用 documents 技能的官方 `render_docx.py`，明确指定项目路径 `paper/runtime/libreoffice/LibreOffice/program/soffice.exe`（26.2.6.3），不查找桌面安装。官方MSI由The Document Foundation签名，Windows验证Valid，SHA256为 `f9877032fd908beb9c0ddf06df4af5c2e85f419c42e14876c4cce5aae5fb2660`。仅解析MSI并复制CAB内容，未安装系统软件。`runtime/`是本机依赖，不纳入交付压缩包；页图也只用于内部QA。

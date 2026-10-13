# F1 两期执行约定（已审定，尚未开跑）

本文件把 Claude 2026-10-08 的审定落实到执行器。正式入口为 `runner-f1.mjs`；旧 `runner.mjs` 仅保留历史开发演练用途。当前不运行付费参评，青啤亦等 F1 上线通知才从旧断点续跑。

## 题链与顺序

`f1-config.json` 保存原题全文、项目和依赖。第一期 D1/D2/D3/X4/X5/X6：24 回合、20 条链；第二期 X1/X3/X7/H1/H2：20 回合、16 条链。每题 prepared/financial 各 2 次；同题两组相邻，第二次反转两组先后，第二遍反转公司块，块内保持依赖顺序。44 回合、36 个新会话；X2 本轮记为“未执行”。

每次 `plan` 生成新的批次 UUID，键为 `F1_<UUID>_<P或F><重复>_<根题>`。D2/D3、H1/H2 在本组本次复用会话和键；其他题链全部不同。请求按主线 [隔离交接](../../docs/evidence/evaluation-isolation-20261008/handoff.md) 传 `evaluation.isolation_key`，每次续题也传原键。`budget_group_id` 按回合独立，预算不是隔离机制。读取运行及会话回执核对实际隔离键，审计原样保留。

两组用 3001 同一模型 CPA `gpt-6-luna`；只改每条请求的 `evaluation.profile`，不修改全局配置。`documentIds: []`，不触发材料重新入库。题面逐字沿用批准版本，参考答案不送参与者。原生推理路由和原有 evaluation budget 不变；实际强度及模型请求以审计为准。

## 冻结

F1 必须同时包含 N4 采用率修复、N3 按表搁置继续推进和成果隔离，部署与唯一重启由主线负责。执行器只读运行态，不启动/停止服务、Docker 或端口。

1. 一次 `freeze` 固定 F1 commit/tree、实际监听 PID/启动时刻、健康、所有产品源代码/编译输出/技能/沙箱/依赖文件摘要、公共模型设置摘要、题面及执行/评分程序、主线两组有效配置文件原副本和环境说明。设置仅留摘要，不落凭据。未提交差异清单保留；运行目录字节摘要使已加载构建与源码都可核对。
2. 第一期开跑前 `freeze-phase 1`，第二期年报准备结束后 `freeze-phase 2`。原文页表、PDF 指纹、文档 profile、财务事实、研报记录、疑点、解析及清洗进度、项目规则/技能从只读 SQLite 一致读事务和文件获得，按固定顺序导出。**同一代码 F1，分别保存 F1-P1/F1-P2 数据快照**；允许两期之间按授权继续入库，不伪称两期资产完全相同。
3. 第一阶段参考已冻结；第二阶段 `reference-phase2.json` 和 `selectors-phase2.json` 等 N1 准备完成，当前故意不存在，不把旧草稿冒充正式参考。第二阶段只新增金标数据文件，不改 F1 代码/执行与评分方法。
4. 每次发送分析前及一期结束时，核对代码、运行 PID、设置、公共/当期参考、题面和当期项目材料。差异即停下本期并留证，不重冻覆盖。新代码必须用新版本、新研究目录，旧运行和全部费用保留分报。

N3 对 `374beac2` 的写入需与第一期测量错开；伊利年报全量完成不是第一期前置条件，但一期开始前这些项目必须进入稳定测量窗口。原文完整且已独立核金标的局部 `needs_review` 可作为同等材料缺口，不清洗成“完美数据”再挑好成绩。资料变动检查是程序确定性操作，不新增 LLM 检查回合。

部署收据由 N1 从主线实际 F1 交接转换为以下 JSON，不能把示例值当实测值。`configurationFiles` 指向含两组完整系统指令、工具 schema、项目规则/技能版本等有效配置的私有文件；项目资源同时保存在当期材料快照。环境记录 Node/Python/Pi、容器镜像 digest 与主要计算/图表依赖，未知项明确 null。

```json
{
  "freezeVersion": "F1",
  "loadedCommit": "完整40位实际加载提交",
  "pid": 0,
  "startedAt": "实际进程启动时间",
  "included": {"n4": "提交", "n3": "提交", "isolation": "提交"},
  "environment": {"node": null, "python": null, "pi": null, "imageDigest": null},
  "configurationFiles": ["data/evaluation/主线F1交接/完整配置.json"]
}
```

只读冻结/计划与付费命令明确分开：

```powershell
# plan / check 离线，无请求；研究名正式执行时取新名称。
node benchmark/blind-eval/runner-f1.mjs plan blind-eval-F1-20261008-a benchmark/blind-eval/f1-config.json
node benchmark/blind-eval/runner-f1.mjs check blind-eval-F1-20261008-a
# F1 通知后，读取实际部署收据与当期资料，不调用模型。
node benchmark/blind-eval/runner-f1.mjs freeze blind-eval-F1-20261008-a 收据路径.json
node benchmark/blind-eval/runner-f1.mjs freeze-phase blind-eval-F1-20261008-a 1
# 下列 run 才提交付费回合，只在收到开跑通知后使用。
node benchmark/blind-eval/runner-f1.mjs run blind-eval-F1-20261008-a 1
node benchmark/blind-eval/runner-f1.mjs collect blind-eval-F1-20261008-a
node benchmark/blind-eval/runner-f1.mjs a5 blind-eval-F1-20261008-a
```

研究名为新 ASCII `blind-eval-*` 名称；示例名称本轮未创建正式研究。第二期重复 `freeze-phase ... 2` 和 `run ... 2`，沿用同一研究和 F1。

## 失败规则

- 发送消息前先持久化 `posting`；有 run ID 的只轮询，不重复提交。
- HTTP 响应丢失或其他提交结果不明，保留 `posting` 并停止调度。读取原会话/运行后，用 `reconcile STUDY label runId` 验证项目、会话、原题、profile、预算及隔离键，再关联原运行，零 POST。无法关联则维持未知，不猜测成功或自动重发。
- 已明确 failed/cancelled 的回合原样计入完成率及成本。其延续题在父题未完成或没有交付回答/附件时标为 `blocked_dependency`；其他独立题继续。零请求的依赖阻断单独标注，usage 为 null，不冒充零费用的成功回合。
- 本轮无自动付费重试命令。若协调方后续批准补跑，建立另一个补跑研究，引用失败原记录；不覆盖原成绩，全部尝试费用并入对应题组。错误、未知用量、缺失审计与附件下载失败均保留。
- `completed` 仅是宿主终态，不等于答题通过。附件、数值、来源、复算和独立评审另判；有实质错误 R2 最高 1 分。

## 第一阶段金标与选择器

`reference-development.json` 和原开发集题面/精度不变。`reference-phase1.json` 冻结 X4/X5/X6 的原页事实、必提要点、六维覆盖和解释边界；来源清单含 PDF 与渲染/文本指纹。`selectors-phase1.json` 有 68 项数值参照；源金额/显示比例精度各自定义，不先舍入再算。

由于题面没有强制答卷文件名和列名，开跑前冻结的是金标键、计算值、单位、容差、条件和选择器程序，答卷后只绑定位置，不修改预期值。`selectors-f1.py` 读取 CSV 唯一行或 JSON 明确 path；每条绑定保存文件摘要、单位原注和单位映射。所有仍交付版本均绑定，不挑最正确的一份；无明确单位、未绑定或只在图片/正文出现的数字留为未知交独立评审，不自动记数值通过或实质错误。必要的人工作位置绑定记录不暴露组别。

X5 截止日固定 2024-12-31：华泰 10-30、光大 11-04；五月光大仅修正历史，国信 2025-07-16 排除事前。源页已核华泰/十一月光大归母身份，五月仍未明；收入/总收入、EPS 的口径缺口进入参考。六项差额仅有限可比的参照，不作为无条件预测准确度排名。X6 季度损失原因用同口径全年减 9 个月证据，不将全年损失直接归到 Q4。

## A5、交付及评分

复用 `scripts/collect-pi-analysis.mjs` 保存真实下载状态和全部附件；脚本复算沿用原 `replay.py` 的授权隔离流程。A5 只运行已有 `scripts/scan-delivery-consistency.py` CLI：

```powershell
python -B benchmark/blind-eval/a5-adapter.py data/evaluation/blind-eval-F1-20261008-a/P1_X4-a5.json --study data/evaluation/blind-eval-F1-20261008-a --label P1_X4
python -B benchmark/blind-eval/selectors-f1.py benchmark/blind-eval/selectors-phase1.json 已审位置绑定.json 答卷目录 data/evaluation/blind-eval-F1-20261008-a/P1_X4-numeric.json
```

适配器输入为当前回合已实际查询的来源、宿主审计中的完整 A1 表、最终回答及 manifest 中所有交付 MD/CSV。保留原附件名防止表格自证；失败下载及 PDF/图片等 A5 未覆盖文件明列。A5 原分类、误报和未命中全部保留，不反馈参与者、不触发修改或重试，不另写扫描器。可用 `--input` 接收既有完整 CLI payload，`--mainline-result` 原样导入旧结果。

匿名化按材料块使用 `blind.py --tasks ... --reference-dir ...`，不会把 held-out 混入开发/伊利评审。`make-judge-reference.py` 从冻结参考制作 gold.json，开发集只映射 D1/D2/D3 名称，不改原金标。PDF逐页保留原像素并提取匿名文本；Excel逐格保留数值、公式、存储的计算缓存、合并格、图表XML和嵌入图片，不在宿主执行或重算。PDF可见身份痕迹、Excel嵌图/图表需额外视觉审阅，明确标为待审并阻止直接放行；无法评审的视觉质量不算通过。原文件始终保留供独立复算，不用匿名展开副本冒充产品交付文件。

沿用 rubric v2 与 E4：开发集和 held-out 各自同时满足实质缺陷不更多、R3/R4/R5 各不低且至少一项高、已核实分析成本中位数不高；报告全部尝试总成本和区间。扩展单列，未知用量/费用/未完成/评审不稳定不能宣称优势。两次都报告，不挑最佳。入库、分析、评审分别记账。默认两期答卷均封存后按原四个材料块×换序两遍开 8 个新评审线程，固定 gpt-6-astra/high，避免提前评审反馈污染第二期。

请求规划（非执行截断）：第一期约 256–832 请求、680万–5400万输入、11.2万–55.2万输出；第二期 236–732 请求、720万–4800万输入、9.6万–48万输出。合计仍是 492–1564 请求、1400万–1.02亿输入、20.8万–103.2万输出。目录估价非账单；缓存/未缓存构成和实际费用未知，按运行实记。

## 当前就绪结论

执行器、第一期金标和 A5 离线适配已准备。第一期关键原文及数值可形成正确参照；伊利季报只读快照已显示 9M/Q3 期间，无 FY 错标，但不是全库语义验收。年报仍 normalizing，券商表仍有局部疑点，均留证不改库。只待主线 F1 部署交接、当期稳定数据窗口和明确开跑通知，再现场冻结实际运行与数据；不能把当前 58a903c 或准备快照当 F1。

第二期还有年报入库与 N1 金标冻结；青啤旧断点、旧十次账目和上次续跑账目均未改写。本轮无付费参评、无入库续跑、无服务操作。

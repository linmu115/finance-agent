# 盲评评测台（开发期旁支）

本轮迭代记录，2026-10-07。方向/spec：Claude；执行：N1。

已确认：只写本目录与 `data/evaluation/blind-eval-*`；保留卡罗特三题原文；准备与分析分别记账；两组 prepared/financial 使用 CPA gpt-6-luna 和相同路由、资料；每题每组至少两次。正式付费对照等 Claude 通知，当前只用历史会话演练。3001 由主线程独占启动/停止，N1 不管理服务或其他端口。

已交付：执行器、匿名包、独立评审、数值判分、rubric、题面草稿和来源盘点；完成历史材料两轮盲评演练，结果见 [HANDOFF.md](HANDOFF.md)。产品代码、提示词、工具说明、历史实验不改。历史演练不作为成绩。现有数据的 needs_review 不自动视为已核验。

最新审定及实现：11题×两组×2次，按同一F1分两期；X2本轮“未执行”，X5截止日2024-12-31已批准。当前入口为 [F1_EXECUTION.md](F1_EXECUTION.md) 和 `runner-f1.mjs`，跨项目调度、逐链isolation_key、冻结/失败处理和A5现有CLI已接入，第一期X4/X5/X6金标及68项数值选择器已冻结。参考原PDF18页独立核对，见 `data/evaluation/blind-eval-f1-preparation-20261008/`。正式参评尚未开始，等待主线F1上线、稳定数据窗口和Claude开跑通知。青啤仍暂停，旧账目和断点不改，待通知后从断点恢复；上次结果见 [TSINGTAO_RESUME_20261008.md](TSINGTAO_RESUME_20261008.md)。三份研报历史覆盖与缺陷见 [BROKER_RESUME_20261008.md](BROKER_RESUME_20261008.md)，新代码不等于旧记录全部正确。旧迁移方案已改为N3重新入库。

2026-10-08评测要求对齐见 [REQUIREMENTS_ALIGNMENT_20261008.md](REQUIREMENTS_ALIGNMENT_20261008.md)；新rubric逐一对应五项技术要求及共同要求，9题参考附适用范围和必提点。新增季报/口径草案见 [ANALYST_NEW_TASKS_20261008.md](ANALYST_NEW_TASKS_20261008.md)。旧五维历史结果原样保留，新六维结果单列。

## 文件与操作

- `runner-f1.mjs` / `study-f1.mjs`：正式两期执行入口，44回合36链；实际隔离键按主线交接，每次续题原键原会话，断点保存、失败留账、无自动付费重试。`runner.mjs` 保留为历史单项目执行器。
- `blind.py`：随机匿名编号、逆序复评及重新编号；回答、全附件、ZIP展开内容与实际执行代码匿名化；多版本关系不删除；图片字节不变。私有映射留在round目录之外。
- `metrics.py`：已知/未知用量、全部尝试、时长、请求路由、工具序列和错误；冻结参照与CSV/JSON精度/单位/方向比较；六维统计（未考查为null）、换序稳定性、保守宣称门槛。程序不能判断的金融语义交给独立评审。
- `a5-adapter.py`：调用已有 `scripts/scan-delivery-consistency.py` 离线CLI，当前回合已查询来源/完整A1表/交付清单构造输入，原结果完整保留；不另写扫描器，不反馈参评模型。
- `rubric.md`、`reference-template.json`、`reference-development.json`、`reference-notes.md`：评审契约与参照；原开发题在`tasks-development.json`，逐字保留。
- `review-protocol.md`：全新线程、无历史继承，固定gpt-6-astra/high。评审仍共享文件系统，包外读取受任务指令限制，不声称OS级隔离。
- `DRAFTS.md`：交Claude审定的题目、材料状态、费用估计与未决项。
- `ingest.mjs`：获授权后通过产品标准项目/上传/会话接口执行完整资料准备；失败与续跑保留，用量写入独立preparation台账，不与分析费用混算。只读调研不调用维护/迁移接口。

以下是历史单项目操作记录，不用于本轮正式执行；本轮命令见 F1_EXECUTION.md。

历史准备命令（不发模型请求；当前开发计划已生成，不重复覆盖）：

```powershell
node benchmark/blind-eval/runner.mjs plan blind-eval-COHORT benchmark/blind-eval/development-config.json
node benchmark/blind-eval/runner.mjs freeze blind-eval-COHORT
```

等Claude明确通知版本可冻结且允许正式付费对照后，才执行：

```powershell
node benchmark/blind-eval/runner.mjs run blind-eval-COHORT
# 中断恢复执行同一run命令；已完成的不重做。明确失败可retry，未知POST先确认已有runId。
node benchmark/blind-eval/runner.mjs retry blind-eval-COHORT P1_2
node benchmark/blind-eval/runner.mjs replay blind-eval-COHORT
```

每个新project独立cohort；不把不同准备状态的项目拼作配对。执行器本身不迁移或入库资料。已获明确授权的资料准备由独立ingest.mjs处理。evaluationLimits沿用现有实验预算，所有失败/重试用量保留；不增设工具调用上限。预算耗尽保留进度和实际未完成范围。原始代码只由现有沙箱重放；匿名代码用于阅读，不能执行。

历史匿名演练可复现命令（新目标目录，避免覆盖首轮证据）：

```powershell
python -B benchmark/blind-eval/blind.py data/evaluation/pi-cowork-acceptance-20261006 data/evaluation/blind-eval-REHEARSAL --reference-dir data/evaluation/blind-eval-analyst-alignment-20261008/rehearsal-reference
python -B benchmark/blind-eval/metrics.py stability data/evaluation/blind-eval-REHEARSAL data/evaluation/blind-eval-REHEARSAL/stability.json
```

新题正式匿名包使用该cohort专用 `gold.json`、`reference-notes.md` 和来源页目录，不套用卡罗特参考。先冻结参考数值；CSV/JSON selector仅用于定位可变格式的实际提交单元格，不能根据模型答案改金标。程序判分与A5、人工语义评分互补，不以一个局部numeric pass包装整题通过。

## 本轮验证边界

已做9个有针对性的离线回归：数值/单位/币种/方向/舍入、未知用量和失败保留、禁止缺held-out/费用未知却宣称优势、附件完整与图片字节、高精度小数与中文旁ID匿名化、嵌套原生计算包、仍交付旧版本重放选择、下载失败与评审副本/缺失区分。执行器通过mock transport集成检查：分页完整、两组同题、独立会话与会话内延续、原问题一致、代码/数据/任务/参考/设置冻结不变及防止重复POST；网络请求0、模型请求0。重放计划正确选择18个历史交付版本；上述评测台离线验证阶段未运行Docker、HTTP附件下载或真实3001/付费对照执行器验收。之后另获授权的真实资料入库单列记录，不作为对照验收。

首版演练已发现并修复两项真缺陷：长小数误匹配32位ID、中文邻接文档ID漏匿名化。首版记录保留在`blind-eval-rehearsal-20261007`；修正版在`blind-eval-rehearsal-v2-20261007`。340个高精度数字保留检查无差异；12案124附件18张图保留。Rubric阈值未因首版不稳定而改动。

修正版首评和逆序复评均为全新 `gpt-6-astra / high` 线程：12/12案实质缺陷有无一致，五维平均绝对差0.2333、单项最大差1，满足预设稳定性阈值。历史8项实质问题均在两轮被发现，但C2的JSON单位冲突与F2的差额说明有严重性分歧，详见交接报告；演练不用于比较成绩。

发布排除检查使用 `scripts/build_release.py` 内部与 `--plan` 相同的 `source_plan`，1495文件/312.4MiB清单不含本评测台。CLI强制输出dist，与本会话写入范围冲突，因此函数结果写至`data/evaluation/blind-eval-preparation-20261007/release-plan`；没有写dist或修改打包程序。data/evaluation为开发数据，不进入发布源。

2026-10-08六维历史复评已完成：12/12案实质缺陷有无一致，52个有效评分对平均绝对差0.134615、最大差1，两轮均发现历史8项主要缺陷。仍有严重性分歧和未审辅助文件；见 [RUBRIC_V2_REHEARSAL_20261008.md](RUBRIC_V2_REHEARSAL_20261008.md)，不与旧五维分数混比。

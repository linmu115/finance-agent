# N2 交接

工作区 `D:/AI/财报agent-wt/fin-workpapers`；分支 feat/fin-workpapers，起点 2fd4ddf。未改主目录工作文件，未启停 3001、其他服务端口、Docker 或 WSL；真实模型调用 0。Python 依赖通过主目录 .venv 绝对路径复用，node_modules 通过目录联接复用，未安装或改写依赖。真实资料验收在 SQLite/WAL 副本完成，运行产物在 worktree 的 .tmp/n2-data。

| 阶段 | 提交 | 可合并内容 |
| --- | --- | --- |
| K1 与统一契约 | 1978106614c5034ba3f6072c020e37ca4bc28edb | financial_workpaper 注册/金融专用可见性、statement_analysis、宿主附件、模型紧凑投影、两家公司回放 |
| K3 | d9f7c9ef2638ce2dde670bf7e7d871f03dd1b0c0 | report_audit、CMBI/国信伊利完整副本回放与局部缺项 |
| K2 核心 | 690139e5e879b671ddea30d25daa1b11db2fc180 | comparison_report 纯计算函数，7 项测试，34 个合成数值参照 |
| K4 核心 | 08966242cdba236c535ae08621a6f8cafdc552b3 | expectations_report 纯计算函数，11 项测试，截止日/修正/实际偏差 |

K1 可单独先合并；K3 依赖 K1。K2/K4 使用 K1 的 typed cell/table 帮助函数，不暴露尚未做原文验收的工具 kind。此顺序保留在分支提交中，没有重写已回报提交。

## 主线 A1 合并位置

工具服务返回 `result.data.report`（已解析 report，包含 tables、columns、rows、row_key、evidence），同内容 tables 也在 `result.data.numeric_tables`。宿主 `server/runs.ts` executeTool 已把 delivery.files 登记为下载附件；工具结果交给 `server/model-context.ts` 的 modelContext 前，由主线 A1 直接注册完整 tables，避免从模型紧凑投影反向重建。该投影仅留 summary（表名/列/单位/行键）、前 5 条 observations 和交付清单。

基线没有 A1 注册器，故本分支没有聊天占位符解析实现，也没有验证主线尚未合并的在线下载/UI。主线只需保留新增工具 allowlist、delivery 挂钩和上述先注册后投影顺序；不要让通用 Pi / prepared-data 配置获得 financial_workpaper。

## 已执行验证

- `FINANCE_PYTHON=D:/AI/财报agent/.venv/Scripts/python.exe npm run test:service`：536 项通过，242.297 秒，日志 .tmp/python-final.log。该轮覆盖四个 kind 核心的 41 项专项；专项独立运行也通过。
- `node --import tsx --test tests/financial-workpapers.test.ts tests/model-context.test.ts tests/evaluation-budget.test.ts`：22 项通过。
- 使用主目录 TypeScript CLI 的 server/web `--noEmit` 类型检查通过；server tsc 编译及 Vite build 通过。Vite 只有现存主包超过 500 kB 的提示，不是构建失败。
- node_modules 联接被 npm pretypecheck 视为不支持的本地目录布局，因此先通过主目录只读依赖核验（13 官方文件、3 lock 条目），再用绝对 CLI 路径检查构建；没有修改 prehook 或重装依赖。
- K1 与 K3 使用当前真实副本回放，完整 JSON 和验收说明在本目录。没有重新调用清洗模型，没有把需要修复的原记录写回主库。

## 验收边界

K1 合并/归母/少数股东利润在 profit_attribution 独立表的不同列，income 保留两期对照，这是与 spec 表组织的差异。K3 含大量参数不足或口径不明的局部结果，分别列明原记录/页码，不能把审计流程完成称为全部研报计算通过。

K2/K4 的资料适配、完整材料入库、伊利跨期及美的/海尔原文至少 30 项核对、伊利 2024 真实预期差验收均待后续确认清单。材料与费用见 materials-and-cost-plan.md。N1 尚须执行同模型/同资料的对照；本线不宣称已证明 harness 整体优于通用 Pi。

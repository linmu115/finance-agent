# N2 本轮迭代

授权：2026-10-07 Claude/N2 分工指令。基线 2fd4ddf；仅在 feat/fin-workpapers 工作区改动。主目录未提交 spec 按绝对路径读取，以 AGENTS.md 优先。

确认范围：统一 financial_workpaper 契约、K1 财报底稿先提交；随后 K3 研报审计、K2/K4 计算核心和测试。新材料仅报告来源、缺口和估计费用，等待确认后入库。主线负责合并与 3001；本线不启动服务、Docker、WSL 或真实模型调用。

依赖：Python 使用 D:/AI/财报agent/.venv/Scripts/python.exe；node_modules 目录联接到主目录依赖，仅运行检查/编译，不安装或修改依赖。真实 SQLite 与 WAL 复制到本 worktree .tmp/n2-data 后读取，所有运行产物留在副本或临时目录。

契约：复用 analysis_report 的 typed cells、columns、rows 和宿主渲染；完整 report 供主线 A1 数值绑定，模型只接收紧凑清单与确定性 observations。缺失不补零，语义冲突不猜，已披露来源与派生值保持区分。拒绝重抄计算、因果推断和按样本硬编码答案。

待验：卡罗特与瑞和财报数值及现金桥；CMBI 卡罗特和国信伊利研报；K2/K4 的真实补充资料尚待确认。各阶段结果追加于本文件和 docs/evidence/n2-workpapers/。

K1 已完成确定性实现与两家公司副本回放，数值及边界见 docs/evidence/n2-workpapers/k1-acceptance.md。A1 注册接口在本基线尚不存在，返回完整 data.report/data.numeric_tables 供主线登记，不声称聊天绑定已生效。

K1 后 Python 全套 507 项通过。K3 已加入同一工具，CMBI/国信完整副本结果见 docs/evidence/n2-workpapers/k3-acceptance.md 与 k3-replay.json；部分股数口径和过渡期现金流缺口单列，不把机械差额认定为原研报错误。

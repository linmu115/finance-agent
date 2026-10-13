# original_pi 落地后的离线验收约定

协调者已批准 legacy generic v0.2 契约，主线实现 profile。N1 接交后检查实际请求与执行路径，不调用付费模型，不把 profile 字符串出现当完成。本文件不含 held-out 内容，可以交协调者用于主线交接。

捕获使用现有开发材料或合成文档。建议一次无网络/假 provider 的主会话与续题，经过原文读取、run_analysis、自行生成 CSV/图/Markdown 产物、正常完成、模拟不可转换值和取消；主线保留发给 provider 的最终系统提示、工具 schema、宿主扩展事件与沙箱输入文件清单。续题与压缩/重试的差异也要记录，不能只看创建会话时的 allowlist。

|项|批准契约与检查方法|
|---|---|
|模型/条件|三组相同模型、provider、推理级别、Pi 版本、原生压缩/重试与基础沙箱依赖；可比较的预算。不能回滚整个旧宿主混比。|
|system prompt|original_pi 精确 bare prompt SHA256 `6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f`。逐字核对；不得再追加 shared/answer/finance guidance。analysis_only 的安全性任务路由信息另在实际消息层记录。|
|工具|原 10 个工具，与 baseline-runtime-evidence.json 列表集合相同；读取每个实际 schema/description，尤其 run_analysis 不得残留 report/save_table、绑定、金融模型/底稿帮助。名称相同不代表能力相同。|
|原文/权限|同一 PDF 和同一原文解析/原表/搜索；受控当前项目范围。原文可用而无 facts/research 内容，不能让 G 因读取缺路由而被人为削弱。旧 prompt 所说 facts.json 为空至多是空兼容文件，不得含任何结构化事实。|
|沙箱|记录实际挂载及可导入的应用模块；不提供 analysis_report/report/save_table、model_units 领域辅助、finance_charts、金融模型和技能等本项目资产。标准 Python/Matplotlib、PDF/表格库和字体可用，允许自行实现交付。|
|宿主|A0、A1/P2 绑定及一次修复、事实/推论标注、估值章节校验、输出契约提示、领域预计算不进入 G。以模拟不合规回答仍按原样终结的运行轨迹验证，不仅靠源码分支。|
|成果隔离|每条链的隔离键有效；G/P/F 和不同 repeat 无法读取彼此成果；同组 D2→D3 可继承。只对新成果隔离，原文为同一准备状态。|
|prepared|结构化事实/研报查询和共享基建存在，金融领域资源与 P1.0 预计算不存在。|
|financial|与 P 共享资料和交付基础，金融层/P1.0 按冻结版实际启用；预计算失败原样记录，不伪成功或阻断所有分析。|
|取消/并发|纯调度器已离线验证最多两条异组链、基础设施失败继续、有效性失败停队列、父题不可用时续题不发。实际 adapter 还须用假请求捕获验证：取消同步发生后每个 POST（含续题）均不再发出；已发出的在途请求保留。|

验收证据保留实际原始捕获文件及其摘要、主线 commit/tree、依赖/镜像、捕获脚本参数、每项 observed/pass/fail/unknown；未知不自动通过。没有取得实际请求捕获前，仍标“待主线交接”，不提前宣称 original_pi 可参评。不把本清单追加到参评模型系统提示。

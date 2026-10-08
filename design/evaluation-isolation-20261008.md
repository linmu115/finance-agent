# 评测运行成果隔离（2026-10-08）

用户已授权修复正式盲评前的项目成果串链问题，依据 benchmark/blind-eval/FORMAL_EXECUTION_PLAN_20261008.md 的成果隔离缺口。新增可选 evaluation.isolation_key，只约束带键评测运行的生成物；普通产品会话保留项目共享成果与资产看板行为。文档、原文页表、财务事实、研报记录继续共享。

采用成果归属标记与运行上下文：宿主模型/报告库、Python 的模型引用与分析运行均校验同一键，旧成果没有标记，不进入隔离范围。归属由宿主请求上下文传递，不能由模型的工具参数冒充。会话开始后不能切换、增加或省略原隔离键；同键的新会话或续题可以复用。预算组仍只管预算，可包含多条独立链。

覆盖 list/read、source_model、model_refs、source_run_id、get_analysis_status/get_artifact、底稿交付物与报告包。越界和不存在走相同错误，不提示最新版本或其他链是否存在。共享原文/事实查询不改。

本轮仅隔离数据上的确定性测试，不调用付费模型、不读 held-out、不修改生产事实、不构建替换线上产物、不重启 3001。等待 N4/N3 后续合并后再统一上线为 F1；本次提交不能标为 F1 已部署。下方补录验收和 N1 请求示例。


## 实施和结果

已用 AsyncLocalStorage / MCP metadata / Python ContextVar 传递宿主校验后的键，模型/报告 revision、分析状态、底稿交付清单和报告包快照记录归属。列表先按归属过滤再选最新版本；跨界 id、revision、source_model、model_refs、源运行等不泄露存在或内容。参数中间运行和清洗脚本的分析线程复制当前上下文，状态更新保留初始归属。

模型交付缓存的标识在带键时纳入隔离键，防止普通产品先生成的同模型交付包被错误复用到评测链；无键缓存标识不变。普通产品、资产看板、原 HTTP 下载行为保持，评测工具使用受限运行上下文。这不是用户账户级 ACL 或主机文件系统隔离。

会话消息请求绑定键并持久化；已有会话不能换键或无键化。预算组与链键分离，不新增预算冲突。两组 schema/说明快照完全不变，未添加模型规则。financial 40 工具 / 30,551 字符，prepared 13 工具 / 9,295 字符。

Python 唯一 53 项、Node 唯一 23 项最终通过，类型检查通过。原生 Pi＋MCP 假模型会话真实执行模型保存、同键 source_model 续题及所有宿主权限分支；Python 隔离 fixture 验证分析执行、params 子运行、get_artifact 和非空共享输入。首轮宿主夹具误用跨 profile 预算组的失败保留，修正后通过。没有付费模型调用、Docker 执行或 HTTP 测试监听，没有构建替换线上产物、生产事实写入或重启。

详细请求示例与验收矩阵见 docs/evidence/evaluation-isolation-20261008/handoff.md。N1 为每个批次/独立题链/profile/重复次序生成全新键，D2→D3、H1→H2 保持各自同键。3001 仍为 58a903c / PID 56120；F1 等后续 N4/N3 合并后统一构建、重启。提交后在 data/evaluation/evaluation-isolation-20261008/manifest.json 写入本次精确 commit，当前部署冻结交接不提前改为新版本。

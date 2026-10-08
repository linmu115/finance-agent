# N4 采用修复合并交接（等待 F1 上线）

基线 `e2c1f46`，精确合并 `f945e76`（包含 `47bf960`、`f21b419`，分支基于 `58a903c`）。正式合并 commit 写入 `data/evaluation/adoption-merge-20261008/manifest.json`。N4 的原验收和失败记录完整保留在相邻 `n4-adoption-fixes-20261008/`，没有把逐题补测拼为统一版本的正式成绩。

## 功能与冲突处理

底稿 kind 共用期间归一、缺省可比期、关键值与绑定交接；底稿和模型交付 ID 可供读取/状态查询和下载；取数使用项目内已登记主体别名；指导按题意选 kind，未绑定且无来源的陈述默认呈现为推论/分析。所有这些入口保留来源口径与缺项，不新增确认流程。

`service/core.py`、`service/report_package.py`、`server/research-artifacts.ts` 三处文本冲突采用统一 ID 解析方案。交付清单在 `service/delivery_files.py` 中先过滤隔离归属；未找到可见交付时，带键调用继续通过 `_analysis_state` 检查分析运行。宿主下载经 MCP 继承可信上下文，报告图片也经 `artifact_path` 解析。

因此，用交付 ID 不能绕过 `evaluation.isolation_key`：跨键、旧无键交付和不存在的 ID 返回相同的 `analysis_not_found_in_project`，包括不存在的文件名，不泄露可用文件清单。同键可读；普通无键调用仍共享项目内成果。文档、事实及研报记录共享范围不变。N1 继续沿用 [隔离键接口交接](../evaluation-isolation-20261008/handoff.md) 的请求方式；在当前未升级的 3001 上暂不使用该新字段。

## 验收

- Python 145 项通过：全部底稿期间/财务方向、别名、关键值绑定、交付读取、分析更新、报告包、隔离及相关数值渲染。
- Node 22 项通过：回答语义、A1 表登记、工具可见性、DCF 宿主交付、成果依赖及真实 Pi＋MCP stdio 的隔离链（使用进程内假模型，无付费推理）。
- `npm run typecheck` 通过。没有新开 HTTP 端口，没有 Docker 执行，没有生产事实写入。
- 首次 Python 16 项中 1 项失败：新增夹具取到合法空 JSON 对象，真值断言不适用；改为检验实际文件大小后，完整 145 项通过。`python-isolation.txt` 原日志保留。
- N4 的绑定率改善属于已交付研发观察。本轮只验收合并与确定性路径，不追加真实对照，也不宣称整体金融优势。

## 模型可见上下文

| 配置 | 工具数 | 合并前字符 | 合并后字符 | 字符增量 | 合并前粗估 token | 合并后粗估 token |
|---|---:|---:|---:|---:|---:|---:|
| financial | 40 | 30,551 | 30,809 | +258 | 10,002 | 10,101 |
| prepared | 13 | 9,295 | 9,521 | +226 | 2,923 | 3,011 |

口径沿用 B4：完整原生 Pi system 加紧凑 JSON 工具定义（含 description 与完整 schema），按 Unicode 字符计数；token 为 `ceil(ASCII/4 + 非 ASCII)` 粗估，不是 tokenizer 或账单。排除历史消息、动态工具结果、请求封装。工具顺序和去 description 后的 schema 结构完全相同；prepared 可见整表/单值绑定、params、edits、get_artifact，仍不暴露 financial_workpaper。分项字符与归一化说明哈希见 `context-measurements.json`，脚本 `measure_context.py` 可只读复算。

## 环境与下一步

**尚未部署，不是 F1。** 3001 仍为 `58a903c` / PID `56120` / 2026-10-08 12:43:53.7679380 +08:00；本轮没有构建覆盖线上输出或重启。等待 N3“按表搁置继续推进”修复合并后，在无活动任务时统一构建、重启并重新冻结。后续注意保留 MCP scoped_thread、analysis 线程 copy_context、状态归属和本次 delivery_manifest/artifact_path 隔离路径。

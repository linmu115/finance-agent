# v0.4.1 便携包最终验收

2026-10-12，本地 main 已从 `2e37a22` 快进到 `b275825`，包含 `0ae9c9e` 的报告包导出修复和 `b275825` 的中文加粗修复。版本及发布脚本提交为 `9e50a8c`；最终归档来源是 `ec48a62d6e55055658e0e2747978980bea3f176a`。后续提交只补验收记录，不改归档内容。未 push，未创建 GitHub Release。

## 交付物

- ZIP：`dist/release-0.4.1/finance-agent-0.4.1-windows-x64.zip`
- 大小：305,115,505 字节（290.98 MiB）。
- SHA-256：`68bad2b274bea5152057f013977db2f41868393571cc7fd041808771b42518d5`
- 校验文件：`dist/release-0.4.1/SHA256SUMS.txt`。
- 50,601 个清单文件，另含清单本身；归档 CRC、逐文件 SHA-256，以及两次全新解压核验均通过。
- ZIP 内发布说明保留归档前候选的实际验收数据；源码与 ZIP 同目录的发布说明另补最终归档验收。二者分别标明验收对象，不回写已验证的 ZIP。

## 最终 ZIP 的结果

| 项目 | 结果 | 证据 |
|---|---|---|
| HTTP 安装、启停、端口隔离、解析、持久化、实际导出 | 22/22 | `http-verification.json` |
| 离线、自带运行时、MCP 解析重连、包内回归、必备文件 | 15/15 | `offline-verification.json` |
| 原合成回归 | 57/57，74.498 秒 | `regression-final.txt` |
| 新增报告包回归 | 6/6，3.438 秒 | `report-tests-final.txt` |
| 中文加粗、TeX、附件链接、宿主单飞 | 12/12，无跳过 | `node-tests-final.txt` |
| typecheck / build | 均通过，保留既有 Vite 大包提示 | `typecheck.log`、`build.log`（本地构建日志） |
| 密钥模式、封存公司名、本机用户名/路径、禁止路径扫描 | 未解决命中 0，禁止路径 0 | `sensitive-scan.json`、`reviewed-scan-matches.json` |

HTTP 与离线验收各从最终 ZIP 全新解压到中文/空格路径，移除开发 Node/Python 的 PATH，使用包内运行时和依赖。原始运行记录分别位于 `dist/deployment-check-20261012T024727Z/` 与 `dist/offline-deployment-20261012T025114821706Z/`。

实际报告使用全新合成会话：一张表包含 21,171 字符的定位列表。两个并发 HTTP POST 都返回 200，耗时分别 8.157 秒、8.141 秒，响应字节一致，产物目录只有一个报告包。PDF 为 1 页；Markdown/PDF 使用可读定位，Excel 与 snapshot 原始文本完整保留。报告 ZIP 位于 `dist/deployment-check-20261012T024727Z/synthetic-report-package.zip`。未使用真实会话、评测数据或封存材料。

扫描覆盖 ZIP 的 50,602 个文件以及 454 个嵌套成员/提取 PDF 文本。16 项精确文件哈希复核命中为上游 SDK 示例、PEM 常量或数值误报；另列 3 处数字子串。扫描按已知模式与指定词工作，不将其视为对任意秘密的完备证明。

## 保留的首次失败

候选包首次离线回归为 56/57：`test_financial_acronym_matches_stored_metric_without_new_ingestion` 期望 2 条，实际 3 条。完整原始结果保存在 `offline-first-failure.json`、`regression-first-failure.txt`。

查询当前匹配整段记录 JSON，随机标识含 `fcff` 时可能命中额外记录。`diagnose-acronym.py` 在 0.4.0 和 0.4.1 的独立包内，用纯合成 UUID 均复现额外命中；相关业务代码与测试文件哈希相同，见 `acronym-diagnosis.json`。首次失败的临时 ID 已被测试清理，没有声称恢复该次原始 ID。未改断言、未跳过测试、未修第三处业务行为；候选原样复跑和最终 ZIP 的 57 项完整回归均通过。这个既有查询问题留待后续处理。

## 环境与范围

- 隔离 HTTP 端口为 3011/3012，数据在各自解压目录内，结束均关闭。3001 始终为 PID 9592，未重启，未操作仓库 `data/active`；见 `ports-after.json`。
- 0.4.0 ZIP 保留，前后 SHA-256 均为 `e073bce92bdbdc0e6c5c86f3fcffc87503068901b62fa2e2f621570f64868582`，见 `v040-before.json`、`v040-after.json`。
- 必需验收无跳过；可选浏览器冷启动、真实模型调用与 Docker 执行未运行，不计为已验证。没有启动 Docker/WSL。
- 发布文件遵循允许列表；源码包不包含真实数据库、会话、密钥、私有评测目录或封存公司材料。使用的旧版公开 PDF 安装小样与 0.4.0 相同。

机器可读总览：`validation.json`。

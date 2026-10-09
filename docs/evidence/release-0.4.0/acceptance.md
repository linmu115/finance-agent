# v0.4.0 本地发布验收

已完成 Windows x64 可运行包与两张真实界面截图，未 push、未发布 GitHub Release。

- 发布源码提交：`5fb5e101c146df457b768a2447c19b8bb66785a8`。业务实现保持 F2.1（`7e702ff`），相对打包前 main 的 server/service/web/sandbox 差异仅为一处过时测试断言的修正；业务代码未改。
- 包：`dist/release-0.4.0/finance-agent-0.4.0-windows-x64.zip`，304,833,341 字节（290.71 MiB）。
- SHA-256：`e073bce92bdbdc0e6c5c86f3fcffc87503068901b62fa2e2f621570f64868582`。
- `npm run build` 通过；ZIP CRC 与 50,595 个文件的 SHA-256 一致。
- 按顺序运行 `verify_release.py` 与 `verify_release_offline.py`：19/19、13/13 项通过；内置运行时的 57 项合成回归全部通过。
- 密钥模式、封存公司名、本机用户名与项目绝对路径扫描：0 项未解决命中、0 个禁止路径。16 条精确文件哈希复核项是依赖示例、PEM 解析常量和数值误报；另有 3 处数字子串，不是身份或路径。嵌套压缩成员与 PDF 文本共检查 454 项。证据见 `sensitive-scan.json`、`reviewed-scan-matches.json`。
- 不含真实数据库、会话、评测私有目录及封存测试材料。只保留一个公开解析小样及四份合成测试；Docker 镜像和使用者模型账号另行配置。
- 真实模型调用 0 次，未启动 Docker/WSL。HTTP 验收使用独立解压目录、临时 3011/3012；验收实例已关闭。原 3001 未重启，PID 36552，`service=connected`。原进程仍报告其启动时的 0.3.0 元数据，本次 0.4.0 是交付包版本。

## 截图

两张 PNG 都是 1920 × 1080，来自伊利开发项目 `374beac2-a970-4972-b210-e91018bbd6e6`（资产看板验收 · 财报、研报与金融建模）。

- `submission/plan/assets/screenshot-asset-dashboard.png`：2023/2024 合并经营现金流，右侧展示年报第 94 页与原文入口。
- `submission/plan/assets/screenshot-analysis-result.png`：F2.1 门槛 F1_X3，现金桥汇总、贡献图与年报第 217 页。同一会话 `b1185731-0cfa-4b07-bc6f-1484d7a4e1cf`，运行 `ee50bebe-5eee-43ea-b1c8-d657fe4f7538`。两遍评审的 material_defects 均为空，minor 记录保留。
- 未改写页面、图表或回答。折叠导航后截图，无封存公司、密钥、用户名或文件系统路径；仅把浏览器捕获的 JPEG 转为 PNG。计划书正文及 PDF 未改。

## 初次验收发现与处理

第一候选 HTTP 通过，但离线脚本需要未打包的合成测试，且仍要求旧的按版本命名论文路径。允许列表补齐四份合成测试，改为检查发布说明和第三方声明。回归中发现一条旧断言要求 P0.4 自动改写指标 ID，与 F2.0 已批准停用规则相冲突；只把断言改为保留提交 ID。未跳过失败测试。最终包重新从全新副本完成全部验证。初次候选与日志保留在 `dist/release-0.4.0-attempt1/` 及对应验收目录，不作为交付包。

## 核验记录

- `validation.json`：最终包、源码提交与验收摘要。
- `http-verification.json`：19 项安装/启停、端口隔离、解析和持久化验收。
- `offline-verification.json`：离线 MCP、内置运行时、合成回归与必备文件验收。
- `screenshots.json`：项目、会话、来源页、评审路径及图片哈希。
- 发行说明：`docs/RELEASE-0.4.0.md`；复现命令与范围见 `design/release-0.4.0-20261009.md`。

验收未调用真实模型、未执行 Docker 分析，也不宣称重新完成正式评测。正式评测结论直接沿用技术报告第 7.6 节。

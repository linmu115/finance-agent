# F2.0.2：original_pi 仅保留基础字体

基线：F2.0 `ca81187c043eea52249cfe52a69ce5534aaa153b`。分支：`fix/original-pi-plot`。
本次仅开发并提交，未合并 main、未部署、未暂停入库、未重启 3001。

原因：original_pi 的启动脚本调用了含 A3 修复的 `plot_runtime.setup()`。改为调用拆出的 `setup_fonts()`，只设置中文字体候选和负号字体兼容；不设置自动布局、裁边或边距，不包装 `Figure.savefig` / `tight_layout`。prepared 和 financial 仍调用原 `setup()`，A3 修复函数及其调用顺序未改。原工具、提示、挂载文件清单和文件下载路径未改。

| 实际渲染观察 | original_pi | prepared | financial |
|---|---|---|---|
| 中文字体候选 | Microsoft YaHei、SimHei | 同左 | 同左 |
| savefig / tight_layout 自动修复补丁 | 无 | 有 | 有 |
| constrained layout | 关闭 | 开启 | 开启 |
| 深色格中的黑色文字 | 保持黑色 | 改为白色 | 改为白色 |
| 越过底轴的负柱标签 | 保持原位置 | 调整位置 | 调整位置 |
| 自动 plot_diagnostics.json | 无 | 有 | 有 |

证据和边界：

- `native-request-capture.json`：真实 RunManager / Pi 原生循环与 stdio MCP 的三组请求捕获；模型由本地固定响应替代，沙箱结果模拟。记录完整系统提示、工具 schema、宿主调用、压缩和重试设置。工具仍为 10 / 13 / 32；original_pi 配置提示 SHA256 为 `6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f`。
- `sandbox-capture.json`：真实 FinanceService 导出路径捕获的 launcher、挂载文件摘要和结果字段，Runner 为本地模拟。original_pi 启动入口确为 `setup_fonts()`。
- `plot-startup-capture.json`：执行上述真实捕获的启动前缀，每组使用新 Python 进程和 Matplotlib Agg 实际绘制合成图。仅 financial 的模型产物复制被 mock；没有使用 Docker。记录修复前后标签、rcParams、诊断结果。原版的非字体 rcParams 保持 Matplotlib 默认值。
- `validation.json`：测试结果及三组提示与工具摘要。使用合成材料，未读取评测题或 held-out 文档，付费调用为 0。

与已有 F2.0 原生捕获比较，三组工具摘要相同；original_pi 和 prepared 的配置提示摘要也相同。financial 仅“资源版本”行不同：资源摘要包含技能的绝对文件路径（`server/project-resources.ts:23–24`），本次为独立 worktree。去掉该环境版本行后指导全文完全一致；证据保留原始摘要，不将其声称为逐字相同。

验收：16 项 Python 测试和 2 项原生请求测试全部通过，无跳过。Python 绘图环境为现有 `D:/anaconda/python.exe`（Matplotlib 3.10.0）；主服务 venv 未安装 Matplotlib，不将该环境的跳过当作通过。无 TypeScript 产品改动，本轮未运行构建或部署。

N1 在本分支目录可复现（不启动服务）：

```powershell
$env:ORIGINAL_PI_EVIDENCE_DIR = "$PWD/docs/evidence/f202-original-pi-plot-20261009"
& D:/anaconda/python.exe -m unittest service.tests.test_original_pi service.tests.test_plot_runtime
$env:FINANCE_PYTHON = 'D:/AI/财报agent/.venv/Scripts/python.exe'
node --import tsx --test tests/original-pi.test.ts
```

部署时间继续由协调方决定。本轮没有改变 F2.0 线上状态；本分支合并部署后，N1 应使用新的 launcher 摘要确认 F2.0.2。

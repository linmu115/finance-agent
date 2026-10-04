科学计算容器（当前机器已部署）

在项目根目录 D:\codex\金融 打开 PowerShell：

  python sandbox/portable_vm.py start
  python sandbox/portable_vm.py status
  python scripts/check_container_env.py

start 会保留已经运行的虚拟机，不重复启动。status 会核验 QEMU 进程路径。第三步在与 MCP 相同的过滤环境下，实际执行 Docker 容器并输出 PASS/FAIL。主应用启动命令以项目主说明为准；create_runner 会自动使用 sandbox/runtime/remote.json 指定的本机虚拟机。

关机前可执行：

  python sandbox/portable_vm.py stop

这会关闭本项目的 Linux 虚拟机。请先结束或取消分析任务。不要在分析或镜像构建期间终止 QEMU。

现有配置：QEMU 10.2.0，现有 WHPX 加速，2 vCPU / 4 GiB VM；Docker 28.3.3；科学计算镜像 finance-analysis:0.1。容器逐任务限制 2 CPU / 2 GiB、64 PID、最长 120 秒；非 root、无网络、输入只读、临时目录受限，输出需通过宿主校验。

镜像 ID：sha256:0b8d45a06afce77036b5b7be2763e9ce73649ad5f9ac099f78d03ca4269006f8

迁移到新机器需按 sandbox/README.md 的 prepare / start / connect / download_wheels / sync / build 流程重新准备。不要向他人分发 sandbox/runtime：里面含本机 SSH 私钥、初始化介质和可变 VM 磁盘。WHPX 必须是机器已有能力；本程序不会自动开启系统特性或要求重启，缺少硬件加速时 TCG 明显较慢。

重要边界：
- 50 MiB 是输出导出的接受上限；宿主轮询可在短时间超量写入后终止任务，并非磁盘配额。
- 项目隔离由单用户本地服务的 project_id 检查实现，不能直接当多租户公网服务部署。
- SSH 与 Docker 控制权只在可信服务/VM 宿主；分析代码没有这些权限，也不接收 API 密钥。
- 容器证据见 sandbox/evidence/runtime.json、recovery.json；主应用真实模型图表证据见 agent-chart.json。各证据的 PASS 只覆盖其列出的验收项，不代替全系统 benchmark。

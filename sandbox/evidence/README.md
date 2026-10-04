# 容器验收证据

本报告对应真实 Docker 容器执行，不以宿主 Python 子进程替代容器。最终证据见 [runtime.json](runtime.json)、[recovery.json](recovery.json) 与 [environment.json](environment.json)。最初启动时发现的日志驱动配置错误和 S04 探针权限异常已修复，原始失败记录保留，最终结果来自重新执行。

| 编号 | 实际执行内容 | 结果 |
|---|---|---|
| S01 | 导入全部 8 个科学计算库；核验中文字体字形；生成并目检 PNG | PASS |
| S02 | 修改 /input 副本被内核拒绝；输入 SHA256 不变 | PASS |
| S03 | DNS、外部 TCP、宿主/本地应用服务连接均失败；network=none | PASS |
| S04 | 假密钥未泄漏；UID 10001；无宿主目录、Docker socket、答案目录；挂载白名单 | PASS |
| S05 | 无限循环在 120.221 秒被终止；另一运行取消耗时 0.559 秒；无残留容器 | PASS |
| S06 | 宿主 inspect 核实 2 CPU / 2 GiB / 无额外 swap / 64 PID；实际触发 OOM 与 PID 限额 | PASS |
| S07 | 超过 50 MiB 输出被拒绝；符号链接拒绝；越界写入失败 | PASS |
| S08（容器部分） | A 项目真实产物被 B 项目 status / artifact / cancel 请求访问，全部拒绝并留审计 | PASS |
| S10 | 三家公司 2023/2024 收入图和 chart_data；六个值与独立 gold 一致；四张图目检通过 | PASS |
| S11（容器部分） | 真实 SIGKILL 可信 Linux runner 进程，重新连接后回收孤儿容器、标为 failed、不导出 partial.txt | PASS |

三公司输入由 service 的真实财报解析结果导出，保留 source_ref，随后只规范化公司简称与产物名称；没有从 evaluator/reference.sqlite 生成任务输入。标准答案仅由 Windows 上的验收代码读取。

实际镜像 ID：sha256:0b8d45a06afce77036b5b7be2763e9ce73649ad5f9ac099f78d03ca4269006f8；镜像大小 713658978 字节。基础环境为项目目录内 QEMU 10.2.0、现有 WHPX 硬件加速、Alpine 3.22、Linux 6.12.81、Docker 28.3.3。没有开启 Windows 特性、安装全局服务或重启宿主系统。

[charts/](charts/) 保存三个真实公司图、字体探针图、原始 chart_data、依赖版本和 SHA256 manifest。Linux 宿主边界测试 11/11 通过，输出见 [host-tests-linux.txt](host-tests-linux.txt)。

本报告仅证明上述容器范围；全系统 S08/S09/S11/S12 仍以应用级报告为准。输出总量采用可信宿主监测和停止后拒绝机制，50 MiB 为导出接受上限，轮询间隔内可能出现短暂超量写入，并非底层磁盘配额。


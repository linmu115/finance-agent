# Linux 部署包：先在 WSL 测试，再上云试用（2026-10-13）

状态：草案，等用户确认后派给 Codex。负责线程建议为 main（它负责 3001 端口和 Docker 生命周期）。

## 1. 目标

把现在只能在 Windows 上跑的便携版，做成在 Linux 上用 `docker compose up` 一条命令就能起来的服务。功能和计算结果要与 Windows 版一致。

这个部署包服务三件事：

1. **决赛交付**：决赛要求提交“可运行原型、源码及运行说明”，运行说明要覆盖任务编排、工具调用、提示指令、数据处理、日志记录五个模块。评委拿到后应能照着说明在一台 Linux 机器上跑起来。
2. **本机测试**：先在用户电脑的 WSL2（Ubuntu + Docker Desktop）上跑通。
3. **云上试用**：以后部署到用户的阿里云服务器，供远程演示（见第 7 节，本期只做准备，不实施）。

## 2. 不做的事

- 多租户、计费、Kubernetes。
- 从 SQLite 迁到 Postgres。单机单租户继续用 SQLite，等试点之后再议。
- 对公网开放。本期服务只绑定 `127.0.0.1`。
- 更换模型。继续用 luna，经用户本机的 cli-proxy-api 转发。
- 修改比赛冻结版本。所有改动在新分支上做；合并进 main 前须经 Claude 确认；`submission/` 和 `dist/release-0.4.1/` 不动。

## 3. 现状（据 2026-10-13 的代码）

- **服务入口**：`tsx server/main.ts`。监听地址和端口来自 `FINANCE_HOST` / `FINANCE_PORT`（Windows 上为 `127.0.0.1:3001`），数据目录来自 `FINANCE_DATA_DIR`（默认 `data/active`，内含 `finance.sqlite`、`documents/`、`artifacts/`、`analysis/` 等）。
- **Python 服务**：由 Node 通过 MCP 的 stdio 方式启动，解释器取 `FINANCE_PYTHON`；非 Windows 平台默认用 `.venv/bin/python`。版本要求 3.12，依赖见 `requirements.lock.txt`，启动自检会导入 `sqlite3, fitz, pandas, openpyxl, rapidocr_onnxruntime, onnxruntime, mcp, langextract`。
- **沙箱**：`sandbox.create_runner()` 的选择规则是：有 `sandbox/runtime/remote.json` 就走 QEMU 虚拟机，否则用本机 Docker 的 `SandboxRunner`。镜像 `finance-analysis:0.1` 由 `sandbox/Dockerfile` 构建，基础镜像按摘要固定，wheel 按哈希固定。单任务限制为 2 CPU、2 GiB 内存、64 个进程、120 秒，非 root、断网、输入只读。
- **模型**：`FINANCE_LLM_BASE_URL`、`FINANCE_LLM_API_KEY`、`FINANCE_LLM_MODEL`，或数据目录下 `settings.json` 里的配置。cli-proxy-api 在用户 Windows 上只监听 `127.0.0.1:8317/8318`。
- **凭据加密**：Windows 用 DPAPI；其他平台用数据目录下的 `secret.key` 做 AES-GCM（`server/config.ts` 已实现）。
- **启动守卫**：`server/startup-guard.ts` 已支持 Linux。
- **只在 Windows 上走的分支**：
  - `scripts/manage.ps1` 和所有 `.cmd` 脚本；
  - `research.ts` 在证书错误时退回调用 `System32\curl.exe`（Linux 上不会触发，但要确认 Linux 下的证书链正常）；
  - `config.ts` 的 DPAPI。
- **用户 WSL 现状**：
  - 已装 Ubuntu 和 docker-desktop 两个发行版；
  - `.wslconfig` 里网络模式是 `networkingMode=nat`，资源是 `memory=4GB`、`processors=2`；
  - NAT 模式下，WSL 里的 `localhost` 访问不到 Windows 上只监听 `127.0.0.1` 的服务。

## 4. 方案

### 4.1 镜像

`finance-app`：一个镜像同时放 Node 24 和 Python 3.12。

- **基础镜像**：选 `python:3.12-slim-bookworm`，再安装官方的 Node 24 二进制包。两个基础镜像都按摘要固定。
- **Node 依赖**：`npm ci`，然后执行 `npm run build`，产物是 `web/dist` 和编译后的 server。保留 `scripts/fix_dependency.mjs --check` 自检。
- **Python 依赖**：放进 `/opt/venv`，按 `requirements.lock.txt` 安装，`FINANCE_PYTHON=/opt/venv/bin/python`。
- **中文字体**：必须装 Noto Sans CJK 或同类字体，否则导出的 PDF 报告和图表里的中文会是方块。验收时要实际导出一份含中文的 PDF 来检查。
- **运行身份**：以非 root 用户运行，工作目录 `/app`。
- **不能进镜像的东西**：`data/`、`samples/` 里的封存包、`.env`、任何密钥。在 `.dockerignore` 里列明。

`finance-analysis:0.1`：沙箱镜像，沿用现有的 `sandbox/Dockerfile` 和 `download_wheels.py` 流程，构建方式不变。

### 4.2 沙箱：应用容器怎么启动沙箱容器

v1 采用“把宿主 Docker 的 socket 挂进应用容器”的方式。

- **信任边界不变**：现在的设计里，Docker 控制权本来就只在可信的服务进程手里，分析代码没有。挂 socket 等于让应用容器扮演这个可信宿主。
- **风险**：应用容器一旦被攻破，就等于拿到宿主 Docker 的权限。这在本机测试和单租户试用阶段可以接受，但必须写进运行说明。上云前（第 7 节）要重新评估，可选的加固有 rootless Docker，以及沙箱容器改用 gVisor（`runsc`）运行时。

**必须处理的路径问题（Docker-out-of-Docker）。** 沙箱用绑定挂载传入 `/input` 和取回 `/output`，Docker 守护进程按**宿主**路径解析挂载源，所以：

- 数据目录在宿主和应用容器里必须是**同一个绝对路径**，例如两边都是 `/srv/finance/data`；
- 沙箱临时目录（runner 的 `state_root`）也必须落在这个同路径的目录下；
- 验收时要专门测这一条：在应用容器里触发一次沙箱运行，确认输入文件进得去、产物取得回。

`create_runner` 不需要改。容器里没有 `remote.json`，自然会走本机 Docker。确认镜像 ID 解析和清理逻辑在 Linux 下正常即可。

### 4.3 模型连接

- **WSL 阶段**：Docker Desktop 的容器可以通过 `host.docker.internal` 访问 Windows 宿主，所以在 `.env` 里设 `FINANCE_LLM_BASE_URL=http://host.docker.internal:8317/v1`（具体路径以 cli-proxy-api 实际暴露的为准）。验收第一步就要从应用容器里 `curl` 一次模型列表或一次最小补全，确认连得通。
- **如果连不通**，按顺序排查：
  1. Docker Desktop 设置里，Ubuntu 这个发行版的 WSL 集成有没有打开；
  2. Windows 防火墙；
  3. 最后的选项是把 WSL 改成 `networkingMode=mirrored`。这一步改的是系统配置，**由用户自己操作**，Codex 不得修改 `.wslconfig`。
- **API 密钥**：只写在 `.env` 里，不进镜像也不进仓库。仓库里提供 `.env.example`。

### 4.4 compose 结构

```yaml
services:
  app:
    image: finance-app:<version>
    env_file: .env                  # FINANCE_LLM_*，不入库
    environment:
      FINANCE_HOST: 0.0.0.0         # 容器内监听全部地址，对外只映射到宿主回环
      FINANCE_PORT: "3001"
      FINANCE_DATA_DIR: /srv/finance/data
      FINANCE_PYTHON: /opt/venv/bin/python
    ports: ["127.0.0.1:3001:3001"]
    volumes:
      - /srv/finance/data:/srv/finance/data          # 宿主与容器同路径，见 4.2
      - /var/run/docker.sock:/var/run/docker.sock
    extra_hosts: ["host.docker.internal:host-gateway"]
    healthcheck: { test: <请求 /api/health>, interval: 30s }
    restart: unless-stopped
```

- 沙箱镜像不放进 compose 常驻运行，只在安装时构建一次，由应用按需启动。
- 日志写到数据目录下的 `logs/`，同时输出到 stdout。审计日志（`server/audit-log.ts`）的位置不变。

### 4.5 安装与运行说明

新增 `deploy/linux/` 目录：

- `Dockerfile`、`docker-compose.yml`、`.env.example`、`.dockerignore`；
- `install.sh`：
  - 检查 Docker 和 compose 的版本；
  - 创建数据目录并设好权限；
  - 构建两个镜像，沙箱镜像沿用离线 wheel 流程；
  - 检查模型连通性；
- `README.md`：运行说明。这一份就是决赛要交的运行说明的底稿，必须写清：
  - 五个模块分别在哪：任务编排是 `server/runs.ts` 和 Pi 主循环；工具调用是 MCP 和 `service/server.py`；提示指令是 `server/financial-guidance.ts` 等；数据处理是 `service/` 下的入库和底稿；日志记录是审计日志和运行记录；
  - 怎么导入样例数据；
  - 怎么跑一次完整分析；
  - 第三方组件和许可证（引用现有的 `THIRD_PARTY_NOTICES.md`）。

### 4.6 测试数据

- **开发数据**：从 `data/active` 复制伊利项目（374beac2）和 Carote 开发项目到 WSL 的数据目录，用来对照 Windows 版的结果。复制脚本只能按项目 ID 白名单导出，不能整目录复制。
- **禁止带入**：封存项目和封存材料，包括青岛啤酒（8513b99f）、白云机场（4feb8474），以及 `samples/` 下所有 `holdout` 包。复制脚本要显式拒绝这些项目 ID，并在日志里写明拒绝了哪些。
- **评委样例**：现场样例数据另做一份精简包，只放公开年报和对应项目，单独评审。

## 5. 用户需要自己做的事（Codex 不得代劳）

1. **（建议）调大 WSL 资源。** 在 `%USERPROFILE%\.wslconfig` 里把 `memory` 改到 8GB，`processors` 改到 4，然后执行 `wsl --shutdown` 重启。现在是 2 核 4G，而沙箱单任务就要 2 CPU、2 GiB，再加上入库进程，会很紧。
2. **确认 Docker Desktop 的 WSL 集成**已对 Ubuntu 打开。
3. **启动 cli-proxy-api**，测试时保持运行。

## 6. 验收

在用户 WSL 上逐条通过，并把结果记录到 `deploy/linux/ACCEPTANCE-<日期>.md`：

1. **一键起停**：全新目录里执行 `install.sh`，再 `docker compose up -d`，健康检查通过；浏览器打开 `http://127.0.0.1:3001` 能用。
2. **原有测试**：在容器里跑 `npm test`、`npm run typecheck`、Python 的 `service/tests` 和 `sandbox.test_launcher`，全部通过；失败项逐条列出，不能跳过。
3. **沙箱**：`scripts/check_container.py` 通过；从界面触发一次带画图的分析，产物能取回。这一条同时验证 4.2 的同路径挂载。
4. **端到端对照**：用复制过来的伊利项目，问视频里那个现金流问题。要求：
   - 回答、现金桥图、底稿 Excel、PDF 报告都能生成；
   - 关键数值与 Windows 版逐一一致，至少核对经营现金流 2023、2024 和现金桥各分项；
   - PDF 里的中文显示正常。
5. **入库**：在容器里新入库一份公开年报，抽查 20 个事实的页码和数值。用 `samples/native-pdf/伊利股份2023年年度报告.pdf`，这是开发材料。不要用美的 2024：它是扩展候选，可能留作决赛前的新公司复测，开发线程不应提前接触。
6. **持久化**：`docker compose down` 再 `up`，项目、对话、产物都还在。
7. **安全**：
   - 端口只映射到 `127.0.0.1`；
   - 镜像历史里查不到 `.env` 内容和密钥（用 `docker history` 加 `grep` 自查）；
   - 封存项目确认不在数据目录里；
   - 运行说明里写明 4.2 的 socket 风险。

## 7. 下一步：阿里云试用（只设计，不实施）

前提：用户提供服务器的配置和地域（执行 `nproc; free -h; df -h /; cat /etc/os-release`）。我估计最低需要 4 核 8G 内存、40G 硬盘。上面已有 RustDesk 中继（端口 21115–21119），不冲突。

需要额外做的：

1. **连模型**：服务器和用户电脑加入同一个 ZeroTier 网络，服务器调用电脑的 ZeroTier 地址。
   - 电脑这边要让 cli-proxy-api 在 ZeroTier 网卡上可访问，并用防火墙规则只放行服务器的 ZeroTier 地址。
   - 这些是用户本机的系统配置，由用户操作。
   - 演示期间用户电脑必须在线。
2. **访问控制**：
   - 加登录，账号由用户发放，不开放注册；
   - 对每个账号限制调用频率和每日分析次数，因为消耗的是用户自己的模型额度；
   - 前面放 Nginx 加 HTTPS。
3. **域名**：大陆服务器用域名提供网页，需要先做 ICP 备案；没备案只能用 IP 访问。
4. **沙箱加固**：重新评估 socket 挂载，优先试 gVisor 运行时。

## 8. 待用户确认

- 本文的范围和验收标准。
- 负责线程定为 main 是否合适（第 2 节已限定：只在新分支开发，不碰冻结版本）。

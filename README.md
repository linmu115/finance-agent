# Finance Agent · 财报研究工作台 0.1

在本机上传财报，通过模型完成资料抽取、财务分析、来源核验、金融建模和联网研究。项目下组织会话，财务数据按项目隔离保存，附件处理进度与入库去向在“附件流向”中查看。

**首次使用请下载 [v0.1 Release](https://github.com/linmu115/finance-agent/releases/tag/v0.1) 中的 `finance-agent-0.1-windows-x64.zip`。** GitHub 自动提供的 “Source code” 是源码包，不包含运行环境。

产品版本为 **0.1**，程序内部版本号为 **0.1.0**。这是首个便携部署版本；历史 benchmark 的 v0.2、v0.3、v0.5 等编号是测试集版本，并非应用发布版本。

## 三步开始

1. **完整解压** Windows x64 部署 ZIP 到一个可写目录，例如 `D:\Apps\FinanceAgent`。不要在压缩包预览窗口中运行。
2. 双击 **`install.cmd`**。它检查包内环境、创建当前用户的桌面快捷方式，然后启动本地页面。无需管理员权限，无需另装 Node、Python、npm 或 Excel。
3. 在页面的 **“API 配置”** 中填写模型地址、模型 ID 和 API Key，点击保存并测试连接。联网研究还需配置 Tavily 或 Brave。随后创建项目、上传文件并发送任务。

正常入口：**http://127.0.0.1:3001/**。

首次启动时，Windows 可能需要检查新解压的依赖文件，启动窗口会显示等待提示。请保留窗口等待，启动器最多等待 3 分钟，成功后再打开页面；不要连续双击启动。

| 文件 | 用途 |
| --- | --- |
| `install.cmd` | 检查环境、创建桌面启动/停止快捷方式并启动 |
| `start-finance.cmd` | 日常启动；已运行时复用本安装目录的服务 |
| `stop-finance.cmd` | 停止本安装目录启动的服务，保留数据；有运行中任务时提示先在应用中停止 |
| `check-install.cmd` | 检查运行环境与依赖，显示数据目录和服务状态 |
| `README.md` | 使用、配置、部署与故障说明 |
| `INSTALL_MANIFEST.json` | 部署包内逐文件 SHA-256 与大小 |
| `RELEASE.json` | 运行环境版本与构建信息 |

安装动作只创建快捷方式和本地数据目录，不修改系统 PATH、不注册开机自启、不安装 Windows 服务，也不自动启动 Docker 或 WSL。关闭浏览器不会停止后台服务；退出时可双击停止快捷方式。

## 系统与联网要求

- Windows 10/11 **x64**。当前部署验收在 Windows x64 上进行；不宣称已经验证 Linux、macOS 或 Windows ARM。
- 解压后为文件夹形式的便携应用，建议使用路径较短的可写目录，至少预留 3 GB 磁盘空间及后续资料空间。
- 内置 Node.js **24.7.0**、CPython **3.12.11** 及锁定依赖；启动无需下载开发环境。
- 基础文档解析、数据存储和内置 OCR 在本机执行。模型分析和联网检索需要网络及用户自己的服务商账号，会产生相应 API 用量。
- Docker 是任意 Python 代码分析/绘图的**可选**运行环境，见下文。固定公式和三表/DCF 等内置建模工具不要求安装 Excel。
- 本版只绑定本机回环地址，不提供公网、多用户账号或团队权限系统。

## API 配置

在应用中配置并保存即可，不需要编辑代码。

| 服务 | 配置建议 |
| --- | --- |
| 主模型 | OpenAI 兼容接口；DeepSeek 官方地址可填 `https://api.deepseek.com`，模型 ID 以账号当前可用模型为准。开发验收使用过 `deepseek-flash`。 |
| 搜索 | Tavily 或 Brave，填写对应密钥；不使用联网研究时可暂不填写。 |
| OCR | 默认使用包内本地识别器；也可按应用提供的接口格式配置远程 OCR。 |
| Embedding | 默认关闭，不是首次启动的必要条件。 |

“保存设置”只证明配置已存储；“测试连接”会发出实际请求，成功后再进行模型任务。不要把 API Key 放进 Git、截图或反馈附件。

密钥保存在 `data/settings.json`，Windows 下由当前用户 DPAPI 加密。部署包与仓库不附带开发者密钥、真实会话数据库、上传资料或沙箱私钥。

## 主要使用方式

1. 创建公司或研究主题项目，在其下建立会话。同项目共享财务数据，不同项目隔离。
2. 添加 PDF、Excel、CSV、TSV。**上传只保存附件，发送任务后才由该会话处理。**
3. 点击右上角唯一的 **附件流向** 入口，查看当前会话的处理记录、提取结果、入库去向及原始页面。处理完成与核验通过是不同状态。
4. 在财报看板按公司、期间、合并/母公司口径等筛选；通过回答中的来源回查原文。
5. 划选会话文字，选择“添加到当前会话”，直接写注释。Enter 保存、Shift+Enter 换行。输入区数量气泡可悬停查看列表，原文角标和已发送引用可重新打开。
6. 项目约定与技能由项目设置管理。内置财务建模、模型复核更新和供应链分析技能；模型可按需调用。
7. SQL、数据删改、跨项目读取等受控操作逐次显示授权卡片。核对操作和参数后再同意；授权只对该次请求有效。

完整报告与分析题见 [samples/native-pdf/验收提问.md](samples/native-pdf/验收提问.md)。包含茅台、伊利两年、海尔、美的 5 份完整年报，共 1220 个 PDF 页面。建议先单份茅台，再做伊利跨年分析。样本和历史测试不代表当前应用对所有财报都能正确抽取或得出正确结论。

## 端口、数据与迁移

默认数据位于安装目录下的 `data/`，日志位于 `data/runtime/`。该目录保存项目、会话、上传原文件、财务数据、成果和配置；退出应用不会删除。

如果 3001 被其他程序占用，启动器会明确报错，不会接管或停止其他程序。可使用：

```powershell
.\start-finance.cmd -Port 3010
.\stop-finance.cmd -Port 3010
```

也可指定独立数据目录，例如：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage.ps1 -Action start -Port 3010 -DataDirectory D:\FinanceData
```

停止时须使用相同的端口和 `-DataDirectory`。同一个数据目录不可同时启动多个服务。

备份前先停止会话任务，再停止服务，复制整个 `data/`。升级时解压新版本到新目录，保留旧版本与数据备份，再迁移数据。**跨电脑或跨 Windows 用户迁移时，不要沿用旧 `settings.json`，请在新环境重新填写 API 配置**，因为 DPAPI 与原用户绑定。不要删除旧备份。

便携卸载：停止服务，删除属于这份安装的桌面快捷方式；确认已备份所需数据后，再自行删除整个安装目录。启动器不提供一键清空研究数据。

## 可选：高级 Python 分析与绘图

基础应用可独立启动。只有需要模型编写并执行任意分析代码时，才需要自己安装并启动兼容的 Linux Docker 引擎，并准备镜像：

```powershell
.\runtime\python\python.exe .\sandbox\download_wheels.py
docker build -t finance-analysis:0.1 .\sandbox
```

首次构建需要网络；依赖使用 `sandbox/requirements.lock` 和带哈希的 `sandbox/wheels.lock.json`。该步骤不是 `install.cmd` 的自动动作。

代码分析容器按任务限制 CPU、内存和时间，默认断网，只读接收导出输入；不会直接挂载主数据库或模型密钥。没有 Docker 或镜像时，这类工具返回不可用，不会改为在宿主机无隔离执行。更多说明见 [sandbox/README.md](sandbox/README.md)。旧机器的 QEMU 镜像、SSH 密钥与 Docker 状态不随包分发。

## 从源码部署与开发

普通使用者优先下载上述部署 ZIP。源码方式需要先安装 Node.js 24+ 和 Python 3.12：

```powershell
git clone https://github.com/linmu115/finance-agent.git
cd finance-agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm ci
npm run build
.\start-finance.cmd
```

源码目录的启动器自动使用系统 Node 和项目 `.venv`。`npm run dev` 启动源码后端；`npm run web` 启动前端开发服务器。生产包使用编译后的后端和已构建页面。

构建部署包需要已准备好的 Windows x64 Node、Python 3.12 和项目依赖。命令示例：

```powershell
npm run build
.\.venv\Scripts\python.exe scripts/build_release.py --plan
.\.venv\Scripts\python.exe scripts/build_release.py --stage
.\.venv\Scripts\python.exe scripts/build_release.py --archive
.\.venv\Scripts\python.exe scripts/verify_release.py --zip dist/release-0.1/finance-agent-0.1-windows-x64.zip --browser
```

构建器先扫描源码与嵌套样本压缩包，排除凭据及运行数据，再建立独立运行目录。归档后检查 ZIP CRC 和逐文件 SHA-256，输出 `SHA256SUMS.txt`。重复构建使用新的 `--output dist/另一个目录`，不会覆盖既有发行包。

部署验收会把 ZIP 解压到新的中文及空格目录，使用包内环境和独立端口执行安装、启停、PDF 解析及数据持久化检查；不会沿用 API 密钥。`--browser` 额外使用开发环境的 Playwright 与已安装的 Microsoft Edge 检查页面；普通使用者无需这些测试工具。证据保存在 `dist/deployment-check-*/`。

## 检查与故障排查

| 现象 | 处理 |
| --- | --- |
| 双击后页面未打开 | 先运行 `check-install.cmd`；查看 `data/runtime/server-3001.stderr.log`，或按所选端口查对应日志。 |
| 找不到运行环境或依赖 | 确认下载的是 Windows 部署 ZIP，且已完整解压；GitHub “Source code” 需要按源码步骤安装。 |
| 端口占用 | 停止占用者，或指定另一个端口；启动器不会自动结束无关进程。 |
| API 显示未配置/连接失败 | 在应用内填写、保存并测试；检查模型 ID、服务商余额及网络。不要发送密钥到仓库。 |
| 容器分析不可用 | 按可选 Docker 步骤准备；这不影响基础页面、文档查询和内置模型工具。 |
| 换电脑后凭据解密失败 | 备份后移走迁移过来的 `data/settings.json`，重新配置 API。 |
| Windows 阻止下载文件运行 | 本包没有商业代码签名。先核对发布页 SHA-256 和来源；必要时在 ZIP 属性中解除锁定后重新解压。 |

开发检查：

```powershell
npm run typecheck
npm test
.\.venv\Scripts\python.exe -m unittest discover -s service/tests -v
```

真实模型与浏览器验收可能调用外部 API，使用独立测试数据目录。已知边界与本次部署验收见 [docs/RELEASE-0.1.md](docs/RELEASE-0.1.md)。

## 目录与第三方组件

`web/` 界面；`server/` 本地 API 与 Agent；`service/` 文档、数据库和模型工具；`skills/` 专业技能；`sandbox/` 可选隔离计算；`samples/` 示例；`benchmark/` 冻结评测与历史证据；`scripts/` 管理和构建工具。

第三方授权见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、`licenses/`，以及包内各依赖自身的 LICENSE/NOTICE。报告样本保留原披露来源和版权；仓库设为私有。

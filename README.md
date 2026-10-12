# Finance Agent v0.4.1

面向财报研究的本地智能体。此版本保留 F2.1 的 v3 底稿流水线、来源追溯与交付检查能力，并修复报告包导出卡死和聊天中文加粗渲染。正式三组评测的总体 E4 优势均未证实，具体深度收益、缺陷与成本见 [发布说明](docs/RELEASE-0.4.1.md)。

**使用本次提供的 `finance-agent-0.4.1-windows-x64.zip` 和 `SHA256SUMS.txt`。本版尚未推送或发布 GitHub Release。** 完整解压后运行 `install.cmd`，默认地址 `http://127.0.0.1:3001/`；API 在界面配置。便携包包含 Node、Python 与生产依赖，Docker 和分析镜像另行准备。[启动与使用](docs/START_AND_USE.md)。

可运行包按允许列表收录产品源码、运行依赖与安装资料，不附带真实项目数据库、会话、评测私有资料或完整研究样本。源码仓库中的历史论文、评测和大样本保持原位置，不代表随部署包分发。历史 benchmark 编号与应用版本独立。

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
- 默认财报清洗与任意 Python 分析/绘图使用 Docker 沙箱，须按下文启动引擎并准备镜像。已有资料查询、固定公式和内置建模工具不依赖 Docker，也不要求安装 Excel。
- 本版只绑定本机回环地址，不提供公网、多用户账号或团队权限系统。

## API 配置

在应用中配置并保存即可，不需要编辑代码。

| 服务 | 配置建议 |
| --- | --- |
| 主模型 | OpenAI 兼容接口；DeepSeek 官方地址可填 `https://api.deepseek.com`，模型 ID 以账号当前可用模型为准。开发验收使用过 `deepseek-flash`。 |
| 搜索 | Tavily 或 Brave，填写对应密钥；不使用联网研究时可暂不填写。 |
| OCR | 默认使用包内本地识别器；也可按应用提供的接口格式配置远程 OCR。 |
| Embedding | 默认关闭。可在“语义检索”中配置兼容 embeddings 的服务，与全文关键词合并检索；首次索引和新增内容按服务商单独计费，相同内容复用缓存。 |

“保存设置”只证明配置已存储；“测试连接”会发出实际请求，成功后再进行模型任务。不要把 API Key 放进 Git、截图或反馈附件。

密钥保存在 `data/active/settings.json`，Windows 下由当前用户 DPAPI 加密。部署包与仓库不附带开发者密钥、真实会话数据库、上传资料或沙箱私钥。

## 主要使用方式

1. 创建公司或研究主题项目，在其下建立会话。同项目共享财务数据，不同项目隔离。
2. 添加 PDF、Excel、CSV、TSV。**上传只保存附件，发送任务后才由该会话处理。**
3. 点击右上角唯一的 **附件流向** 入口，查看当前会话的处理记录、提取结果、入库去向及原始页面。处理完成与核验通过是不同状态。
4. 进入唯一的 **资产看板**，按研究对象查看“总览、财务与经营、机构预期、观点与证据、模型与成果”。披露事实与研报预测仍分别保存；来源按钮回到原文，选中记录可带引用继续分析。
5. 划选会话文字，选择“添加到当前会话”，直接写注释。Enter 保存、Shift+Enter 换行。输入区数量气泡可悬停查看列表，原文角标和已发送引用可重新打开。
6. 项目约定与技能由项目设置管理。内置研报入库、财务建模、模型复核更新和供应链分析技能；模型可按需调用。
7. 研报完整入库同时检查数值表和正文页。同一表中的历史值与预测只清洗一次；每个公司、机构、发布日期、期间和情景分别保存。按“截至某日”提问可避免混入后续报告，日期不明的材料会明确排除。无法可靠提取的图形和歧义保留为待核验，完成处理不代表人工核验通过。
8. SQL、数据删改、跨项目读取等受控操作逐次显示授权卡片。核对操作和参数后再同意；授权只对该次请求有效。

首次使用可上传自己合法取得的财报与研报，按 [启动与使用](docs/START_AND_USE.md) 中的示例任务处理。包内仅保留一个公开 PDF 小样，供安装脚本验证原文解析；历史研究样本与评测资料不随本包分发。

**附件看板**按当前项目逐条列出已登记资料、类型、处理状态和入库数量，可查看原文。删除某份资料时，在该行确认后清除其财务事实、全部历史研究记录、预测、观点、原文解析、检索条目及关联处理快照/产物。其他资料保留；正在执行任务的项目需先完成或停止任务，防止写入与删除同时进行。历史会话文字、已存在的备份不会被改写；依赖已删来源的保存模型会显示来源失效。“附件流向”仍用于当前会话的处理进度，“附件看板”用于项目层面的资料清单。原“数据集与测试”导航已移除，开发评测脚本和历史证据继续在源码仓库保留。

资产看板的 **观点与证据** 展示已从研报提取的定性研究记录，包括研究观点、风险、催化因素及引用的管理层表述，保留提出者/机构、发布日期、原句、页码与待核验状态。可搜索、过滤、查看原文或选中记录继续分析；这里的“证据”表示可追溯依据，不表示观点已被证实。机构预期侧重预测数值，模型与成果保存应用计算或撰写的研究产物。

本版正式评测显示局部分析深度提升，同时保留材料范围、单位与币种标签、可比口径语义等交付缺陷。两个主对比的总体 E4 优势均未证实；输入成本的完整口径见 [发布说明](docs/RELEASE-0.4.1.md)。

## 端口、数据与迁移

默认运行数据位于安装目录下的 `data/active/`，日志位于 `data/active/runtime/`。该目录保存项目、会话、上传原文件、财务数据、成果和配置；退出应用不会删除。

日常只使用 **3001**。如果端口被其他程序或旧版占用，启动器会明确报错；先确认并停止其所属实例，再启动新版，不自动另开测试端口。需要把数据放在另一块磁盘时，可在同一个 3001 指定目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage.ps1 -Action start -Port 3001 -DataDirectory D:\FinanceData
```

停止时须使用相同的端口和 `-DataDirectory`。同一个数据目录不可同时启动多个服务。

备份前先停止会话任务，再停止服务，复制实际数据目录。v0.1 默认数据在 `data/`，v0.3.0 及本版默认在 `data/active/`；升级时必须确认数据库 `finance.sqlite` 的实际位置，不能只移动配置文件。具体步骤见 [升级迁移](docs/START_AND_USE.md#从-01-或当前开发目录升级)。**跨电脑或跨 Windows 用户迁移时重新配置 API**，DPAPI 加密与原用户绑定。保留旧备份。

便携卸载：停止服务，删除属于这份安装的桌面快捷方式；确认已备份所需数据后，再自行删除整个安装目录。启动器不提供一键清空研究数据。

## 财报脚本清洗、Python 分析与绘图

基础应用可独立启动。新财报默认由模型编写 Python 清洗规则，先在沙箱运行、核对原文和候选结果，再由服务写入数据库。使用这一流程或自由 Python 分析前，请安装并启动兼容的 Linux Docker 引擎，并准备镜像：

```powershell
.\runtime\python\python.exe .\sandbox\download_wheels.py
docker build -t finance-analysis:0.1 .\sandbox
```

首次构建需要网络；依赖使用 `sandbox/requirements.lock` 和带哈希的 `sandbox/wheels.lock.json`。该步骤不是 `install.cmd` 的自动动作。

代码分析容器按任务限制 CPU、内存和时间，默认断网，只读接收导出输入；不会直接挂载主数据库或模型密钥。没有 Docker 或镜像时，这类工具返回不可用，不会改为在宿主机无隔离执行。更多说明见 [sandbox/README.md](sandbox/README.md)。旧机器的 QEMU 镜像、SSH 密钥与 Docker 状态不随包分发。

清洗脚本只输出带来源坐标的规则和候选映射，数值由服务重读原始单元格取得；已提交的表有检查点，可继续剩余部分。主库任意 SQL、删改和跨项目访问仍逐次请求授权。每次终结的任务回复下方可展开用量详情，查看输入、输出、缓存命中、思考和各阶段费用；未返回用量的请求会明确标为未知，估算不等同实际账单。

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

源码目录的启动器自动使用系统 Node 和项目 `.venv`。日常使用构建后的单服务 3001；开发者可在先停止原实例后使用 `npm run dev`。生产包使用编译后的后端和已构建页面，不需要额外前端服务。

构建部署包需要已准备好的 Windows x64 Node、Python 3.12 和项目依赖。命令示例：

```powershell
npm run build
.\.venv\Scripts\python.exe scripts/build_release.py --plan
.\.venv\Scripts\python.exe scripts/build_release.py --stage
.\.venv\Scripts\python.exe scripts/build_release.py --archive
.\.venv\Scripts\python.exe scripts/verify_release.py --zip dist/release-0.4.1/finance-agent-0.4.1-windows-x64.zip
.\.venv\Scripts\python.exe scripts/verify_release_offline.py --zip dist/release-0.4.1/finance-agent-0.4.1-windows-x64.zip
```

构建器先扫描源码与嵌套样本压缩包，排除凭据及运行数据，再建立独立运行目录。归档后检查 ZIP CRC 和逐文件 SHA-256，输出 `SHA256SUMS.txt`。重复构建使用新的 `--output dist/另一个目录`，不会覆盖既有发行包。

本版离线包验收会把 ZIP 解压到新的中文及空格目录，使用包内 Node/Python，通过 stdio MCP 验证文档解析和重连持久化，不开启额外 HTTP 端口、不调用模型 API。它不能代替首次 HTTP 启停验收。完整 HTTP 启停脚本 `verify_release.py` 仅用于另行安排的独立环境，执行前必须确认端口与数据隔离。实际执行范围见发布资产的验证 JSON。

## 检查与故障排查

| 现象 | 处理 |
| --- | --- |
| 双击后页面未打开 | 先运行 `check-install.cmd`；查看 `data/active/runtime/server-3001.stderr.log`，或按所选端口查对应日志。 |
| 找不到运行环境或依赖 | 确认下载的是 Windows 部署 ZIP，且已完整解压；GitHub “Source code” 需要按源码步骤安装。 |
| 端口占用 | 确认旧实例归属、停止旧实例，再在同一 3001 启动；启动器不会结束无关进程。 |
| API 显示未配置/连接失败 | 在应用内填写、保存并测试；检查模型 ID、服务商余额及网络。不要发送密钥到仓库。 |
| 清洗／容器分析不可用 | 按 Docker 步骤准备引擎与镜像；基础页面、已有文档查询和内置模型工具仍可使用。 |
| 换电脑后凭据解密失败 | 备份后移走迁移过来的 `data/active/settings.json`，重新配置 API。 |
| Windows 阻止下载文件运行 | 本包没有商业代码签名。先核对发布页 SHA-256 和来源；必要时在 ZIP 属性中解除锁定后重新解压。 |

开发检查：

```powershell
npm run typecheck
npm test
.\.venv\Scripts\python.exe -m unittest discover -s service/tests -v
```

真实模型验收会调用外部 API。已知边界与本次部署验收见 [docs/RELEASE-0.4.1.md](docs/RELEASE-0.4.1.md)。

## 目录与第三方组件

`web/` 界面；`server/` 本地 API 与 Agent；`service/` 文档、数据库和模型工具；`skills/` 专业技能；`sandbox/` 可选隔离计算；源码仓库中的 `samples/` 示例与 `benchmark/` 历史评测不整体随可运行包发布；`scripts/` 管理和构建工具。

第三方授权见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、`licenses/`，以及包内各依赖自身的 LICENSE/NOTICE。报告样本保留原披露来源和版权；仓库设为私有。

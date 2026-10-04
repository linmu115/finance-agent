# Python 财报数据服务 · v0.3

本服务提供 Pi 会话可调用的文档、清洗、数据库和分析工具。Pi 管理任务、模型调用、上下文、进度及取消；上传接口只登记附件。用户发送消息后，当前 Pi Session 通过 process_documents 完成全部可提取财务主表和附注表的理解、分批入库与看板更新。

```powershell
$env:FINANCE_DATA_DIR = "D:\codex\金融\data"
.venv/Scripts/python.exe -m service.server
```

通过官方 Python MCP SDK 的 stdio 连接，标准输出仅传输协议。Node 使用 @modelcontextprotocol/sdk，向 Pi 提供项目绑定的工具白名单。实际签名见 server.py；tool-schema.json 保存工具签名，并标明生产路径和历史兼容入口。

## 会话内处理链

1. register_document 保存原文件并返回 registered 文档。登记阶段不解析、不调用模型、不生成财务事实。
2. 当前 Pi Session 调用宿主工具 process_documents(document_ids, force?)。宿主注入当前项目、运行 ID 和临时模型桥凭证，调用 start_document_processing；这些内部参数不由模型提供。
3. 服务读取原文、页面、表格、Excel 合并表头及单元格坐标，建立全文关键词索引和项目 YAML 导航。原生 PDF 在独立解析进程中处理，避免 PyMuPDF 表格提取的进程级共享缓冲区在并发线程间串扰。
4. LangExtract 1.3.0 使用 OpenAI 兼容协议请求当前运行的私有 Pi 模型桥。桥通过 Pi 模型运行时调用配置的 DeepSeek 官方 API，用量、进度与取消归属当前会话。本服务不单独配置或直接调用 DeepSeek。
5. 模型解释字段、期间、币种、单位、口径、重述和分部。程序根据模型指向的原单元格取值，以 Decimal 执行倍率换算并逐批提交 SQLite。字段目录可增加新指标；同比百分率与金额必须使用不同指标。
6. 同一 Pi 运行审校项目指标目录，再检查所有已入库指标的期间语义；只有需复核的原文行列进入定点日期修订。目录和期间概览使用明确的 low 推理配置，原表抽取与定点日期修订保留 high；配置独立进入缓存签名。
7. Pi 工具等待并持续报告进度，完成后返回覆盖情况；看板和其他会话可以查询已提交的数据，无需等待整份报告结束。

LangExtract 提供原文位置对齐和结构化抽取。表级、行级、列级映射支持混合摘要表、横向不同指标、季度与累计期间、调整前后及分部维度。发现空列映射、漏行或单位冲突等具体问题时，会带原表和问题再请求一次模型纠正。仍未解决的项目保留问题记录，不伪造数值，也不自动切回规则抽取。

## 工具与返回协议

全部 MCP 工具返回：

```json
{"status":"ok","data":{},"source_refs":[],"warnings":[],"trace_id":"..."}
```

status 为 ok、accepted、insufficient_evidence 或 error。错误代码位于 data.error。项目相关工具验证 project_id，文档、任务、事实和产物再验证所属项目。

| 工具 | 用途和主要返回 |
|---|---|
| create_project / list_projects | 宿主项目管理，包含项目文档数 |
| register_document | 宿主保存附件；返回文档 ID、状态、去重标志 |
| start_document_processing | 宿主为 Pi 工具启动处理，返回 processing_id；临时运行凭证只留内存 |
| get_processing_status / cancel_processing | 所属运行的进度、文档列表、事实数、覆盖统计及取消 |
| get_data_catalog | 实际数据库、原文件和 YAML 路径；动态指标、公司、期间、口径、币种和处理状态 |
| get_document_index | 指定文档的 YAML 导航内容：页标题、表 ID、原始资料位置 |
| query_financial_data | 按公司、指标、期间、年份、口径、币种、分类、文档、版本和分部过滤，支持分页 |
| get_dashboard | 宿主看板读取 documents、facts、catalog、total、truncated |
| get_normalization_details | 摘要与分页 LangExtract 映射；支持 table_id、limit（默认20，最多20）、offset，返回 total；包含历史版本数 |
| list_documents / get_document | 文档来源、表数、事实数，新模型清洗与旧规则数据的区分 |
| get_source_table | 目录与前 5 行；传入 table_id 时读取完整表、公式和单元格位置 |
| get_source_page | 页面原文、物理页码、可选原页图像 |
| search_evidence | FTS5 关键词检索；处理中但已建立索引的资料也可查询 |
| get_financial_metrics | 常用指标便捷查询，同时识别动态目录中的指标 ID 与中文规范名称 |
| calculate_financial_metrics | Decimal 公式、输入、精确结果、单位和来源 |
| run_analysis / get_analysis_status / cancel_analysis | 独立科学计算容器中的 Python 分析与图表产物 |
| get_artifact | 已核验产物的位置、格式、大小和哈希 |
| get_app_state / put_app_state / list_app_state | 宿主持久化会话和运行状态 |

process_documents 在 Node 的 Pi 工具层定义，不属于本服务 MCP 列表；它组合启动、轮询与取消。模型不会直接收到宿主配置工具、桥凭证或后台任务管理权限。

query_financial_data 默认每页 200 条，上限 200，返回实际 limit、offset 和 total；大请求也按 200 条分页，调用方依据实际返回的页长继续读取全部记录。看板首批至多 200 条并给出截断标记。此限制避免完整源格证据使单条 MCP 消息超出传输大小。事实包含 label、statement、period_start/end、version/restatement、dimensions、normalized_unit、source_ref。金额以原币基础单位保存，百分率保留百分数值，每股指标保存独立单位，不执行没有依据的汇率换算。

口径区分 consolidated_CAS、parent_CAS、consolidated_IFRS、parent_IFRS、unspecified。期间包括年度、季度、半年、九个月累计、日期时点及有原文依据的跨年区间（YYYY-MM-DD/YYYY-MM-DD）。分部、币种、版本、口径不同的数据分别保存，查询与绘图不得盲目相加。显式传入空筛选列表返回零条记录，省略筛选条件才表示不限。

## 项目共享与并行

- 同项目共享数据库、原文件、索引和看板；每段会话保留独立 Pi Session 与运行状态。
- 服务最多同时推进 4 个会话文档工具，每个文档的 LangExtract 批次最多并行 4 个请求；请求仍经过所属 Pi 运行的模型桥。小表按不同 table_id 打包推理，每组最多 3 表、28 行、14000 字符，同页上下文只提供一次；提交、修复和恢复仍保持原切片粒度。
- 相同项目、相同文件内容复用已登记文档。同一文档同时提交时共享正在进行的处理。
- 取消等待共享文档的会话，不停止原拥有者。原拥有者取消或失败时，仍需要该文档的会话可使用自己的 Pi 运行继续处理。
- force=true 明确重新清洗。中断恢复会按原切片复用已保存且模型/提示一致的抽取，重新物化即可修复标签，不因目录变化重调整篇模型。自动复用完成结果要求清洗器版本、模型和映射提示版本一致；问题未解决的结果允许重试。
- 批次提交使用短事务，更新旧单元格前将其存入 fact_history。无法完成新映射而保留的旧值带 previous_version_unresolved 标记和原因。
- processing_runs 持久化处理状态；服务重启将中断运行标记为失败，可在会话里继续处理，已提交数据和原文保留。

## 数据目录与执行范围

默认根目录是 FINANCE_DATA_DIR：

```text
finance.sqlite                       项目、文档、事实、全文索引、批次及历史版本
documents/<project_id>/              原始附件
indexes/<project_id>/catalog.yaml    自动生成的资料与表格导航
indexes/<project_id>/<document>.json 逐页原文、原表格及提取位置
exports/                            科学计算容器输入副本
artifacts/                          页面预览及分析产物
```

SQLite 使用 WAL、外键和短写事务，Python 服务负责写入。模型可通过工具了解真实位置并读取业务内容；不提供宿主 shell、任意文件读取或数据库直写权限。

v0.3 生产路径禁用 Embedding：Node 明确配置 embedding.enabled=false。查询使用 YAML 导航、逐页原文、原始表格、SQLite 和 FTS5。中文关键词使用重叠二元词，拉丁文字使用词项。

PDF 保留页面与单元格坐标，页码是上传文件的物理页，从 1 开始。页面预览也使用独立 PDF 子进程，并在完整 PNG 生成后发布文件，避免并发线程共享原生渲染状态。Excel 保留合并范围、公式及已有数值缓存；缺失缓存不会变成零。CSV/TSV 保留原始行列。扫描页仍可按 OCR 设置处理；OCR 属于文档识别器，不是本地大语言模型。

模型桥临时凭证不写数据库、YAML 或报告。OCR 配置只留进程内存。科学代码仅交独立容器执行，输入是当前项目表格和全部动态指标的 JSON 副本；容器无模型密钥和数据库连接。

## 历史兼容接口与验证

- ingest_document、get_ingestion_status、cancel_ingestion 保留给旧版确定性规则基线及回归测试，不是 v0.3 的上传生产路径。旧规则数据标记为 legacy_rules，不声称已经过 LangExtract 清洗。
- configure_processing 的旧 Embedding 配置、index_embeddings 及回归测试仅为兼容保留；当前 Pi 白名单不开放这些入口，应用不启用它们。

```powershell
.venv/Scripts/python.exe -m unittest discover -s service/tests -p "test_*.py" -v
```

当前服务回归覆盖：实际 stdio MCP、实际 LangExtract 经本地协议测试桥抽取、上传只登记、动态指标、百万/外币单位、重述历史、合并表头、横向指标、增长率与金额分离、PDF 多进程一致性、同文件共享与取消接续，以及原有解析计算回归。协议测试桥使用受控响应，不能算作真实 DeepSeek 准确率。

真实模型验收独立记录在 benchmark/results/。v0.3 标准化测试集位于 benchmark/versions/v0.3-normalization/；预期答案只供宿主评分，不作为 Agent 输入。完整年报执行与少量原文数值锚点校验，也不等于逐条验证所有提取事实。

scripts/verify_financial_pipeline.py --runs 3 继续复现旧版三份 PDF、708 页、30 个主要指标的规则基线，不能代替新的 Pi/LangExtract 验收。

## v0.3.4 的物化、指标目录与期间审校

模型解释横向表格时，列指标与行主体分别保留：例如“期末余额”的 financial_item 维度保存“交易性金融资产”，dimension_labels 保存中文轴标签。每 10 股金额以 CNY/10shares 保存完整单位；276.24 元/10 股仍是 276.24，unit_conversion 另给出 27.624 CNY/share 及 0.1 转换因子。

同一个 Pi process_documents 完成表格后，使用原运行的模型桥调用 LangExtract 审校项目指标目录。目录归并读取指标定义、单位、报表类型及原表上下文，模型只可选择目录已有 ID；原 metric/label 和归并证据保存于 source.normalization。营业收入、营业总收入、分部收入及不同净利润口径保持概念边界。事务提交前重读目录，并继续处理并发新增字段。目录与提示词版本未变时复用真实审校结果；catalog_review 明确区分 not_run、partial 和 reviewed。

宿主维护接口 rematerialize_documents(project_id, document_ids) 仅回放 normalization_batches 已保存的模型抽取，不解析新材料、不调用模型、不触发目录语义审校。用于修复物化代码后更新历史事实，保留真实 extraction_processing_id，并把零模型调用审计写入 exports/。该接口不进入 Agent 工具白名单，不产生用户可见的独立入库任务。不能追溯所有者的旧推理缓存不复用；有 normalization_batches 原记录的批次仍可直接恢复。

期间审校包含全部已有事实的紧凑行列语义概览，不局限于互相矛盾的日期；例如全项目一致把资产余额写成年流量，也必须进入模型审阅。概览每片最多 100 组、约 60000 字符，3 路并行；定点复核按原表上下文去重，同样 3 路并行推理，主线程逐片校验并提交。模型只修改 period/start/end，不修改数值、单位、币种、口径或指标。没有原文依据的计划归属日期记为 unresolved，不自动赋年度。

事实的 source_ref.normalization.temporal_correction 保存 before/after、原文证据、源格指纹、原抽取哈希及真实 Pi 所属运行；get_data_catalog.temporal_review 公开完整覆盖计数与待定项。缓存与校正绑定原抽取和源坐标，重新物化后可零模型调用叠加。并发新来源及已被其他审校更新的日期不会被旧快照覆盖；公开完成状态选取与当前全部来源一致的审校报告。完整审校输入覆盖与模型原始输出分别留在 temporal_project_reviews、temporal_review_cache。

再次处理相同原始映射时，已完整审阅的期间概览与已解决来源直接复用。只对未决、已变更或新增加的来源继续审校；未决来源补上同一文件前两页、本页、后一页全文及原表表头。原审阅输出与原 Pi 所有者仍在审计中保留，跨年区间必须与起止日期严格相符。新报告分别给出累计覆盖与本次新增工作，不把再次保存证据当作新增日期错误修复数。

Pi 可在同一个 process_documents 里显式传 review_metrics 指定需要复核定义的指标。LangExtract 查看这些指标全部源行的标题、列头、定义和排除条款，原表数值单元格不参与同义判断；年份、每股分母和期限限定仍保留。同表同一行且定义相同的年度列合组，族间并行、同族批次继承已确认的目录定义。模型逐组保留正确指标或按不同定义拆分，只修改 metric、label、definition、definition_scope；scope 会计口径、数值、单位和日期均不变。

定义修订保存在 fact_definition_corrections 与 source_ref.normalization.definition_review，公开目录 definition_review 展示覆盖、定义和未决项。共同提交与维护回放按原源格指纹叠加这些修订，后续普通目录归并不会覆盖已确认的定义。字段 original_metric 始终保留原模型映射，因此定义名称变化不会触发全项目期间重新推理。

明确的年数单位以 years 保存；没有时序归属的政策、税率、预算内容仍可通过原文与原表查询。原文索引完整不表示每个数值都已成为标准化时间序列。

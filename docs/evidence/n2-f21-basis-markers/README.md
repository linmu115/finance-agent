# F2.1-A 验收记录

范围：`service/workpaper_basis.py::scan_basis_markers` 通用语言纠偏。基线 main `14b9bde`，无 LLM 调用。

## 来源和回放方式

F203 的 F1_X7/F2_X7 markers、两轮 `review-v4-round*-decoded.json` 均指向同一处误判。原产物的 document_id 与原句表明 p12/p94/p163 属于**海尔 2024 年报**，并非 Carote；按真实来源留存测试，不改写公司身份。Carote 的现有开发材料是 55 页中报。

复制 `data/active/finance.sqlite` 和 WAL 到 worktree 临时目录，连接临时库时使用 `mode=ro`。SHM 原文件锁定未复制，临时 SQLite 自行建立本地索引。仅读取以下三个固定文档，未读取 held-out 文档或参考答案：

| 材料 | document_id | 页数 |
|---|---|---:|
| 伊利 2024 年报 | d84573bf6b584e7e874faa4c6adf454a | 270 |
| 海尔 2024 年报 | e7b0d9679ddc4b739f8f35ecb6dc6227 | 247 |
| Carote 2025 中报 | 3d9d0befd8374eed9a7488dbd8dd00d2 | 55 |

前后两版 `basis_changes` 都用同一临时库、同一其余程序代码全量执行。最终扫描函数的全部结果与回放底稿的 95 条 markers 逐字段相等。金额调整、比率影响、连续非经常项目、未识别行、observations 共 5 张表逐字段未变；重述判断仍为伊利 false、海尔 true、Carote false。

复现命令（从仓库根目录运行，snapshot 必须是已复制的临时库）：

```powershell
& 'D:\AI\财报agent\.venv\Scripts\python.exe' scripts/replay_f21_basis_markers.py --snapshot .tmp/f21-markers/finance.sqlite --out docs/evidence/n2-f21-basis-markers --baseline 14b9bde
& 'D:\AI\财报agent\.venv\Scripts\python.exe' -m unittest service.tests.test_basis_markers service.tests.test_workpaper_basis service.tests.test_report_package -q
```

## 状态分布

单元测试 **19/19 通过**。含真实原页正例、全部 5 种类型的明确完成语、政策/估计区别、混合标题、模板条件句、不适用勾选、未来事项、泛泛政策描述，以及“已执行但零影响”和“政策已执行但无需重述”的局部否定。

| 材料 | 版本 | reference_only | unclassified | change_disclosed | restatement_disclosed | not_applicable | no_impact_or_no_change | 总数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 伊利 | 前 | 19 | 0 | 0 | 0 | 7 | 3 | 29 |
| 伊利 | 后 | 0 | 32 | 0 | 0 | 8 | 3 | 43 |
| 海尔 | 前 | 27 | 0 | 3 | 0 | 1 | 0 | 31 |
| 海尔 | 后 | 0 | 36 | 7 | 3 | 1 | 0 | 47 |
| Carote | 前 | 2 | 0 | 0 | 0 | 1 | 0 | 3 |
| Carote | 后 | 0 | 5 | 0 | 0 | 0 | 0 | 5 |

`unclassified` 的 73 条说明均精确为“未自动判定是否本期发生，需对照原文核对”。`no_impact_or_no_change` 仅引用原文明示内容，未由零影响推断未执行。

新增 32 个词语命中（伊利 14、海尔 16、Carote 2）来自准则执行、解释编号、重分类、普通“重述”和并列政策标题的识别，不等于新增 32 个事件。原有 63 个词语命中全部保留，未删除复杂项。伊利新增一条政策标题的不适用归属；Carote 原来跨句吸附的 `not applicable` 改为未知。

`change_disclosed` 延用已有接口：其中海尔 p163、p213 的 2 个原有单项“√适用”标题只表示该项披露适用，说明明确保留执行时间待对照正文；不计为新增完成语确认。

## 全量核对新增确认项

新增 8 条确认标记对应以下 5 处原文；逐一核对，**8/8 有明确完成或实施表述**。伊利、Carote 新增确认均为 0。

| 页码 | 类型及条数 | 原文明示依据 | 结果 |
|---|---|---|---|
| 海尔 p12 | 同控合并 1、重述 1 | “报告期内（2024 年12 月），公司完成对于物流业务的并表（同一控制下企业合并）”；“对于前三季度财务数据进行了重述” | 分别 change_disclosed、restatement_disclosed |
| 海尔 p94 | 政策 1 | “本公司根据财政部发布的《企业会计准则解释第18 号》的规定，将本公司计提的保证类质保费用计入‘营业成本’，不再计入‘销售费用’” | accounting_policy / change_disclosed |
| 海尔 p94 | 政策 1、重述 1 | “本公司采用追溯调整法对可比期间的财务报表数据进行相应调整” | 分别 change_disclosed、restatement_disclosed |
| 海尔 p163 | 政策 1 | 与 p94 同一质保费用实施说明 | accounting_policy / change_disclosed |
| 海尔 p163 | 政策 1、重述 1 | 与 p94 同一追溯调整实施说明 | 分别 change_disclosed、restatement_disclosed |

p94 混合章节标题中的“会计估计变更”仍保留为 `unclassified`，其原句不再混入质保正文。质保正文单独归政策，不产生估计变化事件。p161 的“变更当期予以确认”等通用政策说明也保持未知。

## 文件与边界

- `summary.json`：状态/类型分布、转移、8 条新增确认的完整句子与依据、数值表不变校验。
- `*-before.json` / `*-after.json`：三份底稿全部 markers，含原句、文档和页码。
- 单元测试 fixture：`service/tests/fixtures/f21_basis_marker_pages.json`，保留海尔上述三页完整入库原文。
- 未运行新的盲评、未改主库、未改主目录文件、未合并或部署、未操作 3001。19 项测试和开发材料回放不能代替 main/N1 后续 F2.1 门槛评审。

与任务的差异仅为纠正 p12/p94/p163 的公司归属；需求所指的全部具体原句均已覆盖。状态名延用 `change_disclosed` / `restatement_disclosed`，避免改变底稿消费接口；未知状态按要求改为 `unclassified`。

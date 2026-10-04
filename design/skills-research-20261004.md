# 财报 Agent 专业技能调研

核查日期：2026-10-04。状态：在线来源与文件内容核查；未安装、未启用、未执行候选脚本，未完成 DeepSeek 效果评测。本文建议不是用户已经批准的实施范围。

## 结论

优先候选是 Anthropic 官方金融技能中的三表联动、可比估值、模型核验、模型更新、行业概览；DCF 的研究流程值得复用，但现版本有已核实的问题，需修改与验证后才能接入。供应链方向分为上市公司产业链研究和企业运营两类；本项目当前更适合前者，再按任务补充供应商风险与供应冲击情景。

技能提供分析步骤、检查规则和输出约定。实际取数、计算、文件生成与数据库写入仍需要应用工具；技能文本本身不提供数据订阅、工具权限或计算正确性保证。

## 候选及用途

| 候选 | 本次核查到的内容 | 本项目匹配判断与接入条件 |
| --- | --- | --- |
| [Anthropic financial-analysis](https://github.com/anthropics/financial-services/tree/main/plugins/vertical-plugins/financial-analysis) | 包含 dcf-model、3-statement-model、comps-analysis、audit-xls 等技能；官方仓库 Apache-2.0 | 首批重点。原工作流较依赖 Excel，应将本地取数、计算与成果保存工具接入；不能照搬工具名、路径和 Office 环境假设。 |
| [3-statement-model](https://github.com/anthropics/financial-services/blob/main/plugins/vertical-plugins/financial-analysis/skills/3-statement-model/SKILL.md) | 在既有模板中填入历史数据，联动利润表、资产负债表、现金流量表并检查勾稽；预测和派生单元格使用公式 | 三表建模的流程参考。现应用尚需支持相应模型结构、运算和表格导出，不能仅加提示词便声称三表联动已经可用。 |
| [model-update](https://github.com/anthropics/financial-services/blob/main/plugins/vertical-plugins/equity-research/skills/model-update/SKILL.md) | 按财报、指引、宏观或事件变化更新假设和估值，并呈现变更 | 与本项目研究成果版本和依赖机制较吻合；应保留旧版本与输入依据。 |
| [sector-overview](https://github.com/anthropics/financial-services/blob/main/plugins/vertical-plugins/equity-research/skills/sector-overview/SKILL.md) | 行业边界、价值链、竞争结构、重点公司、估值背景与来源要求 | 更接近上市公司产业链研究，可结合本地材料、已配置联网检索以及现有 industry_chain 成果。它本身没有实现成本向利润、估值传导的完整定量模型。 |
| [Oria industry-analysis](https://github.com/andreworia/claude-finance-skills/blob/main/packs/investment-banking/skills/industry-analysis/SKILL.md) | 波特五力，包含供应商与客户议价能力、行业利润分布及判断的反转条件；MIT | 作为行业概览的补充，采用轻量方法部分即可，避免与官方行业技能重复加载。当前精确路径是 packs/investment-banking/skills 下，部分搜索目录仍引用旧路径。 |
| [awesome-supply-chain](https://github.com/kishorkukreja/awesome-supply-chain) 中 [supplier-risk-management](https://github.com/kishorkukreja/awesome-supply-chain/blob/main/skills/supplier-risk-management/SKILL.md)、[scenario-planning](https://github.com/kishorkukreja/awesome-supply-chain/blob/main/skills/scenario-planning/SKILL.md) | 社区项目，MIT；相关文件覆盖风险分类、供应中断、敏感性与概率情景，包含 Python 示例 | 可用作方法参考。很多任务需要企业内部采购、成本和交付数据；分值、阈值和概率假设必须按来源与行业重新确认。当前文件树未见 tests/evals 目录，不能宣称示例已通过财务验收。 |
| [vendor-assessment-qcc](https://github.com/duhu2000/vendor-assessment-qcc/blob/main/SKILL.md) | 社区供应商评估技能，Apache-2.0；Kraljic 分类、多维评估，指定企查查 MCP 工具 | 适合未来国内供应商尽调。不是企查查官方技能；仓库里的工具名称不证明本应用已经接通相应服务。需另核对账户、数据权限、MCP 与相对引用文件完整性。 |

## 已发现的实际问题

1. **DCF 资本权重**：当前官方 dcf-model/SKILL.md 约 224–240 行及 1053–1060 行使用净债务和企业价值计算权重，并接受负债务权重。作者仓库 [issue 340](https://github.com/anthropics/financial-services/issues/340) 与 [修复 PR 344](https://github.com/anthropics/financial-services/pull/344) 对应这一问题。本次读取 GitHub API 显示两者仍 open；直接读取 main 文件也确认相关文本尚在。接入时需要修正并加计算校验，不将外部技能视为计算标准答案。
2. **Excel 重算依赖未打包完整**：三表和 DCF 技能要求 recalc.py，本次 main 递归文件树未找到该文件；[PR 358](https://github.com/anthropics/financial-services/pull/358) 仍 open。应核对本项目的公式重算方案，不能交付只有公式但没有核验的表格。
3. **原交互约定不应自动成为本产品规则**：部分金融技能要求每个建模阶段都暂停确认。用户当前明确要求的是特定数据库高权限操作逐次授权；原技能的其他交互方式需要适配，不额外把逐段审批引入产品。
4. **外部数据另行授权**：官方仓库列出多家金融数据 MCP，并注明可能需要服务商订阅或 API 密钥。开源技能许可不包含数据服务许可。[官方连接器说明](https://github.com/anthropics/financial-services#MCP-Integrations)。

## 本地接入核查

- `server/runs.ts` 的 DefaultResourceLoader 当前设置 `noSkills: true` 和 `noContextFiles: true`。当前应用不会因为 Codex 全局安装了技能或项目多了 agent.md 就自动读取。
- 模型仍可使用 DeepSeek。可迁移的是技能的说明、方法与配套资源；Claude 插件命令、托管 API、Office JS 能力并非自动兼容。DeepSeek 对适配后技能的遵循效果仍需实际验证。
- 本地已有财务数据查询、原文证据、隔离计算、DCF/可比估值/制造业情景等计算与研究成果接口。应先将候选方法映射到这些入口，缺失能力再单独开发。
- 分层建议（待用户后续确定）：项目 agent.md 定义项目约定；技能负责具体分析流程；工具负责取数和计算；权限系统负责用户要求的数据库操作逐次授权。技能加载不得替代权限检查。
- 产业链研究的额外需求是让上下游关系有证据，采购/收入敞口有口径，价格与销量冲击有可复算假设，再连到利润、现金流和估值。本次候选没有一个已经在本项目内完成这条链路的实际验收。

## 建议接入顺序（未批准、未实施）

1. 模型核验、模型更新、三表联动与可比估值。
2. 修正后的 DCF 流程；行业概览和五力中的互补部分。
3. 与现有制造业情景计算衔接的供应冲击、成本传导方法。
4. 确有供应商尽调任务、数据和服务账户后，再考虑 QCC 等外部连接器。

## 来源版本快照

GitHub API 于本次调研返回的 main SHA；用于后续复核和固定版本，尚未安装：

| 仓库 | main SHA | API 返回许可证 |
| --- | --- | --- |
| anthropics/financial-services | 574ed3624aebd0418c7e96cd101262f30210ab26 | Apache-2.0 |
| kishorkukreja/awesome-supply-chain | ce33d6be5040e33c64997544a7ce442ccc3e15d7 | MIT |
| andreworia/claude-finance-skills | e19bba60ec18203161854532f283a19023c20d3d | MIT |
| duhu2000/vendor-assessment-qcc | 4552d4d60c7ea20453c7057a012b15d9eea97be1 | Apache-2.0 |

核查方式：网页搜索发现候选；阅读作者 GitHub 页面、README 与具体 SKILL.md；对网页读取失败的文件使用 GitHub Contents API 只读获取；查询仓库树、许可证信息与上述问题状态。未执行第三方代码、未验证外部服务登录、未作真实金融建模基准测试。

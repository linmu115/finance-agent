# 应用内技能来源说明

这三份技能为本应用原创适配，计算器与输入输出契约使用本项目实现；没有复制上游工作簿模板或脚本。

方法调研参考：Anthropic financial-services（Apache-2.0）中 financial-analysis 的 dcf-model、3-statement-model、comps-analysis、audit-xls，以及 equity-research 的 model-update、sector-overview。调研地址：https://github.com/anthropics/financial-services ，审阅版本及已知缺陷记录在 design/skills-research-20261004.md。

供应链风险与情景的候选参考及适用边界也记录在上述调研中。内置技能不依赖 Excel、Claude 专有连接器或外部收费数据；需要特定真实数据时必须显示缺口或由用户提供。

"""Update the editable manuscript for reviewed benchmark methodology; no model answers."""
import json
from pathlib import Path

p=Path(__file__).with_name('manuscript.json')
d=json.loads(p.read_text(encoding='utf-8'))
blocks=d['blocks']
def by_key(key):return next(b for b in blocks if b.get('key')==key)
def paragraph(key,text):return {'type':'paragraph','key':key,'text':text}
def replace_start(start,key,text):
    b=next(b for b in blocks if b.get('text','').startswith(start));b.update(key=key,text=text)

d['version']='论文初稿　2026年10月3日　评测协议 v0.2'
by_key('abstract')['text']='针对财报问答中来源难以定位、金额与会计口径混淆、自由分析代码缺少隔离等问题，本文实现面向单机研究任务的财报分析系统。单一 Pi 智能体组织任务，Python MCP 服务承担解析、查询、检索和十进制计算，SQLite 保存事实及证据，独立 Docker 容器执行科学计算。自建回归集包含三份中文年报和 FinQA 抽样任务，共186题。三轮确定性解析每轮读取708个PDF物理页，30个目标事实的数值、期间、口径与引用均通过，合计90次查询一致，总耗时384.203秒；这一结果不等于语言模型成绩。真实 DeepSeek 另完成三份完整年报的自主查询与容器制图，6个金额及亿元换算经生成后独立核对一致。实验同时发现公开标签存在语义与单位错误，因而采用先读原材料、独立求解、冻结答案后再比较旧标签的代理复核流程。本文区分开发记录、冻结评测与边界探针，保留标注质量、未知版式和开放式分析可靠性的适用限制。'
replace_start('每道模型评测题只导出','input_protocol','每道模型评测题只导出允许的材料，并使用独立项目、会话和缓存。标准答案、参考数据库及含答案的上游原文件位于评分侧，不能挂载到模型任务环境；OCR题只提供图片。模型接收问题、材料和公开的输出单位约定，返回十进制数值、单位、期间、口径与引用。证据不足必须给出对应状态和原因。对未明确要求百分比或比值的增加额问题，协议采用绝对变化；单题的正确答案、歧义标签和复核记录不进入模型输入。')
replace_start('中文金额误差容限','scoring_protocol','中文金额容差为0.01元，同比为0.005个百分点，比值为0.00005；FinQA v0.2依据逐题Decimal结果和显式绝对容差核验，保留披露精度合理的舍入变体。漏答、失败和超时计入分母。来源评分允许一组或多组独立充分证据：直接披露变化额的段落，与两个年度数值所在行，可以构成替代证据集；不要求模型同时引用所有重复位置。表头等有效背景证据单独记录。答案及证据联合正确率要求数值或拒答状态正确，并覆盖至少一组充分证据；引用命中仍不等于开放式论证质量。')
if not any(b.get('key')=='curation_protocol' for b in blocks):
    index=blocks.index(by_key('scoring_protocol'))
    blocks.insert(index,paragraph('curation_protocol','v0.1直接使用公开FinQA执行标签。开发检查发现其中既有公式、年份与数量级错误，也有材料不能唯一确定目标的问题。v0.2保留全部186题和原材料；120道FinQA由分工代理先独立阅读题目与允许材料、保存可复核算式和材料哈希，再与旧标签比较。该流程是独立代理复核，不是人工双人标注。唯一可解的错误标签更正；确有歧义的题目仍保留，要求识别证据不足并引用歧义依据。旧标签和旧评分单独保留，不用模型预测反向生成答案。'))
by_key('agent_chart_result')['text']='合成CSV开发探针已贯通真实模型、容器和HTTP下载，模型在代码失败后自主修正，PNG与JSON产出及两个金额核对通过。随后另开展三份完整真实年报的应用演示，使用完整文档而非仅提供预选题目页。两类输入分别保存证据，不能把合成数据探针当作真实财报成绩。'
if not any(b.get('key')=='demo_result' for b in blocks):
    index=blocks.index(by_key('agent_chart_result'))+1
    blocks.insert(index,paragraph('demo_result','三份完整真实年报的应用演示结果将从独立核对报告导入。'))
for b in blocks:
    if b.get('text')=='6.4 真实模型问答状态':b['text']='6.4 开发基线与冻结评测'
if not any(b.get('key')=='legacy_baseline' for b in blocks):
    index=blocks.index(by_key('model_result'))
    blocks.insert(index,paragraph('legacy_baseline','v0.1真实模型开发基线将从历史汇总报告导入。'))
    blocks.insert(index+1,paragraph('baseline_diagnosis','开发记录暴露了两类实现问题：部分回答未按结构化协议输出；页面与表格工具未把原始text_N、table_N标识完整传回，导致可读证据与评分来源无法稳定对应。后续补回有序段落及逐行来源，并统一输出契约。这些修正改变了代码与提示，必须以新的冻结记录重新评测；旧分数与v0.2分数还涉及标签和评分协议变化，不能把两者之差全解释为模型能力提升。'))
by_key('model_result')['text']='v0.2完整模型评测尚待冻结运行记录。正式结果须同时报告数据版本、模型标识、提示与代码哈希、输入隔离、分题型表现、时延和调用用量，并保留全部失败题。只有完整的124题验收集重复运行记录才能用于判断预设门槛；解析查询、评分器标准答案自检或单次演示都不能替代这一结果。'
replace_start('第一，数据规模','data_limitations','第一，数据规模和标注独立性有限。三份中文年报均参与过解析开发与回归，不代表对未知版式的泛化。公开FinQA也可能进入模型预训练语料，公司划分与运行隔离无法消除预训练污染。v0.2的复核由代理分工进行，保存先解后比记录及哈希，但不是人工双标，更不是权威重新标注；仍可能存在共享偏差和遗漏。标签纠正与系统优化发生在开发阶段，正式成绩必须绑定后续冻结版本。')
by_key('conclusion')['text']='已有证据支持选定材料上的解析可追溯性、真实应用链路和已测试边界行为；公开标签复核还表明，评测正确性本身需要接受原材料与财务语义约束。开发集分数、完整验收结果和单次演示应分别解释。后续重点是未知材料验证、异常版式与口径冲突处理，以及由独立人工评阅开放式报告的事实和论证质量。'
for row in by_key('verification_layers')['rows']:
    if row[0]=='真实模型问答':row[1:]=['旧版开发基线及独立演示已记录','v0.2正式成绩以冻结汇总为准']
p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated protocol source')

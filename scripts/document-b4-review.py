"""Document paragraph decisions against exact native-session snapshots, without deployment."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidence/b4-plan-20261007'
current=json.loads((OUT/'current-context.json').read_text(encoding='utf8'))
proposed=json.loads((OUT/'proposed-context.json').read_text(encoding='utf8'))
m=json.loads((OUT/'measurements.json').read_text(encoding='utf8'))
def count(s):return len(s),math.ceil(sum(.25 if ord(c)<128 else 1 for c in s))
def without_descriptions(obj):
    if isinstance(obj,dict):return {k:without_descriptions(v) for k,v in obj.items() if k!='description'}
    if isinstance(obj,list):return [without_descriptions(v) for v in obj]
    return obj
def q(s):return '\n'.join('> '+line for line in s.splitlines())
def write(name,s):(ROOT/'design'/name).write_text(s,encoding='utf8',newline='\n')

system_reviews={
0:'必改：必须先查询材料才给任何数字，排除了用户直接给定 FCF 的合法任务。可删/合并：项目绑定、字体配置、进度和单位输出已由程序处理，答复要求与后文重复。保留：证据/假设、币种期间与口径选择、资料不能授权、安全边界、精度要求。',
1:'可删：Pi 持久化和界面进度的实现说明；流程参数留工具说明。保留：默认完整入库、主表附注覆盖、low 最低与局部 high。不能把完整入库删成只准备原文。',
2:'可删：文件/索引实现知识与重复工具导航；参数归工具说明。保留：发现真实 metric，局部原文补证、合并/母公司、季度/累计、重述判断。',
3:'可移出主系统：review_existing_only/force 的接口互斥已在 schema/程序；保留工具字段说明。保留：净额/总额和包含范围需语义判断，不能用改数消除冲突。',
4:'可删：归档、分页、PDF 登记的重复程序步骤；放到对应工具的简短说明。保留：实际读取原文、截止日、未知署期、可定位引用、传导系数需要证据；来源与归属判断未自动化。',
5:'必改：所有 DCF 都是财年末估值不适用于 dcf_fcf 的 valuation_date 与 cashflow_timing；起手路径缺 statement_analysis。可删：金额/股数换算和来源继承的机械展开。保留：利润锚点、股权/企业价值、同口径、周转起止余额、扣非税后归属、外推假设。',
6:'可删/合并：保存、版本和依赖状态的重复步骤，工具说明保留 stale 的意义。保留：纠错原文定位、replacement、可证伪条件和传导证据；详细方法仍在按需 schema/技能。',
7:'可删重复：与系统首段和答复方式重复，合并为共享交付段。实质限制不能隐藏。',
8:'可删：压缩/持久化由 Pi 与宿主负责，不要求每轮重新检查。保留：摘要不是精确新证据；分页仍按问题范围读取，next_offset 留工具接口。',
9:'保留：OP 与 EBIT、应计财务费用与现金利息、应收余额与现金投放、少数损益与非经常性不是程序可判的同义关系。可删：重复转抄/舍入指令，以共享绑定表达替代。',
10:'可删：工具序列、分流实现及重复检查点说明；这些接口在工具/按需技能中。保留：完整表页、资料分类、出版日期、研究对象及观点归属、披露与预测分开。',
11:'必改：泛化为 run_analysis report 起手已落后于 K1 底稿优先；保留复杂自由计算。可删：单位转换、四份产物同源的机械展开；保留占位符入口、未知和口径。',
12:'必改：不要笼统声称模型调用返回可直接复制的 model_refs；当前需用 id/revision_id 组成引用。可删：附件/脚本自动导出的叙述。保留：复用、自由布局与 edits；情景更新须补 params/overrides。',
13:'保留：needs_review 的局部影响与未知≠零；可删：多个工具的重复用法、程序保留数据的细节。不能删成“有疑点一律禁止使用”。',
14:'必改：reference_value_per_share 只适用于旧 dcf，dcf_fcf 使用 target_price/target_assumptions。可删：数值/单位搬运和比较器计算步骤。保留：贡献顺序不是唯一因果，融资/投资不混进经营现金桥。',
15:'可删：费用加总、重复扣减、计算小计由程序返回线索，不另增模型复核轮次。保留：not_checked 不等于通过、局部 needs_review、source/input_usage 与永续外推的经济含义。',
16:'可删重复：并入共享结论/关键依据/实质限制与用户输出要求，不在多个系统段重复。',
17:'可删：已实现的标准字体、数据导出等机械细节。保留：何时画图、图形选择、零基线、缺失与实际/预测、同尺度比较。A3 尚未合并，不能声称自绘图布局全部程序接管；新版仍提醒标签/色条/对比度。',
18:'可删长公式示例：保留当前前端 $$ 契约；这不是要改 Markdown 渲染器。',
19:'可合并：技能工具入口；数据库操作 JSON 留授权工具说明。保留：逐次用户授权和不可绕过，安全约束不归类为可删机械规则。',
20:'保留现状计入候选：资源版本是实现元数据，不是领域判断；可以将来移到审计，但本方案未把移除它计入收益。',
21:'保留按需技能入口，不把四个技能全文注入每次主请求。',
}
tool_reviews={
'request_database_operation':'保留：逐次授权、SQL 不自动隔离、被拒不绕过、主库不挂载。可删重复示例，但 analysis_changes 的文件结构必须留下。',
'read_project_skill':'保留：启用技能的按需读取和不能代替授权；压缩措辞。',
'search_web':'保留：原文优先、检索范围/as_of 的局限与 advanced 成本。',
'fetch_research_source':'可删：归档内部细节。保留：PDF 的 document_id 和准备/入库两种后续路径，资料不是授权。',
'read_research_source':'保留：按 next_offset 读完目标范围、PDF 改走页表、不能猜链接。分页参数不是程序替模型自动读完。',
'list_research_sources':'保留：发布日期与获取日期不同；简写功能。',
'run_financial_model':'必改：声称返回可直接传的 model_refs 与实际返回不符；run_analysis 只用于画图/成文会排斥合法定制计算。可删：单位换算、来源继承、自动导出清单的重复展开。保留：最小 dcf_fcf 输入形状、overrides/order、目标价不可识别目标假设、引用入口。',
'compare_financial_models':'保留：同类型与顺序归因语义；可删自动计算/保存细节。该调用实际返回 analysis.model_refs，不能与 run_financial_model 一概判错。',
'save_research_report':'保留：事实/假设与可定位 replacement；结构由按需 schema 给出。',
'get_research_report_schema':'保留接口入口，正文简写；不删除返回 schema。',
'list_research_artifacts':'保留依赖过期的经济后果；程序已比对依赖版本，不逐项重讲机制。',
'read_research_artifact':'保留读指定版本的完整信息；结构字段仍在 schema。',
'list_documents':'可删：项目绑定/状态字段的重复叙述；保留工具用途。',
'prepare_document_sources':'保留：准备原文不等于入库；提取实现细节可删。',
'inspect_document_routing':'保留：从样本判断元数据，不足补读；程序提供样本，不替模型决定归属。',
'set_document_profile':'保留：profile 是开放对象，内部 kind/entity/evidence 参数不在 schema，不能为瘦身删掉；公司/行业研究区别、未知元数据与证据要求保留。可删重复修订回执。',
'save_research_claims':'可删：合法/失败候选保存的内部实现过程。保留：entity 选择/证据、引语归属与空页语义；schema 保留 claim 字段。',
'get_research_ingestion_status':'可删重复工具序列；保留表页都需覆盖及完成≠语义核验。',
'query_research_records':'可删：程序默认保留历史/疑点的长说明，局部影响原则在共享段。保留：开放 filters 名称、OR/精确 metric、机构日期与历史版本区别、同日冲突和分页。',
'run_cleaning_script':'可删：沙箱内部装配机制。保留输入/输出路径、SDK、script_refs、坐标和隔离，避免省文字后猜接口。',
'get_cleaning_result':'保留：按需调用，不成为提交门槛；details、选表和 offset 语义不能靠猜。',
'commit_cleaning_result':'可删：原格取值和程序校验的重复解释。保留：局部修复、剩余表、reviews 只代表实际语义判断，不能默认成功。',
'get_data_catalog':'保留：动态 metric、query OR、分页范围及维度只对应本页；不要求重复目录确认。',
'get_processing_checkpoint':'可删：把持久状态当作额外检查步骤的展开。保留恢复入口与继续方法。',
'get_document_index':'保留：物理页码、含端点范围、两个 section 独立分页、导航搜索不是全文；删除重复演示。',
'query_financial_data':'保留：开放 filters 的全部字段、披露精确值/来源、动态 metric 与分页。疑点局部处理原则合并。',
'get_normalization_details':'保留：按实际疑点选表/筛选/分页；状态不是语义结论。可删重复叙述已完成/未完成条目结构。',
'get_document':'简写用途；完整返回原文定位与质量信息保留。',
'get_source_page':'保留物理页码从 1 开始和图片；不删证据读取能力。',
'get_source_table':'保留原格/坐标/公式与列表读取；压缩重复描述。',
'search_evidence':'保留：开放 filters、company/publisher 语义、as_of 未知日期、结构化数值工具和分页。',
'get_financial_metrics':'可删固定别名局限的重复说明。保留动态 ID/别名、未知非零与冲突局部核实。',
'financial_workpaper':'保留 K1/K3、默认期间与适用任务；计算与产物机械展开可删。K2/K4 仅有核心，不承诺暴露尚未交付的能力。',
'calculate_financial_metrics':'保留公式参数、单位差异和引用形状；不能把 ratio/百分比的选择当成可自动删除的机械规则。',
'run_analysis':'可删：多种单位别名、换算示例、附件/脚本自动导出细节，完整合同已挂载 /input/analysis_report.md。保留 report 最小形状、save_table、params/edits 的不同语义、隔离边界和自由 Python。金融专属段保留 model_refs/comparisons；prepared 不授予金融工具。',
'get_analysis_status':'保留异步结果入口；状态/表格结构由工具结果给出，避免重复说明。',
'get_artifact':'保留 rows 的 0 起点和 end 不包含，参数语义不能省略。',
'get_research_model_schema':'保留当前 schema 与合成示例非事实；模型参数完整 schema 继续按需返回。',
'process_documents':'可删程序保存进度/复用的重复说明；保留完整入库路径、表页均完成、routing_required 和 review_metrics。',
}
doc=['# B4 逐段审阅（待审，不修改运行时）','原文取自 current-context.json 的真实 Pi 会话快照；段号按非空行从 0 起。可删表示可从重复主提示中移除，必要接口入口仍保留。领域判断与安全授权不作为机械规则删除。每段全文保留，便于审阅实际删改。']
for profile in ('prepared','financial'):
    before=current['profiles'][profile];after=proposed['profiles'][profile]
    assert [t['name'] for t in before['tools']]==[t['name'] for t in after['tools']]
    assert [without_descriptions(t['parameters']) for t in before['tools']]==[without_descriptions(t['parameters']) for t in after['tools']]
    doc.append('## '+profile+' 系统文本')
    for i,p in enumerate(filter(None,before['system'].splitlines())):
        if profile=='prepared':review=('可删：重复项目/路径/工具过程；保留原文定位、自由编程、证据/假设与安全。新增共享答案绑定入口，避免基线不知道已有能力。' if i==0 else '保留 $$ 格式契约，缩短示例。' if i==1 else '保留 Pi 原生 cwd 上下文，不计作可删指导。')
        else:review=system_reviews.get(i,'保留启用技能目录；全文仍按需读取。' if i<26 else '保留原生项目规则/cwd 包装和用户项目内容，本方案不删用户规则。')
        doc+=['### 系统段 '+str(i)+' · '+str(count(p)[0])+' 字符 / 约 '+str(count(p)[1])+' token',q(p),review]
    doc.append('## '+profile+' 逐工具说明与 schema 描述')
    for old,new in zip(before['tools'],after['tools']):
        name=old['name'];a=m['profiles'][profile]['before']['tools'][name];b=m['profiles'][profile]['proposed']['tools'][name]
        ac,at=count(old['description']);bc,bt=count(new['description'])
        doc+=['### '+name,f'description：{ac} → {bc} 字符；粗估 {at} → {bt} token。完整参数 schema：{a["schema_full"]["chars"]} → {b["schema_full"]["chars"]} 字符，粗估 {a["schema_full"]["rough_tokens"]} → {b["schema_full"]["rough_tokens"]} token。',tool_reviews[name]]
        for i,p in enumerate(filter(None,old['description'].splitlines())):
            doc+=['原段 '+str(i)+'：',q(p)]
            if name=='run_analysis':
                decision=['保留隔离与 /input 文件入口。','保留研究预测≠披露的语义。','可删换算/文件输出的机械长例；保留最小 report/API 入口与自由计算。','可删快照/脚本导出的实现过程；保留 params 顺序与 edits 参数的区别。','金融专用模型引用与比较入口保留，删自动导出清单。','保留可编辑图与 helpers 入口；A3 未完成，不能删掉自由布局判断。','保留 /output 及无网络/密钥/主库边界。']
                doc.append(decision[min(i,len(decision)-1)])
        doc+=['建议 description 全文：',q(new['description'])]
        if not a['schema_description_fields']:doc.append('schema 没有 description 字段；type/enum/required/default/约束全部保持。')
        for oldfield,newfield in zip(a['schema_description_fields'],b['schema_description_fields']):
            assert oldfield['path']==newfield['path']
            field=oldfield['path'];review='保留接口语义并去重复；不删除字段、枚举或必填条件。'
            if 'source_model' in field or field in ('/properties/baseline','/properties/scenario'):review+=' 明确 artifact_id 默认最新，历史版本才固定 revision。'
            if 'parent_revision_id' in field:review+=' source_model + 相同 artifact_id 的模型更新确会自动继承父版本；其他保存路径仍需父版本，不能一概要求手填。'
            if 'review' in field or field.endswith('/force'):review+=' 保留来源定义复核与重洗的差别。'
            doc += [f'schema `{field}/description`：{oldfield["chars"]} → {newfield["chars"]} 字符；约 {oldfield["rough_tokens"]} → {newfield["rough_tokens"]} token。',q(oldfield['text']),review,'建议：'+newfield['text']]
doc+=['## 按需技能（不混入初始上下文降幅）','financial-modeling 与 model-review-update 需要把 run_financial_model 返回 analysis.model_refs 的表述改为用 id/revision_id 组成 model_refs；compare_financial_models 的该返回字段确实存在。model-review-update 的 delivery.delivered_to_user 应改 delivery.files。同一 artifact_id + source_model 的父版本自动继承确实存在，不列作错误。','技能中导出清单、单位搬运和重复机械勾稽可合并到工具合同；利润锚点、融资/投资现金分类、WACC 资本权重、终值与代理假设、可比选择、供应链证据/传导、资料归属和完整入库判断继续保留。plot_amounts 实际存在，不列作过时 API。A3/A5 合并后再核对其新增接口，不预先承诺。']
write('b4-paragraph-review-20261007.md','\n\n'.join(doc)+'\n')

lines=['# B4 瘦身方案（2026-10-07，待审，未部署）',
'金融组完整主模型可见上下文预计减少超过 30%，两组共享说明同步精简。工具数量、参数类型/枚举/必填结构、自由 Python、完整入库与安全授权边界保持；不改 Pi 循环。本轮只测量和生成候选文档，生产系统提示、领域指导、工具说明及技能均未替换。',
'## 测量口径',
'使用 scripts/measure-b4-context.ts 在隔离空默认项目中实际创建 Pi 原生会话，读取 session.systemPrompt 和 agent.state.tools，没有调用 prompt() 或付费模型。基线指与金融组拥有可比准备资料的 prepared 配置（13 工具），金融组 39 工具；不是 raw-only 配置。snapshot 中包括原生项目规则、启用技能目录、资源版本和 cwd。自定义项目规则/路径/技能集合会使长度变化，这组数字不是所有项目的固定常数。',
'字符为 Unicode 码点；粗估 token = ceil(ASCII 字符/4 + 非 ASCII 字符)。本轮未使用 tokenizer，也未安装新依赖。此估算不是实际 tokenizer 或账单；不同 tokenizer 与语言混合可能产生较大误差，未校准误差区间。跨中英重写尤其应以部署后的实际 usage 再核对。两种总量同时报告：说明文字=系统+工具 description+schema 的 description；完整上下文=系统+含完整 schema 的紧凑 JSON 工具列表，不包含传输封装开销、用户问题、历史与工具结果。领域指导已在系统中，不能重复相加。',
'## 前后测算',
'| 配置/部分 | 当前字符 | 候选字符 | 当前粗估 token | 候选粗估 token |\n|---|---:|---:|---:|---:|']
labels={'system':'完整系统（含领域/项目）','tool_descriptions':'工具 description','schema_descriptions':'schema description','instruction_text':'说明文字合计','full_visible_context':'完整上下文（含完整 schema）'}
for profile,pm in m['profiles'].items():
    for key,label in labels.items():
        a,b=pm['before'][key],pm['proposed'][key]
        lines[-1]+=f'\n| {profile} · {label} | {a["chars"]:,} | {b["chars"]:,} | {a["rough_tokens"]:,} | {b["rough_tokens"]:,} |'
for profile,pm in m['profiles'].items():
    a=pm['reductions']['instruction_text'];b=pm['reductions']['full_visible_context']
    lines.append(f'{profile}：说明文字字符减少 {a["chars"]:.1%}，粗估 token 减少 {a["rough_tokens"]:.1%}；完整上下文字符减少 {b["chars"]:.1%}，粗估 token 减少 {b["rough_tokens"]:.1%}。')
oldparas=list(filter(None,current['profiles']['financial']['system'].splitlines()))
domain='\n'.join(oldparas[11:18]);newdomain=(ROOT/'design/b4-financial-guidance-proposed-20261007.md').read_text(encoding='utf8').split('\n\n',1)[1].strip()
lines += [f'单列 FINANCE_TASK_GUIDANCE 的正文：当前 {count(domain)[0]} 字符 / 约 {count(domain)[1]} token；候选金融指导 {count(newdomain)[0]} 字符 / 约 {count(newdomain)[1]} token。新版同时吸收原 runs.ts 中必要金融语义，因此此行只作定位，正式收益以上方完整系统计量。',
'辅助路由器单独请求，系统文本 '+str(m['outside_main_request']['router_prompt']['chars'])+' 字符 / 约 '+str(m['outside_main_request']['router_prompt']['rough_tokens'])+' token；保持不变，不计成每次主请求重复负担。按需技能只有读取后才进入会话，初始仅目录，全文现状如下；本方案不虚报这些技能的缩减收益。',
'| 按需技能全文（含 frontmatter） | 字符 | 粗估 token |\n|---|---:|---:|']
for s in m['outside_main_request']['on_demand_skills_including_frontmatter']:lines[-1]+=f'\n| {s["path"]} | {s["chars"]:,} | {s["rough_tokens"]:,} |'
lines += ['## 删改依据',
'数值搬运、单位规范化、附件清单、保存脚本/来源、精确比较、断点进度及相同规则的多次重述，已有程序完成，可从主提示中删去展开。保留短入口和最小有效参数示例，完整方法合同仍通过工具 schema 或 /input/analysis_report.md 按需获取。开放对象 profile/filters 的内部字段不在 schema 中，仍保留其参数定义；不为缩短说明让模型猜参数。',
'口径与经济分类、证据归属、时间可得性、未知/疑点的影响、利润与现金、目标价可识别性、终值外推和代理假设仍需判断。新版采用任务路径连接这些判断，不把它们堆成逐项审批清单。自定义图尚无已合并的 A3 保证，保留必要布局判断。安全授权即使程序执行也保留其边界。',
'当前与实现不一致的内容必须改：①“必须先查询”应允许直接计算用户给定输入；②“所有 DCF 是财年末价值”改按具体估值日/约定；③reference_value_per_share 不能泛用到 dcf_fcf，其字段为 target_price/target_assumptions；④run_financial_model 不返回 analysis.model_refs，应由 id/revision_id 组成，compare_financial_models 则有该字段；⑤delivery.delivered_to_user 改 delivery.files；⑥run_analysis 不能限定只画图/成文，定制模型仍可用；⑦起手路径从笼统 report 改 statement_analysis/dcf_fcf，更新区分情景与修复。父版本自动继承和 plot_amounts 已核实存在，不误列为过时内容。',
'证据位置：server/runs.ts、server/financial-guidance.ts、server/research-artifacts.ts（model/deliver/compare）、service/dcf_fcf.py、service/model_comparison.py，以及 skills/financial-modeling 和 skills/model-review-update。逐段原文、每个工具和每个 schema description 的字符/token 及处理理由见 [逐段审阅](b4-paragraph-review-20261007.md)。',
'## 新版金融指导全文',newdomain,
'## 审核后才执行',
'本方案审核后，再在 A3/A5 合并完成的实际代码上复核候选，实施共享系统段、FINANCE_TASK_GUIDANCE、各 description 和两个技能的陈旧字段修正；若 N2 交付改变工具集或说明，重新拍快照并重算，不能沿用本次数字冒充最终状态。候选的全部系统/工具/schema 文本已写入 proposed-context.json，可逐字审阅；当前原文另存，不覆盖。',
'实施后的确定性验收应检查：工具/schema 结构未缩减；相同共享能力在基线可发现；K1/B2/params/edits/绑定入口可用；按需 schema/文档不会产生额外猜参。真实效果由 N1 的正式对照验证，成本与入库分列；静态缩短不能证明金融质量、调用次数或账单已经更优。本轮不做新的付费冒烟。',
'数据与复现： [原始快照](../docs/evidence/b4-plan-20261007/current-context.json)、[候选全文](../docs/evidence/b4-plan-20261007/proposed-context.json)、[逐工具测量](../docs/evidence/b4-plan-20261007/measurements.json)。生成脚本为 scripts/build-b4-proposal.py 与 scripts/document-b4-review.py；二者只写 design 与 docs/evidence。']
write('b4-slimming-plan-20261007.md','\n\n'.join(lines)+'\n')
print('B4 review written; both tool lists and all non-description schema fields unchanged.')

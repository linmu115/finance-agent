"""Prepare proposed X6/X7 from public originals; no ingestion or model calls."""
import json
from decimal import Decimal as D
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/evaluation/blind-eval-analyst-alignment-20261008'
BENCH=ROOT/'benchmark/blind-eval'
def read(p):return json.loads(p.read_text('utf8'))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def pct(a,b):return (D(a)-D(b))/abs(D(b))*100
refs=read(ROOT/'data/evaluation/blind-eval-preparation-20261007/reference-drafts.json')
ytd={'revenue':['88732934445.43','97090826912.59'],'parent_profit':['10868480345.34','9380094922.17'],'cfo':['13869612283.42','11708284111.40']}
q3={'revenue':'29037177483.84','parent_profit':'3337346216.72','cfo':'8544068622.02'}
q4_disclosed={'revenue':'26660376531.26','parent_profit':'-2415620352.16','cfo':'7870128109.96'}
q6={}
for metric in ytd:
 annual=refs['X3']['raw'][metric];v=[D(annual[i])-D(ytd[metric][i]) for i in [0,1]]
 assert v[0]==D(q4_disclosed[metric])
 q6[metric]={'annual_2024_2023_CNY':annual,'ytd9m_2024_2023_CNY':ytd[metric],'Q4_2024_2023_CNY':[str(z) for z in v],'Q3_2024_CNY':q3[metric],'Q4_YoY_percent':str(pct(*v)),'Q4_QoQ_percent':str(pct(v[0],q3[metric])),'Q4_check_residual_CNY':'0','sources':{'annual_pdf_page':7,'ytd_pdf_page':{'revenue':7,'parent_profit':8,'cfo':9}[metric],'Q3_and_Q4_check_annual_pdf_page':8}}
q6['adjusted_parent_profit']={'annual_2024_CNY':'6011274945.92','ytd9m_2024_CNY':'8508870024.72','Q4_2024_CNY':str(D('6011274945.92')-D('8508870024.72')),'Q3_2024_CNY':'3184409980.19','QoQ_percent':str(pct('-2497595078.80','3184409980.19')),'Q4_2023_CNY':None,'reason':'未用披露的累计同比四舍五入百分比反推精确2023扣非基数；草案仅要求该指标2024环比。','sources':{'annual_pdf_page':7,'ytd_pdf_page':1,'Q3_Q4_annual_pdf_page':8}}
hraw={
'revenue':['285981225203.93','274204520847.97','261427783050.10'],
'parent_profit':['18741120122.93','16596615045.87','16596615045.87'],
'adjusted_parent_profit':['17804732809.63','15824164161.43','15824164161.43'],
'cfo':['26543081911.96','26535780568.36','25262376228.30'],
'parent_equity':['111366118999.17','101265984771.17','103514153535.04'],
'assets':['290113822824.61','261067684897.49','253379859977.97']}
hcalc={k:{'values_CNY_2024_2023adjusted_2023original':v,'adjustment_2023_CNY':str(D(v[1])-D(v[2])),'growth_using_adjusted_percent':str(pct(v[0],v[1])),'growth_using_original_percent':str(pct(v[0],v[2])),'growth_difference_pp':str(pct(v[0],v[2])-pct(v[0],v[1])),'pdf_page':10} for k,v in hraw.items()}
revenue=D(hraw['revenue'][1]);cost=D('198838470796.47');sales=D('32726735817.73');shift=D('8328087511.15')
hcalc['warranty_reclassification_2023']={'cost_adjustment_CNY':str(shift),'sales_expense_adjustment_CNY':str(-shift),'gross_margin_adjustment_pp':str(-shift/revenue*100),'sales_expense_ratio_adjustment_pp':str(-shift/revenue*100),'reported_adjusted_gross_margin_percent':str((revenue-cost)/revenue*100),'same_scope_before_this_policy_gross_margin_percent':str((revenue-(cost-shift))/revenue*100),'reported_adjusted_sales_ratio_percent':str(sales/revenue*100),'same_scope_before_this_policy_sales_ratio_percent':str((sales+shift)/revenue*100),'operating_profit_effect_CNY':'0','note':'只隔离此项营业成本/销售费用重分类，收入/合并范围及其他项不变；逆推旧列报不是原2023已发布全口径。','pdf_pages':[94,121,122,163]}
hcalc['weighted_parent_ROE']={'reported_percent_2024':'17.70','2023_adjusted':'17.24','2023_original':'16.85','2023_adjustment_pp':'0.39','2024_change_adjusted_pp':'0.46','2024_change_original_pp':'0.85','pdf_page':11}
hcalc['nonrecurring']={'net_parent_contribution_2024_2023_CNY':['936387313.30','772450884.44'],'government_grants_2024_2023_CNY':['1324181478.11','1093584406.07'],'note':'政府补助连续两期出现是持续性分析线索；不自动重分类为经常性。政府补助为税/少数股东前金额，不等于净归母非经常贡献。','pdf_page':12}
common='请用人民币百万元展示金额，比例与百分点分开；先给结论，再给数据、原文页码和局限，清楚区分事实、推论和观点。交付清晰图表、Markdown/PDF报告、Excel/CSV底稿及可复算计算文件；估值或投资判断如有，说明假设、风险和适用范围。'
p6='我想看伊利2024年第四季度到底发生了什么，不想把前三季度累计数当成单季。请结合2024年年报和三季报，先识别报表口径，用全年减前三季度推导2024和2023第四季度的营业收入、归母净利润、经营现金流，算2024年第四季度的同比和相对第三季度的环比，并用年报分季度数据核对。另列2024年第四季度扣非归母净利润及环比。解释单季利润与现金表现给全年判断带来的变化，哪些原因有报告支持、哪些只能作为推论；说明哪些指标不能简单相减。'+common
p7='海尔2024年年报里2023年数据有调整前、调整后两列。我想知道，选错列会把增长和盈利判断带偏多少。请只用这份年报，找出重述和会计政策变化的原因，列出主要指标的调整额，分别按两列计算2024年收入、归母利润、经营现金流的增速，以及归母净利率和披露ROE的变化。再单独量化质保费用重分类对毛利率、销售费用率和营业利润的影响；不能把其他并表变化混进这项影响。结合非经常性损益表，说明连续出现的项目对盈利判断有什么启示，不要直接改判其性质。最后指出现有披露能解释哪些差异、哪些还不能精确拆开。'+common
align=read(OUT/'requirement-alignment.json')
def req(c,p,scope=''):return {'coverage':c,'must_mention':p,'scope':scope}
c=req('direct',['按题面交付图表、Markdown/PDF报告、Excel/CSV及可复算文件；所有单位一致。','保存来源列、推导公式、输入参数和版本；事实/推论/观点可辨；估值时说明假设风险范围。'])
tasks=[{'id':'X6','status':'draft_pending_Claude','split':'extension','type':'quarter_algebra','materials':['yili_2024','yili_q3_2024'],'prompt':p6,'reference':{'status':'draft_numeric_checked_not_frozen','values':q6,'task_requirements':{'R1':req('direct',['季报本报告期是7–9月，年初至报告期末是1–9月；年报p7年度比较列和p8单季表分开。','三季报未经审计、年报经审计；比较基础有冲突时不得静默相减。']), 'R2':req('direct',['每个Q4保留全年与9个月两端来源；Q4同比/环比基期不同。','Q3 CFO来自年报分季度表，不把三季报p1不适用当0；不以累计同比舍入值反推精确基数。','EPS/加权ROE不是可加总流量，不能简单全年减累计；余额指标也不能当单季流量。']), 'R3':req('supporting',['Q4亏损与正CFO并存要解释，原因证据不足不得把年内原因精确分摊到季度。'],'侧重季度解释，不要求另造完整季度利润桥。'), 'R4':req('supporting',['保留营业收入与营业总收入之别、归母与扣非差；先查重述再做跨报告减法，不无据报会计调整。']), 'R5':req('direct',['Q4归母/扣非亏损而CFO正；年度总量不能掩盖季度异动，负利润覆盖比不能直解盈利质量提高。']), 'C':c},'unresolved':['季度原因与减值等驱动的页码证据仍待最终参考审定，不将年报全年影响量自动分配到Q4。','N3年报完整入库与新三季报入库均未准备就绪；不读取旧库事实替代正式材料。'],'tolerance':'源金额0.01元；百万元展示2位允许0.005百万元；百分比2位允许0.005个百分点。'}},
{'id':'X7','status':'draft_pending_Claude','split':'extension','type':'restatement','materials':['haier_2024'],'prompt':p7,'reference':{'status':'draft_numeric_checked_not_frozen','values':hcalc,'task_requirements':{'R1':req('direct',['CAS版2024年报p10/11的2023调整后/前不可交换；p12季度重述说明、p94/163政策、p213/214并表说明分开。']), 'R2':req('direct',['调整额=调整后−调整前；选错基数的增速影响用百分点。','净利率按同一收入/利润基础；ROE用报告已披露数比较，不拿简单平均ROE冒充加权ROE。']), 'R3':req('direct',['报告变化要区分业务表现、并表范围和列报规则；没有逐项披露的总调整原因保留未分解部分。']), 'R4':req('direct',['物流同一控制合并重述与质保费用由销售费用重分类到成本是不同事项。','隔离质保重分类时毛利率与销售费用率同降约3.03718个百分点，营业利润不变；不能用这项解释收入/CFO/权益调整。','准经常性观察以两期政府补助为线索，保留法定非经常归类、税和少数股东影响，不自动改判。']), 'R5':req('supporting',['先排除比较基准/列报变化造成的伪异常，调整后CFO增长接近0而非原列口径的5%左右。'],'重点口径造成的表观信号，不等同完整异常雷达。'), 'C':c},'unresolved':['合并范围变更与其他因素对各项总调整的逐项拆分并未全部核实；不能用被合并方原收入直接冒充集团抵销后收入增量。','已读CAS版原文；不扩大为国际准则版对照，不额外入2023年报。'],'tolerance':'源金额0.01元；百万元/百分比两位采用最后显示位半单位，披露ROE保留两位。'}}]
# Additional ratio checks for X7, same scope and column identities.
p23=D(hraw['parent_profit'][1]);p24=D(hraw['parent_profit'][0])
hcalc['parent_margin_percent']={'2024':str(p24/D(hraw['revenue'][0])*100),'2023_adjusted':str(p23/D(hraw['revenue'][1])*100),'2023_original':str(p23/D(hraw['revenue'][2])*100)}
manifest=read(OUT/'candidate-exact-document-matches.json')
urls={'yili_q3':'https://static.cninfo.com.cn/finalpage/2024-10-31/1221571075.PDF','haier_2024':'https://static.cninfo.com.cn/finalpage/2025-03-28/1222926246.PDF','yili_2024':'https://static.cninfo.com.cn/finalpage/2025-04-30/1223421123.PDF'}
for m in manifest:
 doc=fitz.open(ROOT/m['local_file']);m['source_url']=urls[m['id']];m['text_characters']=sum(len(p.get_text()) for p in doc);m['model_ingestion_started']=False;m['estimated_model_usage']=None;m['estimated_billed_cost']=None
 m['preparation_status']='annual_reingestion_owned_by_N3_paused' if m['id']=='yili_2024' else 'not_ingested_pending_approval'
 m['estimate_note']='完整文档页数为工作量基数；新版本模型请求/token尚无此材料实测，保持未知，不把原文字符数冒充模型累计输入。'
dump(OUT/'new-task-drafts.json',{'status':'draft_pending_Claude','tasks':tasks})
dump(OUT/'new-material-plan.json',{'materials':manifest,'new_scope_pages':262,'shared_already_planned_annual_pages':270,'proposed_projects':{'yili_q3':'374beac2-a970-4972-b210-e91018bbd6e6','haier_2024':'待审：单独同业/口径评测项目，两组共享；可与未来X2复用'},'policy':'只准备本地PDF和参考；完整入库须另行批准，不能截页替代。伊利年报不计为N1新增资料，也不迁移旧库。','cost_context':{'latest_broker_preparation_known_input':13093305,'latest_broker_preparation_known_output':49201,'pages':19,'unknown_usage_requests':6,'use':'这是第二轮改进上线前的旧流程且语义未通过，不作为新材料预算或成本改善证明；实际CPA费率未知。'}})
dump(OUT/'source-inspection.json',{'method':'PyMuPDF extraction plus actual full-page visual inspection','inspected_pages':{'Yili_2024_Q3':[1,7,8,9,15],'Yili_2024_Annual':[7,8],'Haier_2024_Annual':[10,11,12,94,122,137,213,214]},'limits':'Draft source/numeric preparation only; no complete financial ingestion, no model analysis trial; table semantic counts unknown until standard parser preparation.'})
print(json.dumps({'X6':q6,'X7_growth':{k:v for k,v in hcalc.items() if k in ['revenue','cfo','warranty_reclassification_2023','parent_margin_percent']},'materials':[{k:m[k] for k in ['id','pages','text_characters','bytes']} for m in manifest]},ensure_ascii=False))

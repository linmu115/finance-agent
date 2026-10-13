"""Reproduce N1's independently page-checked phase-one gold (offline, no model)."""
from decimal import Decimal as D
import hashlib,json
from pathlib import Path
from blind import ROOT,dump,read
HERE=ROOT/'benchmark/blind-eval'
E=ROOT/'data/evaluation/blind-eval-f1-preparation-20261008'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def value(v):return str(v)
def pct(a,b):return (D(a)/D(b)-1)*100
sources={
 'guosen':('Guosen_Yili_20250716.pdf',[1,29,30,31,36],'585db15e768043b7b465d1af7c690e90'),
 'annual':('../../samples/native-pdf/伊利股份2024年年度报告.pdf',[7,8,91,92],'d84573bf6b584e7e874faa4c6adf454a'),
 'q3':('../blind-eval-formal-plan-20261008/Yili_Q3_ingested_source.pdf',[1,7,8,9],'4c3e9228d37e49fca132e0e79377b04d'),
 'may':('../blind-eval-preparation-20261007/sources/Everbright_FoodBeverage_20240512.pdf',[8],'5a64cb3df8a54728a8562add6840881c'),
 'huatai':('../blind-eval-preparation-20261007/sources/Huatai_Yili_20241030.pdf',[1,3],'952ecfa574aa4ea8b849bea4b1c6020c'),
 'nov':('../blind-eval-preparation-20261007/sources/Everbright_Yili_20241104.pdf',[1,2],'47d2d1bad23d4318bdfa197bcad17349'),
}
manifest={}
for key,(location,pages,docid) in sources.items():
 p=ROOT/'samples/native-pdf/伊利股份2024年年度报告.pdf' if key=='annual' else (E/location).resolve()
 manifest[key]={'file':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p),'document_id':docid,'visually_verified_pdf_pages':pages,'page_numbering':'1-based physical PDF pages; annual printed pages are PDF minus 4','page_evidence':[{'text':f'source-pages/{key}-p{n}.txt','text_sha256':sha(E/f'source-pages/{key}-p{n}.txt'),'image':f'source-pages/{key}-p{n}.png','image_sha256':sha(E/f'source-pages/{key}-p{n}.png')} for n in pages]}
old=read(ROOT/'data/evaluation/blind-eval-preparation-20261007/reference-drafts.json')
new=read(ROOT/'data/evaluation/blind-eval-analyst-alignment-20261008/new-task-drafts.json')
gold={'version':'phase1-reference-v1-20261008','status':'frozen_reference_not_participant_score','reviewer':'N1 independent visual source review','rubric_version':'analyst-requirements-v2-20261008','evidence_root':'data/evaluation/blind-eval-f1-preparation-20261008','sources':manifest,'tasks':{}}
checks=[]
def add(task,key,v,unit,pages,tol='0.005',role='required_numeric',formula=None):
 checks.append({'key':task+'.'+key,'task':task,'expected':{'value':str(v),'unit':unit,'absolute_tolerance':str(tol)},'source_pages':pages,'role':role,'formula':formula,'missing_policy':'report_missing_for_review_not_automatic_material_defect'})
x4={'task_requirements':old['X4']['task_requirements'],'facts':{},'must_mention':[
 '2025–2027收入、归母、EPS跨p1/p29/p36相符；增速用未舍入基数，附表整数百分比与正文一位小数不构成错误。',
 'p29股本6366百万股；归母/股数可支持两位EPS。p1脚注按最新总股本摊薄；不能倒推一套未披露DCF参数。',
 '2025 PE目标19–20倍×显示EPS1.78=33.82–35.60元，报告33.8–35.6属显示精度；目标市值用11309×19/20=2148.71–2261.8亿元。',
 'p1收盘27.38、p30资本成本表27.88、p31可比表27.77不一致；日期/估值基准未说明，不能凭空解释为同一天。p31的15.60倍与27.77/1.78相符；p1/p36的15.7不能用27.38解释为舍入。',
 'DCF基准32.69元（WACC7.9%、g1.8%）；31.51–33.95敏感范围与PE33.8–35.6是不同方法。31.5–34.0与31.51–33.95可由显示精度解释。',
 'p30先写可预测期2025–2026，再写2024–2026且举2025–2027数据，属确切文字不一致；不能据此虚构实际DCF逐年折现序列。',
 '事实是报告披露的数字；供需拐点、减值缩小、渠道和高附加值产品带动利润是机构判断；分红/资本开支逻辑与需求、竞争、食品安全、原料成本风险并列。'],
 'additional_valid_observations':['p30管理费用/收入3.5%与p29/36的4368/119338≈3.660%不符，报告没有给出调节口径；指出可加深评价，但不是题面额外硬要求。','表6上下浮动5%未指明究竟哪个输入，收入/利润结果并非简单±5%；只能指出解释不足，不能断言模型采用了错误敏感参数。'],
 'limitations':['EBIT Margin为报告所列，不能默认等于营业利润率；缺少其精确定义时保留差异，不虚构调整项。','不引入2025年7月16日之后实际表现，不将所有不一致升格为投资结论必然错误。']}
rev=[D(x) for x in ['115780','119338','122498','125438']];profit=[D(x) for x in ['8453','11309','12222','13152']]
for i,year in enumerate([2025,2026,2027],1):
 eps=[None,'1.78','1.92','2.07'][i]
 x4['facts'][str(year)]={'revenue_CNY_million':str(rev[i]),'parent_profit_CNY_million':str(profit[i]),'EPS_CNY_per_share':eps,'revenue_growth_percent':str(pct(rev[i],rev[i-1])),'parent_profit_growth_percent':str(pct(profit[i],profit[i-1])),'EPS_from_displayed_profit_shares':str(profit[i]/6366)}
 for metric,v,unit,tol in [('revenue',rev[i],'CNY_million','0.5'),('parent_profit',profit[i],'CNY_million','0.5'),('EPS',eps,'CNY/share','0.005'),('revenue_growth',pct(rev[i],rev[i-1]),'%','0.05'),('parent_profit_growth',pct(profit[i],profit[i-1]),'%','0.05')]:add('X4',f'{metric}_{year}',v,unit,{'guosen':[1,29,36]},tol)
for key,v,unit,tol in [('PE_target_low',19,'ratio','0'),('PE_target_high',20,'ratio','0'),('target_price_low','33.82','CNY/share','0.05'),('target_price_high','35.60','CNY/share','0.05'),('DCF_base','32.69','CNY/share','0.005'),('DCF_range_low','31.51','CNY/share','0.05'),('DCF_range_high','33.95','CNY/share','0.05'),('spot_p1','27.38','CNY/share','0.005'),('spot_p30','27.88','CNY/share','0.005'),('spot_p31','27.77','CNY/share','0.005')]:add('X4',key,v,unit,{'guosen':[1,30,31]},tol)
gold['tasks']['X4']=x4
x5={'task_requirements':old['X5']['task_requirements'],'cutoff':'2024-12-31','selection':[{'institution':'华泰','published_at':'2024-10-30','source':'huatai'},{'institution':'光大','published_at':'2024-11-04','source':'nov'}],'revision_only':['may'],'excluded_from_ex_ante':['guosen'],'must_mention':[
 '截止日内各机构最近报告各一份；光大五月只看修正历史；两个机构不是市场一致预期。',
 '年报2024营业收入115393.31097669百万元，营业总收入115779.55464930百万元，两者不可静默替换。研报2023历史收入126179百万元接近年报营业总收入，提示定义疑点，但数值接近不证明同口径。',
 '华泰12235和光大12019百万元可定位归母；五月130.63亿元只写净利润，利润归属不明，不能强行算同口径归母修正额。',
 '华泰p1 EPS称最新摊薄，p3同值还称基本EPS；光大用预测总股本，实际年报基本/稀释均1.33不证明分母与预测相同。',
 '六项算术差额可单列带口径限制的参照，不能无条件称严格同口径预测误差，更不能据此排名预测准确性；若补出原文口径证据，可明确条件后比较，不能因库字段未知而断言原文绝无信息。',
 '光大11月称上调归母+3.64%，并提下半年渠道促销费用减少及信用减值转回；此百分比对应未给定的前次预测，不是五月到十一月。五月EPS2.05到十一月1.89是显示数值下修，股本基础仍需说明。',
 '国信2025-07-16可作事后解释、2025–2027机构预测或口径核对；不能纳入2024-12-31事前预期或替代2024年报实际值。',
 '原页明确华泰p3的8985是经营活动现金流，净利润12776，归母12235；不能使用旧错位事实。光大p2净利润12069和归母12019也要分开。'],
 'source_scope_evidence':['华泰p3、光大p2利润表同时列少数股东损益和归母，支持识别归母预测；不是通过单看旧库标签判断。','各研报未明确CAS及收入口径调节，六项参照维持有限可比；EPS同值不消除基础差异。'],
 'reference_gaps':[], 'strict_same_basis_ranking':None}
actual={'revenue':D('115393.31097669'),'parent_profit':D('8452.85999318'),'EPS':D('1.33')}
for inst,forecasts in [('huatai',['118007','12235','1.92']),('nov',['118170','12019','1.89'])]:
 for (metric,av),fv in zip(actual.items(),forecasts):
  fv=D(fv);unit='CNY/share' if metric=='EPS' else 'CNY_million';delta=av-fv;rate=delta/abs(fv)*100
  x5['reference_gaps'].append({'institution':inst,'metric':metric,'forecast':str(fv),'actual':str(av),'delta_actual_minus_forecast':str(delta),'deviation_percent':str(rate),'unit':unit,'same_basis_status':'conditional_reference_only'})
  add('X5',f'{inst}_{metric}_forecast',fv,unit,{inst:[1]},'0.005' if metric=='EPS' else '0.5')
  add('X5',f'{inst}_{metric}_delta',delta,unit,{inst:[1],'annual':[91,92]},role='conditional_if_reported')
  add('X5',f'{inst}_{metric}_deviation',rate,'%',{inst:[1],'annual':[91,92]},role='conditional_if_reported')
for metric,av in actual.items():add('X5',metric+'_actual',av,'CNY/share' if metric=='EPS' else 'CNY_million',{'annual':[91,92]})
for key,v,unit in [('may_profit_unspecified',13063,'CNY_million'),('may_EPS','2.05','CNY/share'),('may_to_nov_EPS_delta','-0.16','CNY/share')]:add('X5',key,v,unit,{'may':[8],'nov':[1]},role='conditional_if_reported' if 'delta' in key else 'required_numeric')
x5['revision']={'may_net_profit_CNY_million':'13063','may_profit_attribution':None,'may_EPS':'2.05','nov_parent_profit_CNY_million':'12019','nov_EPS':'1.89','same_basis_profit_revision':None,'raw_EPS_delta':'-0.16','nov_stated_revision_percent':'3.64','nov_revision_predecessor':'not_identified_in_supplied_May_report'}
x5['task_requirements']['R1']['must_mention'][1]='国信2025-07-16晚于已批准截止日2024-12-31，不能当事前预期或代填年报实际。'
x5['task_requirements']['R2']['must_mention'][1]='五月EPS2.05至十一月1.89显示差-0.16元/股；五月净利润归属未知，同口径归母修正额留空。若列13063至12019的算术差，必须标为跨归属未齐参照，不作为必须给出的金标。'
gold['tasks']['X5']=x5
x6=next(t['reference'] for t in new['tasks'] if t['id']=='X6')
x6={**x6,'status':'frozen_independent_source_verified','unresolved':[]}
for metric,data in x6['values'].items():
 if metric=='adjusted_parent_profit':
  for name,v in [('Q4_2024',data['Q4_2024_CNY']),('Q3_2024',data['Q3_2024_CNY'])]:add('X6',metric+'_'+name,D(v)/1000000,'CNY_million',{'annual':[7,8],'q3':[1]})
  add('X6',metric+'_QoQ',data['QoQ_percent'],'%',{'annual':[7,8],'q3':[1]})
  continue
 for name,v in [('Q4_2024',data['Q4_2024_2023_CNY'][0]),('Q4_2023',data['Q4_2024_2023_CNY'][1]),('Q3_2024',data['Q3_2024_CNY'])]:add('X6',metric+'_'+name,D(v)/1000000,'CNY_million',{'annual':[7,8],'q3':[7,8,9]})
 for name,v in [('YoY',data['Q4_YoY_percent']),('QoQ',data['Q4_QoQ_percent'])]:add('X6',metric+'_'+name,v,'%',{'annual':[7,8],'q3':[7,8,9]})
 # Independent Decimal recomputation, not acceptance of the old derived gold.
 a,b=map(D,data['annual_2024_2023_CNY']);c,d=map(D,data['ytd9m_2024_2023_CNY']);q4=a-c;q4old=b-d
 assert [q4,q4old]==list(map(D,data['Q4_2024_2023_CNY']))
 assert abs(pct(q4,q4old)-D(data['Q4_YoY_percent']))<D('1e-20')
 assert abs(pct(q4,data['Q3_2024_CNY'])-D(data['Q4_QoQ_percent']))<D('1e-20')
x6['quarter_driver_evidence']={
 'asset_impairment_signed_CNY':{'FY':'-4675845733.44','9m':'-686188008.08','Q4':str(D('-4675845733.44')-D('-686188008.08')),'sources':{'annual':91,'q3':7}},
 'investment_income_CNY':{'FY':'2417330849.26','9m':'2659345939.07','Q4':str(D('2417330849.26')-D('2659345939.07')),'sources':{'annual':91,'q3':7}},
 'conclusion':'Q4资产减值损失约3989.65772536百万元，年报减9个月得到，并非把全年减值武断分摊；投资收益Q4约-242.01508981百万元。均为税前合并损益项目，不能直接等同归母净利降幅；无足够信息精确拆税/少数股东/具体资产的季度影响。',
 'cash_limit':'亏损与正CFO并存，减值为非现金因素线索；未完成季度现金桥时不声称全部CFO由减值或营运资金造成。'}
x6['must_mention']=['用全年减前三季度求两年Q4；年报2024季度表校验残差0；2023Q4由比较列推导，不伪称年报另有2023季度表。','Q4归母及扣非亏损、CFO仍正且同比增/环比降，全年正利润掩盖季度转亏。','资产减值Q4有同口径流量减法证据；具体原因和归母归因仍分清事实/推论/未知。','EPS、加权ROE不能直接相减；余额差是变化量而非期间利润；三季报本报告期CFO不适用不是0。']
add('X6','Q4_asset_impairment_signed',D(x6['quarter_driver_evidence']['asset_impairment_signed_CNY']['Q4'])/1000000,'CNY_million',{'annual':[91],'q3':[7]},role='conditional_if_reported')
gold['tasks']['X6']=x6
selectors={'version':gold['version'],'reference':'reference-phase1.json','binding_policy':'One gold key -> all still-delivered occurrences. Locate cells without changing expected values. Every file/row/path and unit must have submitted evidence. Ambiguous or unbound values remain unknown; no guessed unit or numeric-only semantic pass. Prose/figures/PDF-only answers remain independent-review scope.','checks':checks}
dump(HERE/'reference-phase1.json',gold);dump(HERE/'selectors-phase1.json',selectors)
dump(E/'reference-freeze.json',{'version':gold['version'],'source_pages_visually_checked':sum(len(s['visually_verified_pdf_pages']) for s in manifest.values()),'files':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [HERE/'reference-phase1.json',HERE/'selectors-phase1.json',HERE/'reference-development.json',HERE/'rubric.md']},'formal_participant_runs':0,'product_data_modified':False})
print(json.dumps({'sources':len(manifest),'pages':18,'numeric_checks':len(checks),'paid_requests':0}))

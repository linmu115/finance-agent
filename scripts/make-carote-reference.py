"""Independent grading worksheet; never mounted to an evaluated agent.

Transcribed from publisher PDFs, pages visually checked before any agent run.
This calculator deliberately does not import the application's model library.
"""
from decimal import Decimal as D, localcontext
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'data/evaluation/pi-finance-generalization-20261006/judge'
root.mkdir(parents=True,exist_ok=True)
facts={
 '2025H1':{'revenue':'836.925','gross_profit':'281.594','operating_profit':'96.000','consolidated_net_profit':'102.791','parent_net_profit':'102.785','net_finance_income':'25.533','operating_generated_cash':'16.776','bank_interest_received':'5.723','tax_paid':'41.175','cfo':'-18.676'},
 '2024H1':{'revenue':'955.192','gross_profit':'395.243','operating_profit':'193.422','consolidated_net_profit':'164.084','parent_net_profit':'164.096','net_finance_income':'3.425','operating_generated_cash':'130.795','bank_interest_received':'1.216','tax_paid':'42.147','cfo':'89.864'}}
with localcontext() as ctx:
 ctx.prec=50
 for row in facts.values():
  row['gross_margin_percent']=str(D(row['gross_profit'])/D(row['revenue'])*100)
  row['cash_to_net_profit']=str(D(row['cfo'])/D(row['consolidated_net_profit']))
  assert D(row['operating_generated_cash'])+D(row['bank_interest_received'])-D(row['tax_paid'])==D(row['cfo'])
 flows=[D(v) for v in ('288','512','591','594','626')]
 def calc(wacc,fcfs,g=D('.02')):
  pv=sum(v/(1+wacc)**t for t,v in enumerate(fcfs,1))
  tv=fcfs[-1]*(1+g)/(wacc-g)/(1+wacc)**len(fcfs)
  ev=pv+tv;equity=ev+320
  return {'pv_fcff':str(pv),'pv_terminal':str(tv),'enterprise_value':str(ev),'equity_value':str(equity),'value_per_share_cny':str(equity/555),'value_per_share_hkd':str(equity/555*D('1.07'))}
 base=calc(D('.122'),flows);step=calc(D('.127'),flows);changed=calc(D('.127'),[v*D('.9') for v in flows])
 contribution1=D(step['value_per_share_hkd'])-D(base['value_per_share_hkd']);contribution2=D(changed['value_per_share_hkd'])-D(step['value_per_share_hkd'])
 sensitivity=[{'wacc':str(w),'g':str(g),'baseline':calc(w,flows,g),'scenario':calc(w,[v*D('.9') for v in flows],g)} for w in [D('.112'),D('.122'),D('.132')] for g in [D('.01'),D('.02'),D('.03')]]
 ref={'status':'frozen_before_agent_answers','facts':{'currency':'CNY','unit':'百万元','source_pages':[23,29],'periods':facts},
      'forecast':{'currency':'CNY','unit':'百万元','source_page':45,'revenue':[2402,3242,3910],'net_profit':[348,462,546],
                  'page2_net_profit':['347.8','461.8','546.1'],'page2_reported_eps':['0.63','0.83','0.99'],
                  'accepted_source_variation':'p2净利347.8/461.8/546.1，p45整数348/462/546，p38估值表2025净利463、估值4629；准确标来源即可，不强改为同一个数。EPS须区分报告明示与用股数复算。用p39披露的1.07汇率复算PE约8.90-8.93港币而非精准8.97；可说明输入舍入/隐含汇率差异，不能捏造隐藏精度。'},
      'dcf':{'source_page':39,'unit':'百万元','currency':'CNY','fcff':[str(v) for v in flows],'net_cash':'320','shares_million':'555','hkd_per_cny':'1.07','baseline':base,'scenario':changed,'contributions_hkd':[str(contribution1),str(contribution2)],'sensitivity':sensitivity},
      'quality_criteria':['图、CSV、Markdown、会话的绝对金额与标注单位一致；比例趋势正确不足以通过金额项。','机构预测与实际、分析假设分开；旧研报估值不混入较新的中报数据。','经营利润不再重复扣金融费用，合并净利与归母净利不混同。','现金流缺少完整间接法调节时保留无法解释部分，不凭空补平。','按题设DCF约定独立计算，不为接近报告目标价改参数；报告内部矛盾可保留。','局部更新只有指定输入变化，现金、股数和汇率保持不变；顺序贡献加总等于总差。','敏感性相同绝对网格同色标；更新WACC不等于把整个比较网格平移。','脚本和原数据可复算，输出文件实际可下载。'],
      'scoring':'逐题逐组记录错误及缺失，金额/百分比显示舍入在所声明精度内允许。数字缺失、来源不明、无法复算单列，不合并成一个虚构总准确率。'}
(root/'gold.json').write_text(json.dumps(ref,ensure_ascii=False,indent=2),encoding='utf-8')
print('Frozen independent source/DCF reference; not imported into the project.')

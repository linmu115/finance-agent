import pandas as pd, numpy as np, matplotlib.pyplot as plt, json, os
from pathlib import Path
out=Path('/output'); out.mkdir(exist_ok=True)
# Values transcribed from annual report indirect cash flow reconciliation, CNY million.
rows=[
('净利润',8463.71035565,10284.30619828,'起点','净利润'),
('资产减值准备',4675.84557344,1525.69947787,'非现金项目','减值'),
('信用减值损失',555.01970728,160.47731283,'非现金项目','减值'),
('固定资产/油气/生产性生物资产折旧',4055.64313537,3900.29509742,'非现金项目','折旧摊销'),
('使用权资产摊销',146.79088818,151.58148810,'非现金项目','折旧摊销'),
('无形资产摊销',268.69388532,235.20225714,'非现金项目','折旧摊销'),
('长期待摊费用摊销',140.62090118,144.26275784,'非现金项目','折旧摊销'),
('公允价值变动损失（收益以负号填列）',28.15311485,-278.18620165,'非现金项目','公允价值'),
('递延所得税资产减少（增加以负号填列）',-388.80275425,-208.81785908,'非现金项目','递延税'),
('递延所得税负债增加（减少以负号填列）',25.51390830,124.63568572,'非现金项目','递延税'),
('存货减少（增加以负号填列）',585.32471744,1789.45660589,'营运资金','存货'),
('经营性应收项目减少（增加以负号填列）',1824.57272485,-260.52629291,'营运资金','经营性应收'),
('经营性应付项目增加（减少以负号填列）',2611.14793603,-1751.36989744,'营运资金','经营性应付'),
('财务费用（收益以负号填列）',1026.19005425,2224.98929963,'其他调整','财务费用重分类'),
('投资损失（收益以负号填列）',-2417.33084926,31.08878568,'投资收益剔除项','投资损益重分类'),
('处置长期资产损失（收益以负号填列）',15.20366887,61.49610410,'其他调整','处置损益重分类'),
('固定资产报废损失（收益以负号填列）',42.08950717,23.41512364,'其他调整','报废损失'),
('其他',81.35391871,132.35170750,'其他调整','其他'),
]
cols=['项目','2024金额_百万元','2023金额_百万元','分类','子类']
df=pd.DataFrame(rows,columns=cols); df['同比变动贡献_百万元']=df['2024金额_百万元']-df['2023金额_百万元']
np24=df.loc[df['项目']=='净利润','2024金额_百万元'].iloc[0]; np23=df.loc[df['项目']=='净利润','2023金额_百万元'].iloc[0]
cfo24=21739.74039338; cfo23=18290.35765056
df.to_csv(out/'伊利2024现金桥明细.csv',index=False,encoding='utf-8-sig',float_format='%.6f')
# category table excludes net profit start and uses disclosed adjustment lines
adj=df[df['分类']!='起点'].groupby('分类',sort=False)[['2024金额_百万元','2023金额_百万元','同比变动贡献_百万元']].sum().reset_index()
summary=pd.DataFrame([{'分类':'合并净利润起点','2024金额_百万元':np24,'2023金额_百万元':np23,'同比变动贡献_百万元':np24-np23}])
summary=pd.concat([summary,adj],ignore_index=True)
summary=pd.concat([summary,pd.DataFrame([{'分类':'经营活动现金流量净额','2024金额_百万元':cfo24,'2023金额_百万元':cfo23,'同比变动贡献_百万元':cfo24-cfo23}])],ignore_index=True)
summary.to_csv(out/'伊利2024现金桥汇总.csv',index=False,encoding='utf-8-sig',float_format='%.6f')
# Verify bridge
assert abs(df.loc[df['分类']!='起点','2024金额_百万元'].sum()+np24-cfo24)<1e-5
assert abs(df.loc[df['分类']!='起点','2023金额_百万元'].sum()+np23-cfo23)<1e-5
# chart y/y bridge grouped, values exactly reconcile
items=['合并净利润变化','非现金项目变化','营运资金变化','投资收益剔除项变化','其他调整变化']
vals=[np24-np23]+[adj.loc[adj['分类']==x,'同比变动贡献_百万元'].iloc[0] for x in ['非现金项目','营运资金','投资收益剔除项','其他调整']]
# waterfall
starts=[0]; running=0
for v in vals[:-1]: running+=v; starts.append(running)
fig,ax=plt.subplots(figsize=(11,5.7))
labels=items+['CFO同比增加']
for i,(lab,v) in enumerate(zip(items,vals)):
    base=starts[i]
    ax.bar(i,v,bottom=base if v>=0 else base+v,color=('#218c74' if v>=0 else '#c0392b'),width=.65)
    ax.text(i, (base+v if v>=0 else base+v)-350 if v<0 else base+v+200, f'{v:,.0f}',ha='center',va='center',fontsize=9)
    running+=v
ax.bar(len(items),cfo24-cfo23,color='#34495e',width=.65)
ax.text(len(items),cfo24-cfo23+200,f'{cfo24-cfo23:,.0f}',ha='center',fontsize=9)
ax.axhline(0,color='black',linewidth=.8); ax.set_xticks(range(len(labels)),labels,rotation=15,ha='right'); ax.set_ylabel('同比现金流贡献（人民币百万元）')
ax.set_title('伊利股份2024年经营现金流同比变化桥（合并口径）')
ax.grid(axis='y',alpha=.2); fig.tight_layout(); fig.savefig(out/'伊利2024经营现金流同比桥.png',dpi=180); plt.close(fig)
# self-contained calculation script, using values in this analysis
script='''# Reproducible calculation for Yili 2024 CFO indirect reconciliation\nimport pandas as pd\nrows = '''+repr(rows)+'''\ndf=pd.DataFrame(rows,columns=["项目","2024金额_百万元","2023金额_百万元","分类","子类"])\ndf["同比变动贡献_百万元"]=df["2024金额_百万元"]-df["2023金额_百万元"]\nnet24=df.loc[df.项目=="净利润","2024金额_百万元"].iloc[0]; net23=df.loc[df.项目=="净利润","2023金额_百万元"].iloc[0]\ncfo24=21739.74039338; cfo23=18290.35765056\nprint("2024 CFO recomputed", net24+df.loc[df.分类!="起点","2024金额_百万元"].sum(), "disclosed",cfo24)\nprint("2023 CFO recomputed", net23+df.loc[df.分类!="起点","2023金额_百万元"].sum(), "disclosed",cfo23)\nprint(df.groupby("分类",sort=False)[["2024金额_百万元","2023金额_百万元","同比变动贡献_百万元"]].sum())\n'''
(out/'伊利2024现金桥_可复算.py').write_text(script,encoding='utf-8')
report=f'''# 伊利股份2024年净利润与经营现金流：质量改善的证据与边界\n\n## 结论\n经营现金流（CFO）同比增加 {cfo24-cfo23:,.3f} 百万元，但合并净利润下降 {np24-np23:,.3f} 百万元。现金转换的表观表现改善，主要来自营运资金调节同比转强（以合同负债/经销商预收款为主要管理层解释）及减值等调节增加；这不足以单独证明可持续盈利质量整体改善。营运资金改善含春节备货的时点因素，投资收益属于利润中需从间接法桥中扣除的非现金/非经营现金对应调节，不能当作CFO现金来源。\n\n## 现金桥（人民币百万元）\n|分类|2024|2023|同比贡献|\n|---|---:|---:|---:|\n'''+''.join(f"|{r['分类']}|{r['2024金额_百万元']:,.3f}|{r['2023金额_百万元']:,.3f}|{r['同比变动贡献_百万元']:,.3f}|\\n" for _,r in summary.iterrows())+'''\n合并净利润加全部调节项目与披露CFO勾稽，残差为零。逐项披露数值见明细CSV。\n\n## 关键解释\n- **非现金项目**：减值准备和折旧摊销、公允价值及递延税调整等合计上升，提升净利润至CFO调节额；其中资产减值损失大增与商誉减值相关。它是会计利润向现金流的非现金加回，不等于当期经营现金收入改善，也不是持续性经营动能。\n- **营运资金**：存货、经营性应收及经营性应付合计由2023年净流出转为2024年净流入。年报解释CFO上升主要因2025年春节备货、经销商预收货款增加；液体乳库存亦因春节备货期末库存较大（MD&A第19-20页）。预收款和存货周期可能在后续反转，需跟踪次年结算/发货与现金流。\n- **投资收益**：利润表投资收益同比上升（利润桥约 +2,448.420 百万元），现金流补充资料“投资损失（收益以负号填列）”同比贡献约 -2,448.420 百万元，作用是从合并净利润中扣除投资收益影响，现金桥不将该收益当作经营现金流。年报附注称投资收益增加主要因转让昌吉盛新实业股权处置收益（第210页）；该项一次性特征降低净利下降背后的经常性利润可见度。\n- **其他调整**：含财务费用等多项重分类/调整，合计同比负贡献；不能把补充资料的财务费用全额视为非现金，也不把它等同于现金利息。\n\n## 归母与扣非（不代入合并现金桥）\n2024/2023归母净利润分别为8,452.860/10,428.541百万元；扣非归母净利润分别为6,011.275/10,026.171百万元。两者均下降，且扣非归母降幅更大。归母口径与扣非归母仅作盈利质量旁证；现金桥起点是合并净利润8,463.710/10,284.306百万元。\n\n## 来源、口径与局限\n来源：伊利股份《2024年年度报告》（document_id `d84573bf6b584e7e874faa4c6adf454a`）。现金流量表补充资料：第217页表t253（合并净利润、减值、折旧摊销等），第218页表t254（投资损益、营运资金及CFO终点）；MD&A第19-20页（CFO及春节备货/预收解释）；第210页（投资收益原因）；第212页（商誉减值相关表述）。实际金额为披露/计算，未引入外部预测。\n\n口径为合并报表、人民币百万元；各项同比贡献=本年补充资料金额-上年补充资料金额。现金桥分类是对披露调节项的分析归组，不替代报表科目；财务费用按“其他调整”而非全部归为非现金。应收应付/存货补充资料是间接法调节额，不等同于资产负债表余额变动。春节备货/预收属于管理层定性解释，年报没有提供其对CFO增量的独立金额；不能将其量化为全部营运资金变化。两年比较不足以确认可持续改善。\n\n## 文件\n- 图：`伊利2024经营现金流同比桥.png`\n- 明细：`伊利2024现金桥明细.csv`；汇总：`伊利2024现金桥汇总.csv`\n- 可复算代码：`伊利2024现金桥_可复算.py`\n'''
(out/'伊利2024现金流分析报告.md').write_text(report,encoding='utf-8')
print({'net_profit_change':np24-np23,'cfo_change':cfo24-cfo23,'category':adj.to_dict(orient='records'),'outputs':sorted(p.name for p in out.iterdir())})
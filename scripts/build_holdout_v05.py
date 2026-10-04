"""Independent literal transcription from original rendered pages, never app output.

Run only while preparing the suite. This intentionally refuses to replace gold.
The original PDF words supply citation rectangles, never normalized answers.
"""
from pathlib import Path
from decimal import Decimal
import hashlib, json, re, datetime
import fitz

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'benchmark/versions/v0.5-holdout'
SOURCES = ROOT / 'samples/holdout-v05-sources'
if (OUT / 'gold.json').exists():
    raise SystemExit('Refusing to overwrite independently locked gold')
OUT.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
write = lambda name, value: (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
docs = {name: fitz.open(SOURCES / (name + '.pdf')) for name in ['fuyao_2025', 'cnooc_2025_en']}
table_specs = [
 ('fy_annual', 'fuyao_2025', 8, 2, [84,282,537,471], '主要会计数据', 'All 7 financial rows, all 4 numeric columns including reported growth'),
 ('fy_ratios', 'fuyao_2025', 8, 2, [84,505,537,632], '主要财务指标', 'All 5 financial rows, all 4 numeric columns including percentage-point differences'),
 ('fy_quarters', 'fuyao_2025', 9, 3, [80,571,542,671], '分季度主要财务数据', 'All 4 financial rows and all 4 quarters'),
 ('cn_income_1', 'cnooc_2025_en', 80, 2, [70,116,554,544], 'Consolidated profit or loss and other comprehensive income, part 1', 'Every printed amount; includes otherwise unlabeled subtotal and repeated attribution subtotal'),
 ('cn_income_2', 'cnooc_2025_en', 81, 3, [70,116,554,444], 'Consolidated profit or loss and other comprehensive income, part 2', 'Every printed amount including EPS, continuation, and explicit dash annotations'),
]
tables = [dict(id=i, input_file=f'{s}_whole_tables.pdf', source_id=s, original_page=op, page=ip, bbox=b, title=t, coverage=c, complete=True) for i,s,op,ip,b,t,c in table_specs]
by_table = {t['id']:t for t in tables}
cells=[]
used_words=set()

def numeric(text):
    value=text.replace(',','').replace('%','').strip()
    m=re.fullmatch(r'(增加|减少)?([+-]?\d+(?:\.\d+)?)个?百分点', value)
    if m:value=('-' if m[1]=='减少' else '')+m[2]
    if value.startswith('(') and value.endswith(')'):value='-'+value[1:-1]
    return Decimal(value)

def source_word(table, y, xband, literal):
    words=docs[table['source_id']][table['original_page']-1].get_text('words')
    matches=[(i,w) for i,w in enumerate(words) if xband[0]<=w[0]<xband[1] and abs(w[1]-y)<1 and w[4].strip()==literal]
    if len(matches)!=1:raise ValueError(('literal original cell not unique',table['id'],y,literal,matches))
    idx,w=matches[0];used_words.add((table['source_id'],table['original_page'],idx))
    return [round(v,5) for v in w[:4]]

def add(table_id,row,y,values,label,metric=None,pattern=None,*,currency='CNY',scale='1',raw_units=None,scope='consolidated_CAS',periods=None,unit_kind=None,extra=None,bands=None):
    t=by_table[table_id]
    if bands is None:bands=[(380,480),(480,554)] if table_id.startswith('cn_') else [(234,310),(310,386),(386,461),(461,538)]
    if periods is None:periods=['2025','2024']
    for col,(literal,period,band) in enumerate(zip(values,periods,bands),1):
        instant=len(period)==10
        quarter=re.fullmatch(r'(\d{4})-Q([1-4])',period)
        start='' if instant else f'{period}-01-01'
        end=period if instant else f'{period}-12-31'
        if quarter:
            year,q=quarter.groups(); q=int(q);start=f'{year}-{(q-1)*3+1:02d}-01';end=f'{year}-{q*3:02d}-'+('30' if q in [2,3] else '31')
        fact=dict(id=f'{table_id}_r{row}_c{col}',role='fact',input_file=t['input_file'],company_id=t['source_id'],table_id=table_id,page=t['page'],original_page=t['original_page'],source_row_label=label,source_column_label=period,glyph_bbox=source_word(t,y,band,literal),source_token=literal,raw_value=literal,value=format(numeric(literal)*Decimal(scale),'f'),metric=metric,definition_regex=pattern,currency=currency,normalized_unit='%' if currency=='percent' else currency,raw_unit_values=raw_units or ['元','人民币元','CNY'],scope=scope,version='original',period=period,period_start=start,period_end=end,period_variants=[period+'-FY'] if len(period)==4 else [],unit_kind=unit_kind)
        if extra:fact.update(extra)
        if unit_kind is None:fact.pop('unit_kind')
        cells.append(fact)

# Literal transcriptions checked against the four original rendered pages.
annual=[
 (312.8,['45,787,435,563','39,251,657,267','16.65','33,160,996,641'],'营业收入','revenue',r'营业收入|revenue'),
 (327.6,['11,161,682,700','8,990,819,590','24.15','6,716,021,914'],'利润总额',None,r'利润总额|profit.before.tax'),
 (342.3,['9,312,304,150','7,497,976,123','24.20','5,629,256,054'],'归属于上市公司股东的净利润','net_profit_parent',r'归母|归属于.*股东.*净利润|profit.*(?:equity|parent)'),
 (363.6,['9,164,684,348','7,445,999,659','23.08','5,527,467,830'],'归属于上市公司股东的扣除非经常性损益的净利润','net_profit_excluding_nonrecurring',r'扣.*非|exclu.*non.?recurr'),
 (384.7,['12,055,090,552','8,562,187,329','40.79','7,624,580,890'],'经营活动产生的现金流量净额','operating_cash_flow',r'经营.*现金|operating.*cash'),
 (440.9,['37,556,465,111','35,694,366,243','5.22','31,426,181,639'],'归属于上市公司股东的净资产','equity_parent',r'归母.*净资产|归属于.*(?:股东|母公司).*(?:净资产|权益)|equity.*(?:parent|shareholder)'),
 (455.3,['70,062,354,686','63,254,182,536','10.76','56,630,407,495'],'总资产','assets',r'总资产|资产总|total.assets'),
]
for row,(y,values,label,metric,pattern) in enumerate(annual,1):
    periods=['2025','2024','2025','2023'] if row<6 else ['2025-12-31','2024-12-31','2025-12-31','2023-12-31']
    add('fy_annual',row,y,values,label,metric,pattern,periods=periods)
    c=cells[-2];c.update(metric=None,currency='percent',normalized_unit='%',raw_unit_values=['%','百分比','percent'],unit_kind='ratio_percent',value=values[2],definition_regex='(?=.*(?:'+pattern+'))(?=.*(?:同比|增减|增长|change|growth|year.over.year))')

ratios=[
 (533.1,['3.57','2.87','24.39','2.16'],'基本每股收益','eps',r'基本.*每股|basic.*(?:earnings|EPS)|每股.*基本'),
 (547.3,['3.57','2.87','24.39','2.16'],'稀释每股收益',None,r'稀释|diluted'),
 (568.2,['3.51','2.85','23.16','2.12'],'扣除非经常性损益后的基本每股收益',None,r'扣.*非|exclu.*non.?recurr'),
 (589.2,['25.56','22.72','增加2.84个百分点','18.97'],'加权平均净资产收益率','roe',r'净资产收益率|return.on.equity|ROE'),
 (610.1,['25.16','22.57','增加2.59个百分点','18.63'],'扣除非经常性损益后的加权平均净资产收益率',None,r'扣.*非|exclu.*non.?recurr'),
]
for row,(y,values,label,metric,pattern) in enumerate(ratios,1):
    add('fy_ratios',row,y,values,label,metric,pattern,currency='CNY/share' if row<4 else 'percent',raw_units=['元/股','人民币元/股','CNY/share'] if row<4 else ['%','百分比','percent'],periods=['2025','2024','2025','2023'],unit_kind=None if row<4 else 'ratio_percent',bands=[(244,318),(318,383),(383,475),(475,538)])
    c=cells[-2];c.update(metric=None,currency='percent',normalized_unit='%',unit_kind='ratio_percent' if row<4 else 'percentage_points',raw_unit_values=['%','百分比','percent'] if row<4 else ['个百分点','百分点','percentage points','pp'],value=format(numeric(values[2]),'f'),definition_regex='(?=.*(?:'+pattern+'))(?=.*(?:同比|增减|增长|change|growth|year.over.year))' if row<4 else '(?=.*(?:'+pattern+'))(?=.*(?:百分点|percentage.point|percentage_points))')

quarterly=[
 (598.8,['9,910,012,731','11,537,378,985','11,854,516,214','12,485,527,633'],'营业收入','revenue'),
 (612.9,['2,029,740,416','2,774,971,295','2,259,142,444','2,248,449,995'],'归属于上市公司股东的净利润','net_profit_parent'),
 (633.8,['1,986,938,205','2,719,744,350','2,214,951,522','2,243,050,271'],'归属于上市公司股东的扣除非经常性损益后的净利润','net_profit_excluding_nonrecurring'),
 (654.7,['2,007,595,043','3,346,880,772','4,530,153,839','2,170,460,898'],'经营活动产生的现金流量净额','operating_cash_flow'),
]
for row,(y,values,label,metric) in enumerate(quarterly,1):add('fy_quarters',row,y,values,label,metric,periods=['2025-Q1','2025-Q2','2025-Q3','2025-Q4'],bands=[(230,304),(304,382),(382,460),(460,541)])

cn1=[
 (154.2,['335,652','355,615'],'Oil and gas sales',None,r'油气.*销售|石油.*天然气.*销售|oil.and.gas.sales'),
 (164.7,['53,684','55,142'],'Marketing revenues',None,r'贸易.*收入|营销.*收入|marketing.revenue'),
 (175.2,['8,884','9,749'],'Other revenue',None,r'其他.*收入|other.revenue'),
 (193.1,['398,220','420,506'],'Revenue subtotal','revenue',r'营业收入|收入合计|总收入|revenue'),
 (221.5,['(40,273)','(38,227)'],'Operating expenses',None,r'作业.*费|经营.*费|运营.*费|operating.expense'),
 (232.0,['(18,194)','(20,276)'],'Taxes other than income tax',None,r'税金.*附加|所得税以外|其他税|taxes.other.than.income'),
 (242.5,['(15,365)','(13,860)'],'Exploration expenses',None,r'勘探.*费|exploration.expense'),
 (253.0,['(79,771)','(74,606)'],'Depreciation, depletion and amortisation',None,r'折旧.*(?:折耗|损耗).*摊销|depreciation.*depletion.*amorti'),
 (263.5,['(2,044)','(8,297)'],'Special oil gain levy',None,r'石油特别收益金|special.oil.gain.levy'),
 (274.0,['(3,809)','(8,047)'],'Impairment and provision recognised, net',None,r'减值.*准备|impairment.*provision'),
 (284.5,['(9)','(29)'],'Expected credit losses',None,r'预期信用损失|expected.credit.loss'),
 (295.0,['(47,646)','(50,035)'],'Crude oil and product purchases',None,r'原油.*(?:产品|成品油).*采购|原油.*购买|crude.oil.and.product.purchases'),
 (305.4,['(12,039)','(11,140)'],'Selling and administrative expenses',None,r'销售.*(?:管理|行政).*费|selling.and.administrative'),
 (315.9,['(9,477)','(11,284)'],'Other expenses',None,r'其他.*(?:费|支出)|other.*expense'),
 (333.9,['(228,627)','(235,801)'],'Expenses subtotal',None,r'费用.*(?:合计|总)|(?:合计|总).*费用|total.expenses|expenses.total'),
 (351.7,['169,593','184,705'],'Profit from operating activities',None,r'经营.*利润|营业利润|profit.from.operating|operating.profit'),
 (362.2,['5,062','4,582'],'Interest income',None,r'利息收入|interest.income'),
 (372.7,['(6,512)','(6,096)'],'Finance costs',None,r'财务.*(?:成本|费用)|finance.cost'),
 (383.2,['627','(1,318)'],'Exchange gains/(losses), net',None,r'汇兑.*(?:损|益)|exchange.*(?:gain|loss)'),
 (393.7,['211','5,258'],'Investment income',None,r'投资收益|investment.income'),
 (404.2,['582','757'],'Share of profits of associates',None,r'联营.*(?:利润|损益)|share.of.profits.of.associates'),
 (414.7,['(1,054)','1,079'],'Share of (losses)/profits of a joint venture',None,r'合营.*(?:利润|损益|损失)|joint.venture'),
 (425.2,['1,130','1,009'],'Other income, net',None,r'其他.*(?:收益|收入).*净|other.income.*net'),
 (443.1,['169,639','189,976'],'Profit before tax',None,r'税前利润|利润总额|profit.before.tax'),
 (453.6,['(47,491)','(51,994)'],'Income tax expense',None,r'所得税.*(?:费|支出)|income.tax.expense'),
 (471.5,['122,148','137,982'],'Profit for the year','net_profit',r'净利润|本年利润|profit.for.the.year|net.profit'),
 (498.2,['122,082','137,936'],'Profit attributable to equity shareholders','net_profit_parent',r'归母|股东.*利润|profit.*(?:equity|shareholder|parent)'),
 (508.7,['66','46'],'Profit attributable to non-controlling interests',None,r'少数股东.*(?:损益|利润)|non.controlling.*(?:profit|interest)'),
 (526.6,['122,148','137,982'],'Profit attribution subtotal','net_profit',r'净利润|利润.*合计|profit.*(?:year|total)|net.profit'),
]
cn2=[
 (175.2,['(7,000)','4,486'],'Exchange differences on translation of foreign operations',None,r'外币.*(?:折算|换算)|境外.*(?:折算|换算)|translation.of.foreign'),
 (196.2,['49','(78)'],'Share of other comprehensive income/(expense) of associates',None,r'联营.*其他综合|associates.*comprehensive|comprehensive.*associates'),
 (206.7,['5','15'],'Cash flow hedge reserves',None,r'现金流.*套期|cash.flow.hedge'),
 (238.2,['4','(175)'],'Fair value change on equity investments designated as at fair value through other comprehensive income/(expense)',None,r'权益.*公允价值|其他权益工具.*变动|fair.value.*equity'),
 (248.7,['349','138'],'Change on remeasurement of defined benefit plan',None,r'重新计量.*(?:受益|福利)|(?:受益|福利).*重新计量|remeasurement.of.defined.benefit'),
 (305.5,['(6,593)','4,386'],'Other comprehensive expense/income for year net of tax',None,r'其他综合.*(?:合计|总|税后|净)|other.comprehensive.*(?:year|net.of.tax)'),
 (323.4,['115,555','142,368'],'Total comprehensive income for year',None,r'综合收益.*(?:总|合计)|综合收益总额|total.comprehensive'),
 (351.7,['115,489','142,322'],'Comprehensive income attributable to equity shareholders',None,r'股东.*综合收益|归母.*综合|comprehensive.*(?:shareholder|parent|equity)'),
 (362.2,['66','46'],'Comprehensive income attributable to non-controlling interests',None,r'少数股东.*综合收益|综合收益.*少数股东|comprehensive.*non.controlling'),
 (380.1,['115,555','142,368'],'Comprehensive income attribution subtotal',None,r'综合收益.*(?:总|合计)|total.comprehensive'),
 (417.3,['2.57','2.90'],'Basic earnings per share','eps',r'基本.*每股|basic.*(?:earnings|EPS)|每股.*基本'),
 (427.8,['2.57','2.90'],'Diluted earnings per share',None,r'稀释|diluted'),
]
for table_id,rows in [('cn_income_1',cn1),('cn_income_2',cn2)]:
    for row,(y,values,label,metric,pattern) in enumerate(rows,1):
        eps=table_id=='cn_income_2' and row>=11
        add(table_id,row,y,values,label,metric,pattern,scope='consolidated_IFRS',currency='CNY/share' if eps else 'CNY',scale='1' if eps else '1000000',raw_units=['元/股','人民币元/股','RMB Yuan','RMB/share','CNY/share'] if eps else ['人民币百万元','百万元','百万人民币','RMB million','RMB millions','millions of Renminbi','million RMB'])

# Exhaustive role assignment for every other number token in evaluated tables.
# Year labels and note references are not financial observations. A dash is not
# a disclosed numeric measurement: omission or a zero is neutral, never a hit.
for table in tables:
    for idx,w in enumerate(docs[table['source_id']][table['original_page']-1].get_text('words')):
        if not (table['bbox'][0]<=w[0]<table['bbox'][2] and table['bbox'][1]<=w[1]<table['bbox'][3]):continue
        if (table['source_id'],table['original_page'],idx) in used_words:continue
        if not re.search(r'\d',w[4]) and w[4] not in ['–','—','-']:continue
        if table['id'].startswith('cn_') and w[0]>380 and w[1]>130 and re.search(r'\d',w[4]):raise ValueError(('unannotated number in financial column',table['id'],w))
        if table['id'].startswith('fy_') and re.fullmatch(r'[\d,.]+',w[4]):raise ValueError(('unannotated numeric financial cell',table['id'],w))
        dash=w[4] in ['–','—','-']
        cells.append(dict(id=f'{table["id"]}_nonfact_{idx}',role='unscored' if dash else 'header_or_note',input_file=table['input_file'],company_id=table['source_id'],table_id=table['id'],page=table['page'],original_page=table['original_page'],glyph_bbox=[round(v,5) for v in w[:4]],source_token=w[4],reason='Dash is not an explicit numeric value; zero interpretation is not scored' if dash else 'Year/range header or note reference, not a financial observation',**({'allowed_values':['0']} if dash else {})))

gold={'version':'0.5.0','kind':'whole_table_company_holdout','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tables':tables,'cells':cells,'decidable_cells':sum(c['role']=='fact' for c in cells),'unscored_cells':sum(c['role']=='unscored' for c in cells),'negative_source_roles':sum(c['role']=='header_or_note' for c in cells)}
write('gold.json',gold)
print(json.dumps({'gold_sha256':sha(OUT/'gold.json'),'decidable_cells':gold['decidable_cells'],'unscored_cells':gold['unscored_cells'],'negative_source_roles':gold['negative_source_roles'],'table_counts':{t['id']:sum(c['role']=='fact' and c['table_id']==t['id'] for c in cells) for t in tables}},ensure_ascii=False))

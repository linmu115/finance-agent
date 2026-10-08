"""Exact financial row vocabulary; no document values or company-specific answers.

Keys reflect financial statement labels, not row positions. Unknown labels stay
unknown. Context-dependent totals are resolved by the table mapper separately.
"""
import re
from .normalization import compact, metric_id

VERSION = 'standard-rows-4'
ROWS = {
 'impairment_allowance': '减值准备|Impairment allowance',
 'cash': '货币资金|Cash and cash equivalents',
 'cash_on_hand': '库存现金|Cash on hand',
 'bank_deposits': '银行存款|Cash at banks|Bank balances',
 'other_monetary_funds': '其他货币资金',
 'financial_company_deposits': '存放财务公司存款',
 'cash_held_overseas': '存放在境外的款项总额',
 'interest_accrued_not_due': '未到期应收利息',
 'trading_financial_assets': '交易性金融资产|Financial assets at fair value through profit or loss|以公允价值计量且其变动计入当期损益的金融资产',
 'derivative_financial_assets': '衍生金融资产|Derivative financial assets',
 'notes_receivable': '应收票据|Bills receivable',
 'accounts_receivable': '应收账款|Trade receivables',
 'receivables_financing': '应收款项融资',
 'prepayments': '预付款项|Prepayments',
 'other_receivables': '其他应收款|Other receivables',
 'interest_receivable': '应收利息|Interest receivable',
 'dividends_receivable': '应收股利|Dividends receivable',
 'inventory': '存货|Inventories',
 'contract_assets': '合同资产|Contract assets',
 'assets_held_for_sale': '持有待售资产',
 'noncurrent_assets_due_within_one_year': '一年内到期的非流动资产',
 'other_current_assets': '其他流动资产|Other current assets',
 'current_assets': '流动资产合计|Total current assets',
 'debt_investments': '债权投资',
 'other_debt_investments': '其他债权投资',
 'long_term_receivables': '长期应收款',
 'long_term_equity_investments': '长期股权投资',
 'other_equity_investments': '其他权益工具投资',
 'other_noncurrent_financial_assets': '其他非流动金融资产',
 'investment_property': '投资性房地产|Investment property|Investment properties',
 'property_plant_equipment': '固定资产|Property and equipment|Property, plant and equipment',
 'construction_in_progress': '在建工程|Construction in progress',
 'productive_biological_assets': '生产性生物资产',
 'oil_gas_assets': '油气资产',
 'right_of_use_assets': '使用权资产|Right-of-use assets',
 'intangible_assets': '无形资产|Intangible assets',
 'development_expenditure': '开发支出',
 'goodwill': '商誉|Goodwill',
 'long_term_deferred_expenses': '长期待摊费用',
 'deferred_tax_assets': '递延所得税资产|Deferred tax assets',
 'other_noncurrent_assets': '其他非流动资产|Other non-current assets',
 'noncurrent_assets': '非流动资产合计|Total non-current assets',
 'short_term_borrowings': '短期借款',
 'central_bank_borrowings': '向中央银行借款',
 'customer_deposits': '吸收存款及同业存放',
 'interbank_lending': '拆出资金',
 'interbank_borrowings': '拆入资金',
 'trading_financial_liabilities': '交易性金融负债',
 'derivative_financial_liabilities': '衍生金融负债|Derivative financial liabilities',
 'notes_payable': '应付票据|Bills payable',
 'accounts_payable': '应付账款|Trade payables',
 'advances_from_customers': '预收款项',
 'contract_liabilities': '合同负债|Contract liabilities',
 'employee_benefits_payable': '应付职工薪酬',
 'taxes_payable': '应交税费|Tax payable|Income tax payable',
 'other_payables': '其他应付款|Other payables',
 'interest_payable': '应付利息',
 'dividends_payable': '应付股利',
 'liabilities_held_for_sale': '持有待售负债',
 'noncurrent_liabilities_due_within_one_year': '一年内到期的非流动负债',
 'other_current_liabilities': '其他流动负债|Other current liabilities',
 'current_liabilities': '流动负债合计|Total current liabilities',
 'long_term_borrowings': '长期借款',
 'bonds_payable': '应付债券',
 'lease_liabilities': '租赁负债|Lease liabilities',
 'long_term_payables': '长期应付款',
 'long_term_employee_benefits_payable': '长期应付职工薪酬',
 'provisions': '预计负债|Provisions',
 'deferred_income': '递延收益',
 'deferred_tax_liabilities': '递延所得税负债|Deferred tax liabilities',
 'other_noncurrent_liabilities': '其他非流动负债|Other non-current liabilities',
 'noncurrent_liabilities': '非流动负债合计|Total non-current liabilities',
 'share_capital': '实收资本（或股本）|股本|Share capital',
 'other_equity_instruments': '其他权益工具',
 'capital_reserve': '资本公积',
 'treasury_shares': '库存股|Treasury shares',
 'other_comprehensive_income': '其他综合收益|Other comprehensive income',
 'special_reserve': '专项储备',
 'surplus_reserve': '盈余公积',
 'general_risk_reserve': '一般风险准备',
 'retained_earnings': '未分配利润|Retained earnings',
 'equity_parent': '归属于母公司所有者权益（或股东权益）合计|Equity attributable to owners of the parent',
 'minority_interests': '少数股东权益|Non-controlling interests',
 'equity': '所有者权益（或股东权益）合计|所有者权益合计|Total equity',
 'liabilities_and_equity': '负债和所有者权益（或股东权益）总计|负债和所有者权益总计|Total equity and liabilities',
 'total_operating_revenue': '营业总收入',
 'interest_income': '利息收入|Interest income',
 'fee_commission_income': '手续费及佣金收入',
 'total_operating_cost': '营业总成本',
 'fee_commission_expense': '手续费及佣金支出',
 'taxes_surcharges': '税金及附加',
 'selling_expenses': '销售费用|Selling expenses|Selling and distribution expenses',
 'administrative_expenses': '管理费用|Administrative expenses',
 'research_development_expenses': '研发费用|Research and development expenses|Research and development costs',
 'finance_expenses': '财务费用|Finance costs',
 'other_income': '其他收益|Other income',
 'investment_income': '投资收益',
 'associate_joint_venture_income': '对联营企业和合营企业的投资收益|Share of profits and losses of associates',
 'fair_value_gain_loss': '公允价值变动收益|Fair value gains',
 'credit_impairment_loss': '信用减值损失',
 'asset_impairment_loss': '资产减值损失',
 'asset_disposal_gain_loss': '资产处置收益',
 'operating_profit': '营业利润|Operating profit',
 'nonoperating_income': '营业外收入',
 'nonoperating_expenses': '营业外支出',
 'profit_before_tax': '利润总额|Profit before tax|Loss before tax|Profit/(loss) before tax',
 'income_tax_expense': '所得税费用|Income tax expense|Income tax credit|Income tax expense/credit',
 'net_profit': '净利润|Profit for the year|Loss for the year|Profit for the period|Loss for the period|Profit/(loss) for the period',
 'minority_profit': '少数股东损益',
 'other_comprehensive_income_net_tax': '其他综合收益的税后净额',
 'comprehensive_income': '综合收益总额|Total comprehensive income for the period|Total comprehensive loss for the period',
 'comprehensive_income_parent': '归属于母公司所有者的综合收益总额',
 'comprehensive_income_minority': '归属于少数股东的综合收益总额',
 'eps_diluted': '稀释每股收益|Diluted earnings per share',
 'cash_received_from_sales': '销售商品、提供劳务收到的现金',
 'tax_refunds_received': '收到的税费返还',
 'other_operating_cash_received': '收到其他与经营活动有关的现金',
 'operating_cash_inflows': '经营活动现金流入小计',
 'cash_paid_for_goods_services': '购买商品、接受劳务支付的现金',
 'cash_paid_to_employees': '支付给职工及为职工支付的现金',
 'taxes_paid': '支付的各项税费|Taxes paid|Income tax paid',
 'other_operating_cash_paid': '支付其他与经营活动有关的现金',
 'operating_cash_outflows': '经营活动现金流出小计',
 'cash_from_investment_disposal': '收回投资收到的现金',
 'cash_from_investment_returns': '取得投资收益收到的现金',
 'cash_from_noncurrent_asset_disposal': '处置固定资产、无形资产和其他长期资产收回的现金净额',
 'cash_from_subsidiary_disposal': '处置子公司及其他营业单位收到的现金净额',
 'other_investing_cash_received': '收到其他与投资活动有关的现金',
 'investing_cash_inflows': '投资活动现金流入小计',
 'capex': '购建固定资产、无形资产和其他长期资产支付的现金',
 'cash_paid_for_investments': '投资支付的现金',
 'cash_for_subsidiary_acquisition': '取得子公司及其他营业单位支付的现金净额',
 'other_investing_cash_paid': '支付其他与投资活动有关的现金',
 'investing_cash_outflows': '投资活动现金流出小计',
 'investing_cash_flow': '投资活动产生的现金流量净额|Net cash flows used in investing activities|Net cash used in investing activities',
 'cash_from_equity_financing': '吸收投资收到的现金',
 'cash_from_borrowings': '取得借款收到的现金',
 'other_financing_cash_received': '收到其他与筹资活动有关的现金',
 'financing_cash_inflows': '筹资活动现金流入小计',
 'cash_repayment_borrowings': '偿还债务支付的现金',
 'cash_dividends_interest_paid': '分配股利、利润或偿付利息支付的现金',
 'other_financing_cash_paid': '支付其他与筹资活动有关的现金',
 'financing_cash_outflows': '筹资活动现金流出小计',
 'depreciation': '固定资产折旧、油气资产折耗、生产性生物资产折旧|Depreciation',
 'amortization_intangibles': '无形资产摊销|Amortisation of intangible assets',
 'amortization_deferred_expenses': '长期待摊费用摊销',
 'nonrecurring_profit': '非经常性损益合计',
 'bank_acceptance_notes': '银行承兑票据',
 'commercial_acceptance_notes': '商业承兑票据',
 'equity_instrument_investments': '权益工具投资',
 'forward_foreign_exchange_contracts': '远期外汇合约',
 'financial_assets_purchased_under_resale': '买入返售金融资产',
 'loans_and_advances': '发放贷款和垫款',
 'interest_expense': '利息支出|利息费用|Interest expense',
 'profit_continuing_operations': '持续经营净利润',
 'profit_discontinued_operations': '终止经营净利润',
 'other_comprehensive_income_parent': '归属母公司所有者的其他综合收益的税后净额|归属于母公司所有者的其他综合收益的税后净额',
 'other_comprehensive_income_minority': '归属于少数股东的其他综合收益的税后净额',
 'oci_not_reclassified': '不能重分类进损益的其他综合收益',
 'oci_reclassified': '将重分类进损益的其他综合收益',
 'defined_benefit_remeasurement': '重新计量设定受益计划变动额',
 'equity_method_oci_not_reclassified': '权益法下不能转损益的其他综合收益',
 'equity_method_oci_reclassified': '权益法下可转损益的其他综合收益',
 'equity_instruments_fair_value_change': '其他权益工具投资公允价值变动',
 'cashflow_hedge_reserve': '现金流量套期储备',
 'foreign_currency_translation': '外币财务报表折算差额',
 'net_increase_customer_deposits': '客户存款和同业存放款项净增加额',
 'cash_interest_fees_received': '收取利息、手续费及佣金的现金',
 'net_increase_customer_loans': '客户贷款及垫款净增加额',
 'net_increase_central_bank_deposits': '存放中央银行和同业款项净增加额',
 'net_increase_interbank_lending': '拆出资金净增加额',
 'cash_interest_fees_paid': '支付利息、手续费及佣金的现金',
 'cash_dividends_paid_minority': '子公司支付给少数股东的股利、利润',
 'cash_equity_contributions_minority': '子公司吸收少数股东投资收到的现金',
 'raw_materials_inventory': '原材料',
 'finished_goods_inventory': '库存商品',
 'packaging_materials_inventory': '包装材料',
 'low_value_consumables_inventory': '低值易耗品',
 'semi_finished_goods_inventory': '半成品',
 'materials_sent_for_processing_inventory': '委托加工物资',
 'cash_used_in_operations': 'Cash used in operations|Cash generated from operations',
 'operating_cash_flow': '经营活动产生的现金流量净额|经营现金流净额|Net cash used in operating activities|Net cash generated from operating activities',
 'intangible_asset_purchases': 'Purchase of intangible assets|Purchases of intangible assets',
 'property_equipment_purchases': 'Payment for property and equipment|Purchases of property and equipment',
 'property_equipment_disposal_proceeds': 'Proceeds from disposal of property and equipment',
 'fvoci_asset_purchases': 'Acquisition of financial assets at FVTOCI',
 'fvtpl_asset_purchases': 'Acquisition of financial assets at FVTPL',
 'cash_interest_received': 'Interests received|Interest received',
 'share_issue_proceeds': 'Proceeds from issues of shares|Proceeds from issue of shares',
 'share_issue_expenses': 'Share issues expenses paid',
 'cash_borrowing_interest_paid': 'Interests paid on bank and other borrowings',
 'pledged_deposit_cash_movement': '(Increase)/decrease in pledged bank deposits and other deposits',
 'restricted_deposit_cash_movement': 'Decrease in restricted bank deposits',
 'lease_repayments': 'Repayment of lease liabilities',
 'director_advance_proceeds': 'Advances from directors',
 'director_advance_repayments': 'Repayment of advances from directors',
 'other_borrowing_proceeds': 'Proceeds from other borrowings',
 'other_borrowing_repayments': 'Repayment of other borrowings',
 'bank_borrowing_proceeds': 'Proceeds from bank borrowings',
 'bank_borrowing_repayments': 'Repayment of bank borrowings',
 'financing_cash_flow': '筹资活动产生的现金流量净额|Net cash flows from financing activities|Net cash used in financing activities|Net cash generated from/(used in) financing activities',
 'net_change_in_cash': '现金及现金等价物净增加额|Net increase in cash and cash equivalents|Net decrease in cash and cash equivalents|Net increase/(decrease) in cash and cash equivalents',
 'cash_beginning': '期初现金及现金等价物余额|Cash and cash equivalents at beginning of period|Cash and cash equivalents at beginning of the period',
 'cash_ending': '期末现金及现金等价物余额|Cash and cash equivalents at end of period|Cash and cash equivalents at end of the period',
 'exchange_effect_on_cash': '汇率变动对现金及现金等价物的影响|Effect of foreign exchange rate changes, net|Effect of currency translation differences',
}


def normalize_label(label):
    label = compact(label).casefold()
    label = re.sub(r'^(?:[一二三四五六七八九十]+[、.．]|\(?[一二三四五六七八九十\d]+\)[、.．]?|\d+[、.．])', '', label)
    label = re.sub(r'^(?:其中|加|减)[:：]', '', label)
    label = re.sub(r'\((?:损失|亏损|净亏损|减少).*?\)', '', label)
    label = re.sub(r'\((?:元/股|人民币元)\)', '', label)
    return label.rstrip(':：')


LOOKUP = {normalize_label(label): metric for metric, aliases in ROWS.items() for label in aliases.split('|')}


def standard_metric(label):
    key = normalize_label(label)
    return LOOKUP.get(key) or metric_id(key)


def canonical_rows(table,rows,label_column=1,statement='notes',schema=None,topic=None):
    """Source labels, not English guesses, own standard row identifiers."""
    import copy
    import json
    rows=copy.deepcopy(rows)
    # In an equity matrix a row names a movement, while columns name balances.
    # Its specialized mapper already preserves this distinction.
    if statement=='equity':return rows
    for row in rows:
        attrs=row['attributes'];raw=table['rows'][row['row']-1]
        if attrs.get('row_subject') is False or len(raw)<label_column:continue
        metric=standard_metric(raw[label_column-1])
        if metric and attrs.get('metric'):
            attrs['metric']=metric
        if statement=='notes' and topic and metric in {'impairment_allowance','trading_financial_assets'}:
            dims=attrs.get('dimensions_json') or {}
            dims=json.loads(dims) if isinstance(dims,str) else copy.deepcopy(dims)
            dims.setdefault('asset_class',topic);attrs['dimensions_json']=json.dumps(dims,ensure_ascii=False)
            if metric=='trading_financial_assets' and topic=='other_noncurrent_financial_assets':
                attrs['metric']='financial_assets_fvtpl'
        label=normalize_label(raw[label_column-1])
        endpoint=re.fullmatch(r'(期初|年初|期末|年末)(?:余额|账面价值)',label)
        if endpoint:
            columns=attrs.get('columns_json') or (schema or {}).get('columns_json') or []
            columns=json.loads(columns) if isinstance(columns,str) else copy.deepcopy(columns)
            changed=False
            for c in columns:
                year=re.fullmatch(r'(\d{4})-FY',c.get('period',''))
                if year:
                    date=f"{int(year[1])-(endpoint[1] in {'期初','年初'})}-12-31"
                    c.update(period=date,start=date,end=date);changed=True
            if changed:attrs['columns_json']=json.dumps(columns,ensure_ascii=False)
    return rows

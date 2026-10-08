"""Exact financial row vocabulary; no document values or company-specific answers.

Keys reflect financial statement labels, not row positions. Unknown labels stay
unknown. Context-dependent totals are resolved by the table mapper separately.
"""
import re
from typing import NamedTuple
from .normalization import compact, metric_id

VERSION = 'standard-rows-6'
class StandardMetric(NamedTuple):
    labels: str | None  # None: existing normalization.METRICS row fallback.
    concept: str | None  # Explicitly None when no workpaper consumes this item.


# One semantic definition per canonical ID. New IDs must declare their concept
# here; financial workpapers derive their lookup from this registry.
STANDARD_METRICS = {
 'impairment_allowance': StandardMetric('减值准备|Impairment allowance', None),
 'cash': StandardMetric('货币资金|Cash and cash equivalents', 'cash_balance'),
 'cash_on_hand': StandardMetric('库存现金|Cash on hand', None),
 'bank_deposits': StandardMetric('银行存款|Cash at banks|Bank balances', None),
 'other_monetary_funds': StandardMetric('其他货币资金', None),
 'financial_company_deposits': StandardMetric('存放财务公司存款', None),
 'cash_held_overseas': StandardMetric('存放在境外的款项总额', None),
 'interest_accrued_not_due': StandardMetric('未到期应收利息', None),
 'trading_financial_assets': StandardMetric('交易性金融资产|Financial assets at fair value through profit or loss|以公允价值计量且其变动计入当期损益的金融资产', None),
 'derivative_financial_assets': StandardMetric('衍生金融资产|Derivative financial assets', None),
 'notes_receivable': StandardMetric('应收票据|Bills receivable', None),
 'accounts_receivable': StandardMetric('应收账款|Trade receivables', 'receivables'),
 'receivables_financing': StandardMetric('应收款项融资', None),
 'prepayments': StandardMetric('预付款项|Prepayments', 'prepayments'),
 'other_receivables': StandardMetric('其他应收款|Other receivables', 'other_receivables'),
 'interest_receivable': StandardMetric('应收利息|Interest receivable', None),
 'dividends_receivable': StandardMetric('应收股利|Dividends receivable', None),
 'inventory': StandardMetric('存货|Inventories', 'inventory'),
 'contract_assets': StandardMetric('合同资产|Contract assets', None),
 'assets_held_for_sale': StandardMetric('持有待售资产', None),
 'noncurrent_assets_due_within_one_year': StandardMetric('一年内到期的非流动资产', None),
 'other_current_assets': StandardMetric('其他流动资产|Other current assets', None),
 'current_assets': StandardMetric('流动资产合计|Total current assets', None),
 'debt_investments': StandardMetric('债权投资', None),
 'other_debt_investments': StandardMetric('其他债权投资', None),
 'long_term_receivables': StandardMetric('长期应收款', None),
 'long_term_equity_investments': StandardMetric('长期股权投资', None),
 'other_equity_investments': StandardMetric('其他权益工具投资', None),
 'other_noncurrent_financial_assets': StandardMetric('其他非流动金融资产', None),
 'investment_property': StandardMetric('投资性房地产|Investment property|Investment properties', None),
 'property_plant_equipment': StandardMetric('固定资产|Property and equipment|Property, plant and equipment', None),
 'construction_in_progress': StandardMetric('在建工程|Construction in progress', None),
 'productive_biological_assets': StandardMetric('生产性生物资产', None),
 'oil_gas_assets': StandardMetric('油气资产', None),
 'right_of_use_assets': StandardMetric('使用权资产|Right-of-use assets', None),
 'intangible_assets': StandardMetric('无形资产|Intangible assets', None),
 'development_expenditure': StandardMetric('开发支出', None),
 'goodwill': StandardMetric('商誉|Goodwill', 'goodwill'),
 'long_term_deferred_expenses': StandardMetric('长期待摊费用', None),
 'deferred_tax_assets': StandardMetric('递延所得税资产|Deferred tax assets', None),
 'other_noncurrent_assets': StandardMetric('其他非流动资产|Other non-current assets', 'other_noncurrent'),
 'noncurrent_assets': StandardMetric('非流动资产合计|Total non-current assets', None),
 'short_term_borrowings': StandardMetric('短期借款', 'short_term_borrowings'),
 'central_bank_borrowings': StandardMetric('向中央银行借款', None),
 'customer_deposits': StandardMetric('吸收存款及同业存放', None),
 'interbank_lending': StandardMetric('拆出资金', None),
 'interbank_borrowings': StandardMetric('拆入资金', None),
 'trading_financial_liabilities': StandardMetric('交易性金融负债', None),
 'derivative_financial_liabilities': StandardMetric('衍生金融负债|Derivative financial liabilities', None),
 'notes_payable': StandardMetric('应付票据|Bills payable', None),
 'accounts_payable': StandardMetric('应付账款|Trade payables', 'payables'),
 'advances_from_customers': StandardMetric('预收款项', None),
 'contract_liabilities': StandardMetric('合同负债|Contract liabilities', None),
 'employee_benefits_payable': StandardMetric('应付职工薪酬', None),
 'taxes_payable': StandardMetric('应交税费|Tax payable|Income tax payable', None),
 'other_payables': StandardMetric('其他应付款|Other payables', None),
 'interest_payable': StandardMetric('应付利息', None),
 'dividends_payable': StandardMetric('应付股利', None),
 'liabilities_held_for_sale': StandardMetric('持有待售负债', None),
 'noncurrent_liabilities_due_within_one_year': StandardMetric('一年内到期的非流动负债', None),
 'other_current_liabilities': StandardMetric('其他流动负债|Other current liabilities', None),
 'current_liabilities': StandardMetric('流动负债合计|Total current liabilities', None),
 'long_term_borrowings': StandardMetric('长期借款', 'long_term_borrowings'),
 'bonds_payable': StandardMetric('应付债券', 'bonds_payable'),
 'lease_liabilities': StandardMetric('租赁负债|Lease liabilities', 'lease_liabilities'),
 'long_term_payables': StandardMetric('长期应付款', None),
 'long_term_employee_benefits_payable': StandardMetric('长期应付职工薪酬', None),
 'provisions': StandardMetric('预计负债|Provisions', None),
 'deferred_income': StandardMetric('递延收益', None),
 'deferred_tax_liabilities': StandardMetric('递延所得税负债|Deferred tax liabilities', None),
 'other_noncurrent_liabilities': StandardMetric('其他非流动负债|Other non-current liabilities', None),
 'noncurrent_liabilities': StandardMetric('非流动负债合计|Total non-current liabilities', None),
 'share_capital': StandardMetric('实收资本（或股本）|股本|Share capital', None),
 'other_equity_instruments': StandardMetric('其他权益工具', None),
 'capital_reserve': StandardMetric('资本公积', None),
 'treasury_shares': StandardMetric('库存股|Treasury shares', None),
 'other_comprehensive_income': StandardMetric('其他综合收益|Other comprehensive income', None),
 'special_reserve': StandardMetric('专项储备', None),
 'surplus_reserve': StandardMetric('盈余公积', None),
 'general_risk_reserve': StandardMetric('一般风险准备', None),
 'retained_earnings': StandardMetric('未分配利润|Retained earnings', None),
 'equity_parent': StandardMetric('归属于母公司所有者权益（或股东权益）合计|Equity attributable to owners of the parent', 'parent_equity'),
 'minority_interests': StandardMetric('少数股东权益|Non-controlling interests', None),
 'equity': StandardMetric('所有者权益（或股东权益）合计|所有者权益合计|Total equity', 'equity'),
 'liabilities_and_equity': StandardMetric('负债和所有者权益（或股东权益）总计|负债和所有者权益总计|Total equity and liabilities', None),
 'total_operating_revenue': StandardMetric('营业总收入', 'total_operating_revenue'),
 'interest_income': StandardMetric('利息收入|Interest income', 'interest_income'),
 'fee_commission_income': StandardMetric('手续费及佣金收入', None),
 'total_operating_cost': StandardMetric('营业总成本', None),
 'fee_commission_expense': StandardMetric('手续费及佣金支出', None),
 'taxes_surcharges': StandardMetric('税金及附加', 'surcharges'),
 'selling_expenses': StandardMetric('销售费用|Selling expenses|Selling and distribution expenses', 'selling'),
 'administrative_expenses': StandardMetric('管理费用|Administrative expenses', 'administrative'),
 'research_development_expenses': StandardMetric('研发费用|Research and development expenses|Research and development costs', 'research'),
 'finance_expenses': StandardMetric('财务费用|Finance costs', 'finance_costs'),
 'other_income': StandardMetric('其他收益|Other income', 'other_income'),
 'investment_income': StandardMetric('投资收益', 'investment_income'),
 'associate_joint_venture_income': StandardMetric('对联营企业和合营企业的投资收益|Share of profits and losses of associates', 'associates'),
 'fair_value_gain_loss': StandardMetric('公允价值变动收益|Fair value gains', 'fair_value_gains'),
 'credit_impairment_loss': StandardMetric('信用减值损失', 'credit_impairment'),
 'asset_impairment_loss': StandardMetric('资产减值损失', 'asset_impairment'),
 'asset_disposal_gain_loss': StandardMetric('资产处置收益', 'asset_disposal'),
 'operating_profit': StandardMetric('营业利润|Operating profit', 'operating_profit'),
 'nonoperating_income': StandardMetric('营业外收入', 'nonoperating_income'),
 'nonoperating_expenses': StandardMetric('营业外支出', 'nonoperating_expenses'),
 'profit_before_tax': StandardMetric('利润总额|Profit before tax|Loss before tax|Profit/(loss) before tax', 'profit_before_tax'),
 'income_tax_expense': StandardMetric('所得税费用|Income tax expense|Income tax credit|Income tax expense/credit', 'tax'),
 'net_profit': StandardMetric('净利润|Profit for the year|Loss for the year|Profit for the period|Loss for the period|Profit/(loss) for the period', 'net_profit'),
 'minority_profit': StandardMetric('少数股东损益', 'minority_profit'),
 'other_comprehensive_income_net_tax': StandardMetric('其他综合收益的税后净额', None),
 'comprehensive_income': StandardMetric('综合收益总额|Total comprehensive income for the period|Total comprehensive loss for the period', None),
 'comprehensive_income_parent': StandardMetric('归属于母公司所有者的综合收益总额', None),
 'comprehensive_income_minority': StandardMetric('归属于少数股东的综合收益总额', None),
 'eps_diluted': StandardMetric('稀释每股收益|Diluted earnings per share', None),
 'cash_received_from_sales': StandardMetric('销售商品、提供劳务收到的现金', None),
 'tax_refunds_received': StandardMetric('收到的税费返还', None),
 'other_operating_cash_received': StandardMetric('收到其他与经营活动有关的现金', None),
 'operating_cash_inflows': StandardMetric('经营活动现金流入小计', None),
 'cash_paid_for_goods_services': StandardMetric('购买商品、接受劳务支付的现金', None),
 'cash_paid_to_employees': StandardMetric('支付给职工及为职工支付的现金', None),
 'taxes_paid': StandardMetric('支付的各项税费|Taxes paid|Income tax paid', None),
 'other_operating_cash_paid': StandardMetric('支付其他与经营活动有关的现金', None),
 'operating_cash_outflows': StandardMetric('经营活动现金流出小计', None),
 'cash_from_investment_disposal': StandardMetric('收回投资收到的现金', None),
 'cash_from_investment_returns': StandardMetric('取得投资收益收到的现金', None),
 'cash_from_noncurrent_asset_disposal': StandardMetric('处置固定资产、无形资产和其他长期资产收回的现金净额', None),
 'cash_from_subsidiary_disposal': StandardMetric('处置子公司及其他营业单位收到的现金净额', None),
 'other_investing_cash_received': StandardMetric('收到其他与投资活动有关的现金', None),
 'investing_cash_inflows': StandardMetric('投资活动现金流入小计', None),
 'capex': StandardMetric('购建固定资产、无形资产和其他长期资产支付的现金', None),
 'cash_paid_for_investments': StandardMetric('投资支付的现金', None),
 'cash_for_subsidiary_acquisition': StandardMetric('取得子公司及其他营业单位支付的现金净额', None),
 'other_investing_cash_paid': StandardMetric('支付其他与投资活动有关的现金', None),
 'investing_cash_outflows': StandardMetric('投资活动现金流出小计', None),
 'investing_cash_flow': StandardMetric('投资活动产生的现金流量净额|Net cash flows used in investing activities|Net cash used in investing activities', 'cfi'),
 'cash_from_equity_financing': StandardMetric('吸收投资收到的现金', None),
 'cash_from_borrowings': StandardMetric('取得借款收到的现金', None),
 'other_financing_cash_received': StandardMetric('收到其他与筹资活动有关的现金', None),
 'financing_cash_inflows': StandardMetric('筹资活动现金流入小计', None),
 'cash_repayment_borrowings': StandardMetric('偿还债务支付的现金', None),
 'cash_dividends_interest_paid': StandardMetric('分配股利、利润或偿付利息支付的现金', None),
 'other_financing_cash_paid': StandardMetric('支付其他与筹资活动有关的现金', None),
 'financing_cash_outflows': StandardMetric('筹资活动现金流出小计', None),
 'depreciation': StandardMetric('固定资产折旧、油气资产折耗、生产性生物资产折旧|Depreciation', None),
 'amortization_intangibles': StandardMetric('无形资产摊销|Amortisation of intangible assets', None),
 'amortization_deferred_expenses': StandardMetric('长期待摊费用摊销', None),
 'nonrecurring_profit': StandardMetric('非经常性损益合计', None),
 'bank_acceptance_notes': StandardMetric('银行承兑票据', None),
 'commercial_acceptance_notes': StandardMetric('商业承兑票据', None),
 'equity_instrument_investments': StandardMetric('权益工具投资', None),
 'forward_foreign_exchange_contracts': StandardMetric('远期外汇合约', None),
 'financial_assets_purchased_under_resale': StandardMetric('买入返售金融资产', None),
 'loans_and_advances': StandardMetric('发放贷款和垫款', None),
 'interest_expense': StandardMetric('利息支出|利息费用|Interest expense', None),
 'profit_continuing_operations': StandardMetric('持续经营净利润', None),
 'profit_discontinued_operations': StandardMetric('终止经营净利润', None),
 'other_comprehensive_income_parent': StandardMetric('归属母公司所有者的其他综合收益的税后净额|归属于母公司所有者的其他综合收益的税后净额', None),
 'other_comprehensive_income_minority': StandardMetric('归属于少数股东的其他综合收益的税后净额', None),
 'oci_not_reclassified': StandardMetric('不能重分类进损益的其他综合收益', None),
 'oci_reclassified': StandardMetric('将重分类进损益的其他综合收益', None),
 'defined_benefit_remeasurement': StandardMetric('重新计量设定受益计划变动额', None),
 'equity_method_oci_not_reclassified': StandardMetric('权益法下不能转损益的其他综合收益', None),
 'equity_method_oci_reclassified': StandardMetric('权益法下可转损益的其他综合收益', None),
 'equity_instruments_fair_value_change': StandardMetric('其他权益工具投资公允价值变动', None),
 'cashflow_hedge_reserve': StandardMetric('现金流量套期储备', None),
 'foreign_currency_translation': StandardMetric('外币财务报表折算差额', None),
 'net_increase_customer_deposits': StandardMetric('客户存款和同业存放款项净增加额', None),
 'cash_interest_fees_received': StandardMetric('收取利息、手续费及佣金的现金', None),
 'net_increase_customer_loans': StandardMetric('客户贷款及垫款净增加额', None),
 'net_increase_central_bank_deposits': StandardMetric('存放中央银行和同业款项净增加额', None),
 'net_increase_interbank_lending': StandardMetric('拆出资金净增加额', None),
 'cash_interest_fees_paid': StandardMetric('支付利息、手续费及佣金的现金', None),
 'cash_dividends_paid_minority': StandardMetric('子公司支付给少数股东的股利、利润', None),
 'cash_equity_contributions_minority': StandardMetric('子公司吸收少数股东投资收到的现金', None),
 'raw_materials_inventory': StandardMetric('原材料', None),
 'finished_goods_inventory': StandardMetric('库存商品', None),
 'packaging_materials_inventory': StandardMetric('包装材料', None),
 'low_value_consumables_inventory': StandardMetric('低值易耗品', None),
 'semi_finished_goods_inventory': StandardMetric('半成品', None),
 'materials_sent_for_processing_inventory': StandardMetric('委托加工物资', None),
 'cash_used_in_operations': StandardMetric('Cash used in operations|Cash generated from operations', 'operations'),
 'operating_cash_flow': StandardMetric('经营活动产生的现金流量净额|经营现金流净额|Net cash used in operating activities|Net cash generated from operating activities', 'cfo'),
 'intangible_asset_purchases': StandardMetric('Purchase of intangible assets|Purchases of intangible assets', None),
 'property_equipment_purchases': StandardMetric('Payment for property and equipment|Purchases of property and equipment', None),
 'property_equipment_disposal_proceeds': StandardMetric('Proceeds from disposal of property and equipment', None),
 'fvoci_asset_purchases': StandardMetric('Acquisition of financial assets at FVTOCI', None),
 'fvtpl_asset_purchases': StandardMetric('Acquisition of financial assets at FVTPL', None),
 'cash_interest_received': StandardMetric('Interests received|Interest received', None),
 'share_issue_proceeds': StandardMetric('Proceeds from issues of shares|Proceeds from issue of shares', None),
 'share_issue_expenses': StandardMetric('Share issues expenses paid', None),
 'cash_borrowing_interest_paid': StandardMetric('Interests paid on bank and other borrowings', None),
 'pledged_deposit_cash_movement': StandardMetric('(Increase)/decrease in pledged bank deposits and other deposits', None),
 'restricted_deposit_cash_movement': StandardMetric('Decrease in restricted bank deposits', None),
 'lease_repayments': StandardMetric('Repayment of lease liabilities', None),
 'director_advance_proceeds': StandardMetric('Advances from directors', None),
 'director_advance_repayments': StandardMetric('Repayment of advances from directors', None),
 'other_borrowing_proceeds': StandardMetric('Proceeds from other borrowings', None),
 'other_borrowing_repayments': StandardMetric('Repayment of other borrowings', None),
 'bank_borrowing_proceeds': StandardMetric('Proceeds from bank borrowings', None),
 'bank_borrowing_repayments': StandardMetric('Repayment of bank borrowings', None),
 'financing_cash_flow': StandardMetric('筹资活动产生的现金流量净额|Net cash flows from financing activities|Net cash used in financing activities|Net cash generated from/(used in) financing activities', 'cff'),
 'net_change_in_cash': StandardMetric('现金及现金等价物净增加额|Net increase in cash and cash equivalents|Net decrease in cash and cash equivalents|Net increase/(decrease) in cash and cash equivalents', None),
 'cash_beginning': StandardMetric('期初现金及现金等价物余额|Cash and cash equivalents at beginning of period|Cash and cash equivalents at beginning of the period', 'cash_begin'),
 'cash_ending': StandardMetric('期末现金及现金等价物余额|Cash and cash equivalents at end of period|Cash and cash equivalents at end of the period', 'cash_end'),
 'exchange_effect_on_cash': StandardMetric('汇率变动对现金及现金等价物的影响|Effect of foreign exchange rate changes, net|Effect of currency translation differences', 'cash_fx'),
 'revenue': StandardMetric('营业收入|revenue|revenues|net sales', 'revenue'),
 'net_profit_parent': StandardMetric('归属于上市公司股东的净利润|归属于母公司所有者的净利润|归属于母公司股东的净利润|归母净利润', 'parent_profit'),
 'assets': StandardMetric('总资产|资产总计|total assets', 'assets'),
 'liabilities': StandardMetric('负债合计|负债总计|total liabilities', 'liabilities'),
 'cost_of_revenue': StandardMetric('营业成本|cost of revenue|cost of sales', 'cogs'),
 'gross_profit': StandardMetric('毛利润|毛利|gross profit', 'gross_profit'),
 'net_profit_excluding_nonrecurring': StandardMetric('归属于上市公司股东的扣除非经常性损益的净利润|归属于上市公司股东的扣除非经常性损益后的净利润|扣除非经常性损益后的归属于上市公司股东的净利润|扣非归母净利润', 'deducted_profit'),
 'eps': StandardMetric('基本每股收益|basic earnings per share', None),
 'roe': StandardMetric('加权平均净资产收益率|return on equity', None),
}
ROWS = {key: definition.labels for key, definition in STANDARD_METRICS.items() if definition.labels is not None}

# Noncanonical model/historical IDs remain supported, including IFRS/HK.
LEGACY_WORKPAPER_ALIASES = {
 'bank_and_other_borrowings_current': ('bank_and_other_borrowings_current',),
 'bank_and_other_borrowings_non_current': ('bank_and_other_borrowings_non_current',),
 'lease_liabilities_current': ('lease_liabilities_current',),
 'lease_liabilities_non_current': ('lease_liabilities_non_current',),
 'revenue': ('operating_revenue',),
 'cogs': ('cost_of_sales', 'operating_cost'),
 'selling': ('selling_expense',),
 'administrative': ('administrative_expense',),
 'research': ('research_and_development_expenses', 'research_expense'),
 'operating_profit': ('operating_loss',),
 'finance_net': ('finance_income_net', 'finance_costs_net', 'net_finance_income'),
 'finance_income': ('finance_income',),
 'finance_costs': ('finance_costs',),
 'other_gains_net': ('other_gains_net',),
 'impairment': ('impairment_reversal_loss_financial_assets', 'reversal_of_ecls_on_financial_and_contract_assets'),
 'fair_value_gains': ('fair_value_gains_on_financial_assets_at_fvtpl', 'fair_value_change_gains_losses'),
 'associates': ('share_of_profits_of_associates', 'share_of_profits_of_associates_and_joint_ventures'),
 'profit_before_tax': ('profit_before_income_tax', 'total_profit'),
 'tax': ('income_tax_credit', 'income_tax_credit_expense'),
 'net_profit': ('profit_for_the_period', 'profit_for_the_period_total'),
 'parent_profit': ('profit_attributable_to_owners_of_the_company', 'owners_of_the_company'),
 'minority_profit': ('net_profit_non_controlling_interests', 'profit_attributable_to_non_controlling_interests', 'non_controlling_interests'),
 'deducted_profit': ('net_profit_excluding_non_recurring', 'net_profit_parent_excluding_non_recurring', 'net_profit_parent_ex_nonrecurring'),
 'parent_equity': ('equity_attributable_to_parent', 'equity_attributable_to_owners_of_the_company', 'net_assets_parent'),
 'liabilities': ('total_liabilities',),
 'asset_impairment': ('asset_impairment_losses',),
 'credit_impairment': ('credit_impairment_losses',),
 'investment_income': ('investment_gains',),
 'asset_disposal': ('asset_disposal_gains', 'asset_disposal_income'),
 'surcharges': ('taxes_and_surcharges',),
 'nonoperating_income': ('non_operating_income',),
 'nonoperating_expenses': ('non_operating_expenses',),
 'cfo': ('net_cash_flow_operating', 'net_cash_used_in_generated_from_operating_activities', 'net_cash_used_in_operating_activities', 'net_cash_generated_from_operating_activities', 'net_cash_inflow_outflow_operating_activities', 'operating_cash_flow_net', 'net_cash_from_operating_activities'),
 'cfi': ('net_cash_flow_from_investing_activities', 'net_cash_generated_from_used_in_investing_activities', 'net_cash_used_in_investing_activities', 'net_cash_inflow_outflow_investing_activities'),
 'cff': ('net_cash_flow_from_financing_activities', 'net_cash_used_in_financing_activities', 'net_cash_generated_from_financing_activities', 'net_cash_inflow_outflow_financing_activities'),
 'operations': ('net_cash_generated_from_operations', 'cash_generated_from_operations'),
 'cash_begin': ('cash_and_cash_equivalents_at_beginning_of_the_period', 'cash_and_cash_equivalents_at_beginning_of_period'),
 'cash_end': ('cash_and_cash_equivalents_at_end_of_the_period', 'cash_and_cash_equivalents_at_end_of_period', 'cash_and_cash_equivalents_ending'),
 'cash_fx': ('effects_of_exchange_rate_changes_on_cash_and_cash_equivalents', 'effect_of_exchange_rate_changes_on_cash_and_cash_equivalents', 'effect_of_currency_translation_differences'),
 'receivables': ('trade_receivables', 'trade_receivables_net'),
 'inventory': ('inventories',),
 'payables': ('trade_and_bills_payables', 'trade_payables'),
 'assets': ('total_assets',),
 'equity': ('total_equity', 'owners_equity', 'total_owners_equity'),
 'cash_balance': ('cash_and_cash_equivalents', 'cash_and_bank_balances'),
 'prepayments': ('prepaid_expenses',),
 'other_noncurrent': ('other_non_current_assets',),
 'segment_revenue': ('main_business_revenue', 'segment_revenue'),
 'segment_cost': ('main_business_cost', 'segment_cost'),
 'inventory_charge': ('inventory_write_down_provision_charged', 'inventory_provision_charged', 'inventory_write_down_charge'),
 'inventory_gross_opening': ('inventory_gross_beginning_balance',),
 'inventory_gross_closing': ('inventory_gross_ending_balance', 'inventory_gross_carrying_amount'),
 'receivables_gross': ('gross_carrying_amount',),
 'sales_volume': ('sales_volume', 'sales_quantity', 'quantity_sold', 'volume_sold'),
 'direct_materials_cost': ('direct_materials_cost',),
 'direct_labor_cost': ('direct_labor_cost',),
 'manufacturing_overhead': ('manufacturing_overhead',),
 'loading_and_transportation_cost': ('loading_and_transportation_cost',),
 'transportation_expenses': ('transportation_expenses',),
}

WORKPAPER_ALIASES = {}
for _metric, _definition in STANDARD_METRICS.items():
    if _definition.concept:
        WORKPAPER_ALIASES.setdefault(_definition.concept, []).append(_metric)
for _concept, _aliases in LEGACY_WORKPAPER_ALIASES.items():
    WORKPAPER_ALIASES.setdefault(_concept, []).extend(_aliases)
WORKPAPER_ALIASES = {key: tuple(dict.fromkeys(ids)) for key, ids in WORKPAPER_ALIASES.items()}


def workpaper_concepts(metric):
    """Exact ID contract, also used by inventory diagnostics; no fuzzy guesses."""
    return tuple(concept for concept, ids in WORKPAPER_ALIASES.items() if metric in ids)


def normalize_label(label):
    label = compact(label).casefold()
    label = re.sub(r'^(?:[一二三四五六七八九十]+[、.．]|\(?[一二三四五六七八九十\d]+\)[、.．]?|\d+[、.．])', '', label)
    label = re.sub(r'^(?:其中|加|减)[:：]', '', label)
    label = re.sub(r'\((?:损失|亏损|净亏损|减少).*?\)', '', label)
    label = re.sub(r'\((?:元/股|人民币元)\)', '', label)
    return label.rstrip(':：')


LOOKUP = {normalize_label(label): metric for metric, aliases in ROWS.items() for label in aliases.split('|')}


CONTEXTUAL_LABELS = {}
for _labels, _meanings in (
    ('Non-controlling interests|Non controlling interests|Non–controlling interests|Minority interests|非控股权益|非控股權益',
     {'profit':'minority_profit', 'comprehensive':'comprehensive_income_minority',
      'other_comprehensive':'other_comprehensive_income_minority', 'balance':'minority_interests'}),
    ('Owners of the Company|Owners of the parent|Equity holders of the Company|Equity holders of the parent|Shareholders of the Company|本公司拥有人|本公司擁有人',
     {'profit':'net_profit_parent', 'comprehensive':'comprehensive_income_parent',
      'other_comprehensive':'other_comprehensive_income_parent', 'balance':'equity_parent'}),
    ('Other comprehensive income|其他综合收益|其他綜合收益',
     {'balance':'other_comprehensive_income'}),
):
    for _label in _labels.split('|'):
        CONTEXTUAL_LABELS[normalize_label(_label)] = _meanings


def exact_standard_metric(label, *, context=None):
    key = normalize_label(label) if label is not None else None
    if key in CONTEXTUAL_LABELS:
        return CONTEXTUAL_LABELS[key].get((context or {}).get('kind'))
    return LOOKUP.get(normalize_label(label)) if label is not None else None


def standard_metric(label, *, context=None):
    key = normalize_label(label)
    return exact_standard_metric(label, context=context) or (None if key in CONTEXTUAL_LABELS else metric_id(key))


def canonical_rows(table,rows,label_column=1,statement='notes',schema=None,topic=None,context=None):
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
        from .metric_context import source_metric_context, column_semantics
        label_context=source_metric_context(table,row['row'],context)
        label_key=normalize_label(raw[label_column-1])
        metric=(exact_standard_metric(raw[label_column-1],context=label_context) if label_key in CONTEXTUAL_LABELS
                else standard_metric(raw[label_column-1]))
        columns=attrs.get('columns_json') or (schema or {}).get('columns_json') or []
        columns=json.loads(columns) if isinstance(columns,str) else columns
        measured_columns=columns or [{'column':c} for c in range(label_column+1,len(raw)+1)]
        if any(not column_semantics(table,row['row'],c['column'],c.get('label'))['row_metric_safe'] for c in measured_columns):
            metric=None
        if metric and attrs.get('metric'):
            if attrs['metric'] != metric:
                aliases=attrs.setdefault('source_metric_aliases',[])
                if attrs['metric'] not in aliases:aliases.append(attrs['metric'])
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

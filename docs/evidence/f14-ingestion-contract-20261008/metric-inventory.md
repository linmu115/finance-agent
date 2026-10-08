# 现有指标与底稿概念契约覆盖

只报告，不改指标或事实。未承接表示该 ID 没有精确映射到当前底稿概念；部分细项仍会被原表遍历、文本规则或来源表块消费，因此此清单不等于全部都是功能缺口。茅台使用此前 samples 同一原年报的两个已入库子集，非新增模型入库。

## 伊利2024年报

2006 条当前事实，404 个指标 ID；其中 51 个被概念契约接住，353 个未承接。

|指标 ID|事实数|已有标准 ID|来源表|
|---|---:|---|---|
|`acquisition_cash_flow`|3|否|t255|
|`administrative_expense_detail`|16|否|t231|
|`administrative_expenses_growth_rate`|1|否|t14|
|`advances_from_customers`|1|是|t101|
|`amortization_deferred_expenses`|2|是|t253|
|`amortization_intangibles`|4|是|t231, t253|
|`annual_depreciation_rate`|2|否|t122|
|`annual_proceeds_invested`|1|否|t75|
|`annual_proceeds_investment_rate`|1|否|t75|
|`asset_disposal_income_detail`|8|否|t239|
|`assets_growth_rate`|1|否|t8|
|`average_net_profit_three_years`|1|否|t57|
|`bank_acceptance_notes`|2|是|t129|
|`bank_deposits`|2|是|t125|
|`bargain_purchase_gain`|1|否|t11|
|`basic_eps`|1|否|t333|
|`basic_eps_ex_nonrecurring`|4|否|t333, t9|
|`basic_eps_ex_nonrecurring_growth_rate`|1|否|t9|
|`basic_eps_growth_rate`|1|否|t9|
|`board_meetings_absent`|12|否|t42, t43|
|`board_meetings_attended_in_person`|12|否|t42, t43|
|`board_meetings_attended_remotely`|12|否|t42, t43|
|`board_meetings_held`|4|否|t44|
|`board_meetings_proxy_attendance`|12|否|t42, t43|
|`board_meetings_required`|12|否|t42, t43|
|`business_segment_cost`|15|否|t23|
|`business_segment_cost_yoy`|15|否|t23|
|`business_segment_gross_margin`|15|否|t23|
|`business_segment_margin_change_pp`|15|否|t23|
|`business_segment_revenue`|15|否|t23|
|`business_segment_revenue_yoy`|15|否|t23|
|`buybacks_cancelled_three_years`|1|否|t57|
|`capex`|4|是|t108, t109|
|`capital_reserve`|34|是|t101, t103, t110, t111, t112, t113, t114, t115|
|`cash_and_cash_equivalents_ending`|2|否|t256|
|`cash_balance_in_cash_equivalents_note`|2|否|t256|
|`cash_beginning_balance`|2|否|t254|
|`cash_dividends_interest_paid`|4|是|t108, t109|
|`cash_dividends_paid_minority`|2|是|t108|
|`cash_dividends_ratio_three_years`|1|否|t57|
|`cash_dividends_three_years`|1|否|t57|
|`cash_ending_balance`|2|否|t254|
|`cash_equity_contributions_minority`|1|是|t108|
|`cash_equivalents`|1|否|t256|
|`cash_equivalents_beginning_balance`|2|否|t254|
|`cash_equivalents_ending_balance`|1|否|t254|
|`cash_for_subsidiary_acquisition`|3|是|t108, t109|
|`cash_from_borrowings`|4|是|t108, t109|
|`cash_from_equity_financing`|1|是|t108|
|`cash_from_investment_disposal`|4|是|t108, t109|
|`cash_from_investment_returns`|4|是|t108, t109|
|`cash_from_noncurrent_asset_disposal`|4|是|t108, t109|
|`cash_held_overseas`|2|是|t125|
|`cash_interest_fees_received`|2|是|t107|
|`cash_on_hand`|4|是|t125, t256|
|`cash_paid_for_goods_services`|4|是|t107, t109|
|`cash_paid_for_investments`|4|是|t108, t109|
|`cash_paid_to_employees`|4|是|t107, t109|
|`cash_received_from_sales`|4|是|t107, t109|
|`cash_repayment_borrowings`|4|是|t108, t109|
|`cashflow_hedge_reserve`|2|是|t105|
|`co2e_emissions_reduction`|1|否|t66|
|`commercial_acceptance_notes`|2|是|t129|
|`committed_investment_total`|1|否|t75|
|`comprehensive_income`|4|是|t105, t106|
|`comprehensive_income_minority`|2|是|t105|
|`comprehensive_income_parent`|2|是|t105|
|`construction_in_progress`|4|是|t100, t102|
|`contract_liabilities`|5|是|t101, t103, t298|
|`cost_component_amount`|48|否|t18|
|`cost_component_share`|48|否|t18|
|`cost_component_yoy`|24|否|t18|
|`cost_of_revenue_growth_rate`|1|否|t14|
|`cumulative_proceeds_invested`|1|否|t75|
|`cumulative_proceeds_investment_rate`|1|否|t75|
|`current_assets`|4|是|t100, t102|
|`current_liabilities`|4|是|t101, t103|
|`deferred_income`|4|是|t101, t103|
|`deferred_tax_assets`|4|是|t100, t102|
|`deferred_tax_assets_decrease`|2|否|t254|
|`deferred_tax_liabilities`|4|是|t101, t103|
|`deferred_tax_liabilities_increase`|2|否|t254|
|`defined_benefit_net_liability_movement`|10|否|t217|
|`defined_benefit_obligation_movement`|21|否|t214|
|`defined_benefit_plan_assets_movement`|4|否|t215|
|`defined_benefit_remeasurement`|2|是|t105|
|`demand_bank_deposits`|2|否|t256|
|`depreciation`|2|是|t253|
|`derivative_closing_carrying_value`|3|否|t28|
|`derivative_closing_value_to_net_assets`|3|否|t28|
|`derivative_cumulative_oci_change`|2|否|t28|
|`derivative_fair_value_pnl`|3|否|t28|
|`derivative_financial_assets`|7|是|t100, t128, t13|
|`derivative_financial_assets_change_amount`|1|否|t13|
|`derivative_financial_liabilities`|6|是|t101, t13, t192|
|`derivative_financial_liabilities_change_amount`|1|否|t13|
|`derivative_hedge_fair_value_change_disclosed`|1|否|t29|
|`derivative_hedge_net_pnl_commodity_futures_options`|1|否|t29|
|`derivative_hedge_net_pnl_fx`|1|否|t29|
|`derivative_opening_carrying_value`|2|否|t28|
|`derivative_other_movement`|2|否|t28|
|`derivative_purchases`|3|否|t28|
|`derivative_sales`|4|否|t28|
|`diluted_eps`|1|否|t333|
|`diluted_eps_ex_nonrecurring`|1|否|t333|
|`diluted_eps_growth_rate`|1|否|t9|
|`director_supervisor_executive_compensation_total`|1|否|t39|
|`dividends_payable`|6|是|t101, t103, t201|
|`dividends_receivable`|2|是|t100, t142|
|`employee_benefits_payable`|4|是|t101, t103|
|`employee_count`|11|否|t51|
|`employees_by_education`|5|否|t52|
|`entrusted_wealth_management_outstanding`|1|否|t74|
|`entrusted_wealth_management_overdue_unrecovered`|1|否|t74|
|`entrusted_wealth_management_placements`|1|否|t74|
|`environmental_protection_spending`|1|否|t61|
|`eps`|5|是|t105, t9|
|`eps_diluted`|5|是|t105, t9|
|`equity_instruments_fair_value_change`|4|是|t105, t106|
|`equity_method_investment_balance_movement`|3|否|t24|
|`equity_method_investment_balance_movement_change_amount`|1|否|t24|
|`equity_method_oci_not_reclassified`|2|是|t105|
|`equity_method_oci_reclassified`|2|是|t105|
|`equity_parent_growth_rate`|1|否|t8|
|`external_audit_fee`|2|否|t71|
|`external_auditor_tenure`|2|否|t71|
|`fair_value_asset_closing_balance`|6|否|t25|
|`fair_value_asset_disposals_redemptions`|5|否|t25|
|`fair_value_asset_oci_cumulative_change`|4|否|t25|
|`fair_value_asset_opening_balance`|5|否|t25|
|`fair_value_asset_other_movement`|5|否|t25|
|`fair_value_asset_profit_loss_change`|6|否|t25|
|`fair_value_asset_purchases`|5|否|t25|
|`fair_value_change_disposal_gain_loss_financial_assets_liabilities`|3|否|t11|
|`fair_value_change_loss`|2|否|t254|
|`fair_value_financial_asset_investment_balance_movement`|3|否|t24|
|`fair_value_financial_asset_investment_balance_movement_change_amount`|1|否|t24|
|`fair_value_measurement_items_total`|3|否|t13|
|`fair_value_measurement_items_total_change_amount`|1|否|t13|
|`finance_expense_detail`|6|否|t233|
|`financing_cash_flow_growth_rate`|2|否|t14, t21|
|`financing_cash_inflows`|4|是|t108, t109|
|`financing_cash_outflows`|4|是|t108, t109|
|`foreign_currency_translation`|2|是|t105|
|`forward_foreign_exchange_contracts`|4|是|t128, t192|
|`futures_margin_excluded_from_cash`|1|否|t257|
|`government_grants_nonrecurring`|3|否|t11|
|`guarantee_amount`|2|否|t73|
|`guarantee_balance`|1|否|t73|
|`guarantee_deposits_excluded_from_cash`|2|否|t257|
|`guarantee_to_net_assets_ratio`|1|否|t73|
|`guarantees_incurred_during_period`|1|否|t73|
|`guarantees_to_high_debt_ratio_entities`|1|否|t73|
|`impairment_allowance_reversal_receivables`|3|否|t11|
|`income_tax_current_unrecognized_temporary_differences_effect`|1|否|t243|
|`income_tax_effect_different_subsidiary_rates`|1|否|t243|
|`income_tax_exemptions_effect`|1|否|t243|
|`income_tax_expense_at_applicable_rate`|1|否|t243|
|`income_tax_expense_detail`|6|否|t242|
|`income_tax_nondeductible_expenses_effect`|1|否|t243|
|`income_tax_nontaxable_income_effect`|1|否|t243|
|`income_tax_prior_period_adjustments`|1|否|t243|
|`income_tax_prior_unrecognized_tax_losses_effect`|1|否|t243|
|`income_tax_rate_share`|6|否|t124|
|`indirect_method_asset_impairment_reconciliation`|2|否|t253|
|`indirect_method_asset_retirement_loss_reconciliation`|2|否|t253|
|`indirect_method_disposal_gain_loss_reconciliation`|2|否|t253|
|`indirect_method_rou_amortization_reconciliation`|2|否|t253|
|`intangible_assets`|4|是|t100, t102|
|`interbank_deposits`|2|否|t256|
|`interest_accrued_not_due`|2|是|t125|
|`interest_expense`|6|是|t104, t106, t233|
|`interest_receivable_excluded_from_cash`|2|否|t257|
|`internal_control_audit_fee`|1|否|t72|
|`inventory_decrease`|2|否|t254|
|`inventory_volume`|4|否|t17|
|`inventory_volume_yoy`|4|否|t17|
|`investing_cash_inflows`|4|是|t108, t109|
|`investing_cash_outflows`|4|是|t108, t109|
|`investment_cash_payment_detail`|6|否|t247|
|`investment_cash_receipt_detail`|7|否|t246|
|`investment_income_detail`|9|否|t235|
|`investment_loss`|2|否|t254|
|`investment_property`|4|是|t100, t102|
|`liabilities_and_equity`|4|是|t101, t103|
|`long_term_deferred_expenses`|4|是|t100, t102|
|`long_term_employee_benefits_payable`|2|是|t101|
|`long_term_equity_investments`|4|是|t100, t102|
|`long_term_payables`|3|是|t101, t211|
|`minority_interests`|20|是|t101, t110, t111, t112, t113|
|`net_cash_from_operating_activities`|2|否|t254|
|`net_change_cash_and_cash_equivalents`|2|否|t254|
|`net_change_in_cash`|4|是|t108, t109|
|`net_profit_excluding_nonrecurring_growth_rate`|1|否|t8|
|`net_profit_parent_growth_rate`|1|否|t8|
|`new_subsidiary_net_assets`|2|否|t32|
|`new_subsidiary_net_profit`|2|否|t32|
|`new_subsidiary_registered_capital`|1|否|t32|
|`new_subsidiary_registered_capital_eur`|1|否|t32|
|`noncurrent_asset_disposal_gain_loss`|3|否|t11|
|`noncurrent_assets`|4|是|t100, t102|
|`noncurrent_assets_due_within_one_year`|3|是|t100, t102|
|`noncurrent_liabilities`|4|是|t101, t103|
|`noncurrent_liabilities_due_within_one_year`|4|是|t101, t103|
|`nonrecurring_business_discontinuation_expense`|2|否|t12|
|`nonrecurring_gain_loss_total_after_tax`|3|否|t12|
|`nonrecurring_income_tax_effect`|3|否|t12|
|`nonrecurring_nci_effect_after_tax`|3|否|t12|
|`nonrecurring_other_nonoperating_gain_loss`|3|否|t12|
|`nonrecurring_tax_accounting_law_adjustment`|1|否|t12|
|`notes_payable`|4|是|t101, t103|
|`notes_receivable`|6|是|t100, t102, t129|
|`oci_not_reclassified`|4|是|t105, t106|
|`oci_reclassified`|2|是|t105|
|`operating_cash_flow_growth_rate`|3|否|t14, t21, t8|
|`operating_cash_inflows`|4|是|t107, t109|
|`operating_cash_outflows`|4|是|t107, t109|
|`operating_payables_increase`|2|否|t254|
|`operating_receivables_decrease`|2|否|t254|
|`other_comprehensive_income`|28|是|t101, t103, t110, t111, t112, t113, t114, t115|
|`other_comprehensive_income_minority`|2|是|t105|
|`other_comprehensive_income_net_tax`|4|是|t105, t106|
|`other_comprehensive_income_parent`|2|是|t105|
|`other_current_assets`|4|是|t100, t102|
|`other_current_liabilities`|4|是|t101, t103|
|`other_demand_cash`|2|否|t256|
|`other_equity_instruments_investment_change_amount`|1|否|t13|
|`other_equity_investments`|6|是|t100, t102, t13|
|`other_financing_cash_paid`|4|是|t108, t109|
|`other_financing_cash_payment_detail`|10|否|t251|
|`other_financing_cash_receipt_detail`|5|否|t250|
|`other_financing_cash_received`|2|是|t108|
|`other_investing_cash_paid`|2|是|t108|
|`other_investing_cash_payment_detail`|6|否|t249|
|`other_investing_cash_receipt_detail`|3|否|t248|
|`other_investing_cash_received`|1|是|t108|
|`other_monetary_funds`|2|是|t125|
|`other_noncurrent_financial_assets`|7|是|t100, t102, t13|
|`other_noncurrent_financial_assets_change_amount`|1|否|t13|
|`other_noncurrent_liabilities`|1|是|t101|
|`other_operating_cash_paid`|4|是|t107, t109|
|`other_operating_cash_received`|4|是|t107, t109|
|`other_operating_reconciliation`|2|否|t254|
|`other_payables`|13|是|t101, t103, t201, t298|
|`outsourced_labor_amount`|1|否|t53|
|`overall_equity_investment_summary`|3|否|t24|
|`overall_equity_investment_summary_change_amount`|1|否|t24|
|`overdue_guarantee_amount`|2|否|t73|
|`parent_nonrecurring_asset_disposal_gain_loss`|1|否|t331|
|`parent_nonrecurring_fair_value_and_disposal_gain_loss`|1|否|t331|
|`parent_nonrecurring_government_grants`|1|否|t331|
|`pollutant_ammonia_nitrogen_emission_amount`|32|否|t62, t63, t64, t65|
|`pollutant_ammonia_nitrogen_permitted_emission`|27|否|t62, t63, t64, t65|
|`pollutant_cod_emission_amount`|32|否|t62, t63, t64, t65|
|`pollutant_cod_permitted_emission`|27|否|t62, t63, t64, t65|
|`pollutant_nitrogen_oxides_emission_amount`|1|否|t62|
|`pollutant_nitrogen_oxides_permitted_emission`|1|否|t62|
|`pollutant_particulate_matter_emission_amount`|1|否|t62|
|`pollutant_sulfur_dioxide_emission_amount`|1|否|t62|
|`pollutant_total_nitrogen_emission_amount`|24|否|t62, t63, t64, t65|
|`pollutant_total_nitrogen_permitted_emission`|16|否|t62, t63, t64, t65|
|`pollutant_total_phosphorus_emission_amount`|2|否|t63, t64|
|`pollutant_total_phosphorus_permitted_emission`|1|否|t63|
|`portfolio_security_closing_value`|3|否|t27|
|`portfolio_security_fv_pnl_change`|3|否|t27|
|`portfolio_security_initial_cost`|3|否|t27|
|`portfolio_security_investment_income`|2|否|t27|
|`portfolio_security_opening_value`|3|否|t27|
|`portfolio_security_other_movement`|2|否|t27|
|`proceeds_gross`|1|否|t75|
|`proceeds_net`|1|否|t75|
|`production_volume`|4|否|t17|
|`production_volume_yoy`|4|否|t17|
|`productive_biological_assets`|2|是|t100|
|`profit_continuing_operations`|4|是|t105, t106|
|`property_plant_equipment`|8|是|t100, t102, t161|
|`public_donations_beneficiaries`|1|否|t68|
|`public_donations_cash`|1|否|t68|
|`public_donations_in_kind`|1|否|t68|
|`public_donations_total`|1|否|t68|
|`required_reserves_excluded_from_cash`|2|否|t257|
|`research_and_development_expenses_expensed`|1|否|t19|
|`research_and_development_investment_to_revenue`|1|否|t19|
|`research_and_development_investment_total`|1|否|t19|
|`research_and_development_staff_count`|1|否|t20|
|`research_development_expenses_growth_rate`|1|否|t14|
|`research_expense_detail`|10|否|t232|
|`research_staff_age_count`|5|否|t20|
|`research_staff_education_count`|5|否|t20|
|`research_staff_share_of_total_employees`|1|否|t20|
|`residual_value_rate`|2|否|t122|
|`restricted_deposits_excluded_from_cash`|2|否|t257|
|`retained_earnings`|44|是|t101, t103, t110, t111, t112, t113, t114, t115|
|`retained_earnings_parent`|1|否|t57|
|`revenue_growth_rate`|2|否|t14, t8|
|`right_of_use_assets`|4|是|t100, t102|
|`roe`|3|是|t9|
|`rural_revitalization_beneficiaries`|1|否|t69|
|`rural_revitalization_cash_investment`|1|否|t69|
|`rural_revitalization_in_kind_investment`|1|否|t69|
|`rural_revitalization_total_investment`|1|否|t69|
|`sales_volume_yoy`|4|否|t17|
|`security_closing_book_value`|2|否|t26|
|`security_fair_value_profit_loss`|2|否|t26|
|`security_opening_book_value`|2|否|t26|
|`security_original_investment_cost`|2|否|t26|
|`security_other_movement`|2|否|t26|
|`segment_assets`|6|否|t306|
|`segment_cost_growth_rate`|3|否|t15|
|`segment_cost_main_business`|5|否|t306|
|`segment_cost_other_business`|5|否|t306|
|`segment_cost_yoy`|10|否|t16|
|`segment_gross_margin`|13|否|t15, t16|
|`segment_gross_margin_change_pp`|3|否|t15|
|`segment_liabilities`|6|否|t306|
|`segment_margin_change_pp`|10|否|t16|
|`segment_revenue_growth_rate`|3|否|t15|
|`segment_revenue_main_business`|5|否|t306|
|`segment_revenue_other_business`|5|否|t306|
|`segment_revenue_yoy`|10|否|t16|
|`selling_expense_detail`|18|否|t230|
|`selling_expenses_growth_rate`|1|否|t14|
|`share_capital`|30|是|t101, t103, t110, t111, t112, t113, t114, t115|
|`shareholder_meetings_attended`|12|否|t42, t43|
|`short_term_low_value_lease_expense`|1|否|t260|
|`short_term_low_value_lease_expense_total`|1|否|t260|
|`specified_guarantees_total_c_plus_d_plus_e`|1|否|t73|
|`subsidiary_guarantee_balance`|1|否|t73|
|`subsidiary_guarantees_incurred`|1|否|t73|
|`subsidiary_net_assets`|10|否|t30, t31|
|`subsidiary_net_profit`|10|否|t30, t31|
|`subsidiary_registered_capital`|7|否|t30, t31|
|`subsidiary_registered_capital_usd`|2|否|t30, t31|
|`subsidiary_total_assets`|10|否|t30, t31|
|`suppliers_awarded_low_carbon_leader`|1|否|t67|
|`surplus_reserve`|16|是|t101, t103, t110, t111, t112, t113, t114, t115|
|`tax_refunds_received`|4|是|t107, t109|
|`taxes_paid`|4|是|t107, t109|
|`taxes_payable`|4|是|t101, t103|
|`total_distributions_three_years`|1|否|t57|
|`total_excluded_cash`|2|否|t257|
|`total_guarantee_balance`|1|否|t73|
|`total_operating_cost`|2|是|t104|
|`trading_financial_assets`|5|是|t100, t13|
|`trading_financial_assets_change_amount`|1|否|t13|
|`trading_financial_liabilities`|3|是|t101, t13|
|`trading_financial_liabilities_change_amount`|1|否|t13|
|`treasury_shares`|32|是|t101, t103, t110, t111, t112, t113, t114, t115|
|`useful_life_years`|2|否|t122|
|`weighted_average_roe`|1|否|t333|
|`weighted_average_roe_change_pp`|1|否|t9|
|`weighted_average_roe_ex_nonrecurring`|4|否|t333, t9|
|`weighted_average_roe_ex_nonrecurring_change_pp`|1|否|t9|

## 海尔2024年报

1496 条当前事实，345 个指标 ID；其中 49 个被概念契约接住，296 个未承接。

|指标 ID|事实数|已有标准 ID|来源表|
|---|---:|---|---|
|`acquisition_cash_paid_carrier_benelux`|1|否|t278|
|`acquisition_cash_paid_carrier_india`|1|否|t278|
|`acquisition_cash_paid_kwikot`|1|否|t278|
|`asset_impairment_adjustment`|2|否|t277|
|`average_net_profit_3y`|1|否|t67|
|`basic_eps`|4|否|t11|
|`basic_eps_ex_nonrecurring`|4|否|t11|
|`basic_eps_ex_nonrecurring_growth_rate`|1|否|t11|
|`basic_eps_growth_rate`|1|否|t11|
|`board_meetings_absent`|9|否|t53|
|`board_meetings_attended_by_communication`|9|否|t53|
|`board_meetings_attended_in_person`|9|否|t53|
|`board_meetings_expected`|9|否|t53|
|`board_meetings_held`|1|否|t54|
|`board_meetings_hybrid`|1|否|t54|
|`board_meetings_onsite`|1|否|t54|
|`board_meetings_proxy_attendance`|9|否|t53|
|`board_meetings_remote`|1|否|t54|
|`bonus_shares_per_10_shares`|1|否|t65|
|`business_combination_pre_acquisition_profit_loss`|1|否|t14|
|`capex`|4|是|t120, t122|
|`capital_reserve`|30|是|t110, t113, t124, t126, t129, t130|
|`capitalization_shares_per_10_shares`|1|否|t65|
|`capitalized_research_development`|1|否|t25|
|`capitalized_research_development_ratio`|1|否|t25|
|`cash_and_cash_equivalents_net_change`|2|否|t277|
|`cash_and_equivalents_acquired`|1|否|t278|
|`cash_and_equivalents_acquired_carrier_benelux`|1|否|t278|
|`cash_beginning_balance`|2|否|t277|
|`cash_dividend_amount_gross`|1|否|t65|
|`cash_dividend_payout_ratio`|1|否|t65|
|`cash_dividend_per_10_shares`|1|否|t65|
|`cash_dividend_ratio_3y_including_buybacks`|1|否|t67|
|`cash_dividends_and_buybacks_cumulative_3y`|1|否|t67|
|`cash_dividends_cumulative_3y`|1|否|t67|
|`cash_dividends_interest_paid`|4|是|t120, t123|
|`cash_ending_balance`|2|否|t277|
|`cash_for_subsidiary_acquisition`|2|是|t120|
|`cash_from_borrowings`|4|是|t120, t122|
|`cash_from_equity_financing`|2|是|t120|
|`cash_from_investment_disposal`|4|是|t120, t122|
|`cash_from_investment_returns`|4|是|t120, t122|
|`cash_from_noncurrent_asset_disposal`|3|是|t120, t122|
|`cash_paid_for_business_combinations`|1|否|t278|
|`cash_paid_for_goods_services`|4|是|t120, t122|
|`cash_paid_for_investments`|4|是|t120, t122|
|`cash_paid_to_employees`|4|是|t120, t122|
|`cash_received_from_sales`|4|是|t119, t122|
|`cash_repayment_borrowings`|4|是|t120, t123|
|`cashflow_hedge_reserve`|2|是|t116|
|`comprehensive_income`|4|是|t116, t118|
|`comprehensive_income_minority`|2|是|t116|
|`comprehensive_income_parent`|2|是|t116|
|`construction_in_progress`|4|是|t109, t112|
|`contract_assets`|2|是|t108|
|`contract_liabilities`|4|是|t109, t112|
|`cost_of_revenue_policy_adjustment`|1|否|t134|
|`credit_impairment_adjustment`|2|否|t277|
|`cumulative_fair_value_change_equity`|3|否|t31, t32|
|`current_assets`|4|是|t109, t112|
|`current_liabilities`|4|是|t110, t113|
|`debt_investments`|4|是|t109, t112|
|`deferred_income`|4|是|t110, t113|
|`deferred_tax_assets`|2|是|t109|
|`deferred_tax_assets_change`|2|否|t277|
|`deferred_tax_liabilities`|4|是|t110, t113|
|`deferred_tax_liabilities_change`|2|否|t277|
|`defined_benefit_remeasurement`|2|是|t115|
|`depreciation_expense`|2|否|t277|
|`derivative_closing_carrying_value`|3|否|t34|
|`derivative_closing_value_to_net_assets`|3|否|t34|
|`derivative_cumulative_equity_fv_change`|3|否|t34|
|`derivative_fair_value_change_pnl`|3|否|t34|
|`derivative_financial_assets`|2|是|t108|
|`derivative_financial_liabilities`|2|是|t109|
|`derivative_hedging_actual_profit`|1|否|t34|
|`derivative_initial_investment_amount`|3|否|t34|
|`derivative_investment_realized_profit`|1|否|t37|
|`derivative_opening_carrying_value`|3|否|t34|
|`development_expenditure`|2|是|t109|
|`diluted_eps`|4|否|t11|
|`diluted_eps_growth_rate`|1|否|t11|
|`director_age`|22|否|t39, t40|
|`director_annual_pre_tax_compensation`|13|否|t40|
|`director_shares_change`|15|否|t39, t40|
|`director_shares_closing`|16|否|t39, t40|
|`director_shares_opening`|16|否|t39, t40|
|`directors_supervisors_executives_total_compensation`|1|否|t49|
|`disposal_gain_loss_cashflow_adjustment`|2|否|t277|
|`dividends_payable`|2|是|t109|
|`dividends_receivable`|2|是|t112|
|`employee_benefits_payable`|4|是|t109, t112|
|`employee_count_administration`|1|否|t63|
|`employee_count_associate`|1|否|t63|
|`employee_count_bachelor_or_above`|1|否|t63|
|`employee_count_education_structure_total`|1|否|t63|
|`employee_count_finance`|1|否|t63|
|`employee_count_major_subsidiaries`|1|否|t63|
|`employee_count_parent_company`|1|否|t63|
|`employee_count_production`|1|否|t63|
|`employee_count_professional_structure_total`|1|否|t63|
|`employee_count_sales`|1|否|t63|
|`employee_count_secondary_or_below`|1|否|t63|
|`employee_count_technical`|1|否|t63|
|`employee_count_total`|1|否|t63|
|`eps`|2|是|t116|
|`eps_diluted`|2|是|t116|
|`equity_instruments_fair_value_change`|4|是|t116, t118|
|`equity_method_oci_reclassified`|3|是|t116, t118|
|`external_revenue_by_region`|20|否|t322|
|`fair_value_change_cashflow_adjustment`|2|否|t277|
|`fair_value_change_profit_loss`|5|否|t31, t32|
|`fair_value_derivative_financial_instruments_change_amount`|1|否|t15|
|`fair_value_derivative_financial_instruments_closing_balance`|1|否|t15|
|`fair_value_derivative_financial_instruments_opening_balance`|1|否|t15|
|`fair_value_derivative_financial_instruments_profit_impact`|1|否|t15|
|`fair_value_financial_products_change_amount`|1|否|t15|
|`fair_value_financial_products_closing_balance`|1|否|t15|
|`fair_value_financial_products_opening_balance`|1|否|t15|
|`fair_value_financial_products_profit_impact`|1|否|t15|
|`fair_value_investment_disposals`|5|否|t31, t32|
|`fair_value_investment_funds_change_amount`|1|否|t15|
|`fair_value_investment_funds_closing_balance`|1|否|t15|
|`fair_value_investment_funds_opening_balance`|1|否|t15|
|`fair_value_investment_funds_profit_impact`|1|否|t15|
|`fair_value_investment_other_changes`|4|否|t31, t32|
|`fair_value_investment_purchases`|5|否|t31, t32|
|`fair_value_investments_closing_balance`|7|否|t31, t32|
|`fair_value_investments_opening_balance`|7|否|t31, t32|
|`fair_value_items_change_amount`|1|否|t15|
|`fair_value_items_closing_balance`|1|否|t15|
|`fair_value_items_opening_balance`|1|否|t15|
|`fair_value_items_profit_impact`|1|否|t15|
|`fair_value_other_equity_instruments_change_amount`|1|否|t15|
|`fair_value_other_equity_instruments_closing_balance`|1|否|t15|
|`fair_value_other_equity_instruments_opening_balance`|1|否|t15|
|`fair_value_other_equity_instruments_profit_impact`|1|否|t15|
|`fair_value_receivables_financing_change_amount`|1|否|t15|
|`fair_value_receivables_financing_closing_balance`|1|否|t15|
|`fair_value_receivables_financing_opening_balance`|1|否|t15|
|`fair_value_receivables_financing_profit_impact`|1|否|t15|
|`fair_value_trading_equity_instruments_change_amount`|1|否|t15|
|`fair_value_trading_equity_instruments_closing_balance`|1|否|t15|
|`fair_value_trading_equity_instruments_opening_balance`|1|否|t15|
|`fair_value_trading_equity_instruments_profit_impact`|1|否|t15|
|`finance_expense_cashflow_adjustment`|2|否|t277|
|`financing_cash_inflows`|4|是|t120, t122|
|`financing_cash_outflows`|4|是|t121, t123|
|`foreign_currency_translation`|2|是|t116|
|`gross_margin`|6|否|t22|
|`income_tax_effect_on_nonrecurring_items`|3|否|t14, t367|
|`industry_cost_of_revenue`|2|否|t24|
|`industry_cost_of_revenue_growth_rate`|1|否|t24|
|`industry_cost_of_revenue_share`|2|否|t24|
|`industry_depreciation_cost`|2|否|t24|
|`industry_depreciation_cost_growth_rate`|1|否|t24|
|`industry_depreciation_cost_share`|2|否|t24|
|`industry_energy_cost`|2|否|t24|
|`industry_energy_cost_growth_rate`|1|否|t24|
|`industry_energy_cost_share`|2|否|t24|
|`industry_labor_cost`|2|否|t24|
|`industry_labor_cost_growth_rate`|1|否|t24|
|`industry_labor_cost_share`|2|否|t24|
|`industry_other_cost`|2|否|t24|
|`industry_other_cost_growth_rate`|1|否|t24|
|`industry_other_cost_share`|2|否|t24|
|`industry_raw_material_cost_growth_rate`|1|否|t24|
|`industry_raw_material_cost_share`|2|否|t24|
|`intangible_asset_amortization`|2|否|t277|
|`intangible_assets`|4|是|t109, t112|
|`interest_expense`|4|是|t115, t117|
|`interest_receivable`|4|是|t108, t112|
|`intersegment_revenue`|10|否|t318, t320, t321|
|`inventory_change_operating_cashflow`|2|否|t277|
|`inventory_volume`|1|否|t23|
|`inventory_volume_growth_rate`|1|否|t23|
|`investing_cash_inflows`|4|是|t120, t122|
|`investing_cash_outflows`|4|是|t120, t122|
|`investment_loss_cashflow_adjustment`|2|否|t277|
|`investment_property`|2|是|t109|
|`liabilities_and_equity`|4|是|t110, t113|
|`long_term_deferred_expense_amortization`|2|否|t277|
|`long_term_deferred_expenses`|4|是|t109, t112|
|`long_term_employee_benefits_payable`|2|是|t110|
|`long_term_equity_investments`|4|是|t109, t112|
|`long_term_payables`|2|是|t110|
|`long_term_receivables`|2|是|t109|
|`minority_interest_effect_on_nonrecurring_items`|3|否|t14, t367|
|`minority_interests`|17|是|t110, t124, t126|
|`net_assets_parent`|4|否|t9|
|`net_assets_parent_growth_rate`|1|否|t9|
|`net_change_in_cash`|4|是|t121, t123|
|`net_profit_attributable_to_parent_common_shareholders`|1|否|t65|
|`net_profit_parent_ex_nonrecurring`|20|否|t12, t9|
|`net_profit_parent_ex_nonrecurring_growth_rate`|1|否|t9|
|`net_profit_parent_growth_rate`|1|否|t9|
|`non_recurring_asset_disposal_gains_losses`|3|否|t14, t367|
|`non_recurring_fair_value_and_disposal_gains_losses`|3|否|t14, t367|
|`non_recurring_government_grants`|3|否|t14, t367|
|`noncurrent_assets`|4|是|t109, t112|
|`noncurrent_assets_due_within_one_year`|2|是|t108, t112|
|`noncurrent_liabilities`|4|是|t110, t113|
|`noncurrent_liabilities_due_within_one_year`|4|是|t110, t113|
|`notes_amount`|92|否|t254, t255, t260, t262, t263, t264, t266, t267, t268, t287, t339|
|`notes_payable`|2|是|t109|
|`notes_receivable`|2|是|t108|
|`oci_not_reclassified`|4|是|t115, t118|
|`oci_reclassified`|3|是|t116, t118|
|`operating_cash_flow_net`|4|否|t9|
|`operating_cash_flow_net_growth_rate`|1|否|t9|
|`operating_cash_inflows`|4|是|t120, t122|
|`operating_cash_outflows`|4|是|t120, t122|
|`operating_payables_change`|2|否|t277|
|`operating_receivables_change`|2|否|t277|
|`other_comprehensive_income`|24|是|t110, t113, t124, t126, t129, t130|
|`other_comprehensive_income_minority`|2|是|t116|
|`other_comprehensive_income_net_tax`|4|是|t115, t118|
|`other_comprehensive_income_parent`|2|是|t115|
|`other_current_assets`|4|是|t109, t112|
|`other_current_liabilities`|4|是|t110, t113|
|`other_equity_investments`|4|是|t109, t112|
|`other_financing_cash_paid`|4|是|t121, t123|
|`other_financing_cash_received`|2|是|t122|
|`other_investing_cash_paid`|3|是|t120, t122|
|`other_investing_cash_received`|2|是|t122|
|`other_non_operating_income_expenses`|3|否|t14, t367|
|`other_noncurrent_liabilities`|2|是|t110|
|`other_operating_cash_paid`|4|是|t120, t122|
|`other_operating_cash_received`|4|是|t120, t122|
|`other_operating_cashflow_reconciliation`|2|否|t277|
|`other_payables`|4|是|t109, t112|
|`production_volume`|1|否|t23|
|`production_volume_growth_rate`|1|否|t23|
|`profit_continuing_operations`|4|是|t115, t118|
|`property_plant_equipment`|4|是|t109, t112|
|`provisions`|2|是|t110|
|`raw_materials_inventory`|2|是|t24|
|`rd_staff_age_30_39_share`|1|否|t27|
|`rd_staff_age_40_49_share`|1|否|t27|
|`rd_staff_age_50_59_share`|1|否|t27|
|`rd_staff_age_60_plus_share`|1|否|t27|
|`rd_staff_associate_share`|1|否|t27|
|`rd_staff_bachelors_share`|1|否|t27|
|`rd_staff_doctorate_share`|1|否|t27|
|`rd_staff_high_school_or_below_share`|1|否|t27|
|`rd_staff_masters_share`|1|否|t27|
|`rd_staff_share_of_total_share`|1|否|t27|
|`rd_staff_under_30_share`|1|否|t27|
|`receivables_financing`|2|是|t108|
|`research_and_development_staff_count`|1|否|t26|
|`research_development_expense`|1|否|t25|
|`research_development_to_revenue_ratio`|1|否|t25|
|`retained_earnings`|31|是|t110, t113, t124, t126, t129, t130|
|`retained_earnings_parent`|1|否|t67|
|`retired_employees_with_expense_obligation`|1|否|t63|
|`revenue_growth_rate`|1|否|t9|
|`right_of_use_asset_amortization`|2|否|t277|
|`right_of_use_assets`|2|是|t109|
|`sales_volume_growth_rate`|1|否|t23|
|`security_investment_closing_carrying_value`|5|否|t33|
|`security_investment_cumulative_equity_fv_change`|4|否|t33|
|`security_investment_disposals`|2|否|t33|
|`security_investment_fair_value_change_pnl`|2|否|t33|
|`security_investment_income`|2|否|t33|
|`security_investment_initial_cost`|5|否|t33|
|`security_investment_opening_carrying_value`|5|否|t33|
|`segment_assets`|12|否|t318, t320, t321|
|`segment_cost_growth_rate`|6|否|t22|
|`segment_external_revenue`|6|否|t318, t321|
|`segment_liabilities`|12|否|t318, t320, t321|
|`segment_profit`|12|否|t318, t320, t321|
|`segment_revenue_growth_rate`|6|否|t22|
|`segment_total_cost`|12|否|t318, t320, t321|
|`selling_expenses_policy_adjustment`|1|否|t134|
|`share_buybacks_canceled_cumulative_3y`|1|否|t67|
|`share_buybacks_included_in_cash_dividends`|1|否|t66|
|`share_capital`|25|是|t110, t113, t124, t126, t129, t130|
|`shareholders_meetings_attended`|9|否|t53|
|`subsidiary_corporate_income_tax_rate`|75|否|t136, t137, t138|
|`surplus_reserve`|24|是|t110, t113, t124, t126, t129, t130|
|`tax_refunds_received`|2|是|t120|
|`taxes_paid`|4|是|t120, t122|
|`taxes_payable`|4|是|t109, t112|
|`total_assets_growth_rate`|1|否|t9|
|`total_cash_dividends_including_buybacks`|1|否|t66|
|`total_dividend_payout_ratio_including_buybacks`|1|否|t66|
|`total_nonrecurring_gains_losses`|3|否|t14, t367|
|`total_operating_cost`|2|是|t114|
|`total_research_development`|1|否|t25|
|`trading_financial_assets`|2|是|t108|
|`treasury_shares`|25|是|t110, t113, t124, t126, t129, t130|
|`urban_maintenance_tax_rate`|1|否|t135|
|`weighted_average_roe`|4|否|t11|
|`weighted_average_roe_change_pp`|1|否|t11|
|`weighted_average_roe_ex_nonrecurring`|4|否|t11|
|`weighted_average_roe_ex_nonrecurring_change_pp`|1|否|t11|

## 茅台2024核心20页

578 条当前事实，120 个指标 ID；其中 40 个被概念契约接住，80 个未承接。

|指标 ID|事实数|已有标准 ID|来源表|
|---|---:|---|---|
|`capex`|4|是|t14, t16|
|`capital_reserve`|16|是|t18, t19, t20, t21, t22, t23, t24, t3, t6|
|`cash_dividends_interest_paid`|4|是|t14, t16|
|`cash_dividends_paid_minority`|2|是|t14|
|`cash_from_investment_disposal`|3|是|t14, t16|
|`cash_from_investment_returns`|4|是|t14, t16|
|`cash_from_noncurrent_asset_disposal`|4|是|t14, t16|
|`cash_interest_fees_paid`|2|是|t14|
|`cash_interest_fees_received`|2|是|t13|
|`cash_paid_for_goods_services`|4|是|t14, t16|
|`cash_paid_for_investments`|3|是|t14, t16|
|`cash_paid_to_employees`|4|是|t14, t16|
|`cash_received_from_sales`|4|是|t13, t16|
|`comprehensive_income`|4|是|t10, t12|
|`comprehensive_income_minority`|2|是|t10|
|`comprehensive_income_parent`|2|是|t10|
|`construction_in_progress`|4|是|t2, t5|
|`contract_liabilities`|4|是|t3, t6|
|`current_assets`|4|是|t2, t5|
|`current_liabilities`|4|是|t3, t6|
|`customer_deposits`|2|是|t3|
|`debt_investments`|2|是|t2|
|`deferred_tax_assets`|4|是|t2, t6|
|`deferred_tax_liabilities`|4|是|t3, t6|
|`development_expenditure`|4|是|t2, t6|
|`employee_benefits_payable`|4|是|t3, t6|
|`eps`|4|是|t10, t12|
|`eps_diluted`|4|是|t10, t12|
|`fee_commission_expense`|2|是|t8|
|`financial_assets_purchased_under_resale`|2|是|t2|
|`financing_cash_outflows`|4|是|t14, t17|
|`foreign_currency_translation`|2|是|t9|
|`general_risk_reserve`|8|是|t18, t19, t20, t21, t3|
|`intangible_assets`|4|是|t2, t6|
|`interbank_lending`|2|是|t2|
|`interest_expense`|6|是|t11, t8|
|`investing_cash_inflows`|4|是|t14, t16|
|`investing_cash_outflows`|4|是|t14, t16|
|`investment_property`|4|是|t2, t5|
|`liabilities_and_equity`|4|是|t4, t7|
|`loans_and_advances`|2|是|t2|
|`long_term_deferred_expenses`|4|是|t2, t6|
|`long_term_equity_investments`|2|是|t5|
|`minority_interests`|19|是|t18, t19, t20, t21, t4|
|`net_change_in_cash`|4|是|t15, t17|
|`net_increase_central_bank_deposits`|2|是|t14|
|`net_increase_customer_deposits`|2|是|t13|
|`net_increase_customer_loans`|2|是|t14|
|`net_increase_interbank_lending`|2|是|t14|
|`noncurrent_assets`|4|是|t2, t6|
|`noncurrent_assets_due_within_one_year`|1|是|t2|
|`noncurrent_liabilities`|4|是|t3, t6|
|`noncurrent_liabilities_due_within_one_year`|4|是|t3, t6|
|`notes_receivable`|2|是|t2|
|`oci_reclassified`|2|是|t9|
|`operating_cash_inflows`|4|是|t14, t16|
|`operating_cash_outflows`|4|是|t14, t16|
|`other_comprehensive_income`|12|是|t18, t19, t20, t21, t3|
|`other_comprehensive_income_net_tax`|2|是|t9|
|`other_comprehensive_income_parent`|2|是|t9|
|`other_current_assets`|4|是|t2, t5|
|`other_current_liabilities`|4|是|t3, t6|
|`other_financing_cash_paid`|4|是|t14, t16|
|`other_investing_cash_paid`|4|是|t14, t16|
|`other_investing_cash_received`|4|是|t14, t16|
|`other_noncurrent_financial_assets`|4|是|t2, t5|
|`other_operating_cash_paid`|4|是|t14, t16|
|`other_operating_cash_received`|4|是|t14, t16|
|`other_payables`|4|是|t3, t6|
|`profit_continuing_operations`|4|是|t12, t9|
|`property_plant_equipment`|4|是|t2, t5|
|`retained_earnings`|38|是|t18, t19, t20, t21, t22, t23, t24, t4, t7|
|`right_of_use_assets`|4|是|t2, t5|
|`share_capital`|16|是|t18, t19, t20, t21, t22, t23, t24, t3, t6|
|`surplus_reserve`|30|是|t18, t19, t20, t21, t22, t23, t24, t3, t7|
|`tax_refunds_received`|1|是|t14|
|`taxes_paid`|4|是|t14, t16|
|`taxes_payable`|4|是|t3, t6|
|`total_operating_cost`|2|是|t8|
|`trading_financial_assets`|2|是|t2|

## 茅台2024附注22页

680 条当前事实，153 个指标 ID；其中 7 个被概念契约接住，146 个未承接。

|指标 ID|事实数|已有标准 ID|来源表|
|---|---:|---|---|
|`a`|1|否|t6|
|`accounts_receivable_total`|2|否|t19|
|`accounts_receivable_written_off`|1|否|t23|
|`ar_aging_allowance`|2|否|t21|
|`ar_aging_allowance_rate`|2|否|t21|
|`ar_aging_over_5y`|2|否|t19|
|`ar_aging_receivable`|3|否|t21|
|`ar_aging_under_1y`|2|否|t19|
|`ar_aging_under_1y_subtotal`|2|否|t19|
|`ar_allowance_movement_total`|3|否|t22|
|`ar_allowance_portfolio_movement`|3|否|t22|
|`ar_allowance_rate`|4|否|t20|
|`ar_bad_debt_allowance`|6|否|t20|
|`ar_gross_receivable`|6|否|t20|
|`ar_gross_share`|4|否|t20|
|`ar_net_carrying_value`|6|否|t20|
|`assets_growth_rate`|1|否|t8|
|`bank_acceptance_notes`|2|是|t17|
|`bank_deposits`|2|是|t12|
|`bond_assets`|2|否|t35|
|`bond_assets_subtotal`|2|否|t35|
|`carrying_value`|2|否|t14|
|`cash_held_overseas`|2|是|t12|
|`cash_on_hand`|2|是|t12|
|`construction_account_gross`|4|否|t55|
|`construction_account_net`|4|否|t55|
|`construction_in_progress`|2|是|t54|
|`construction_in_progress_and_materials_total`|2|否|t54|
|`construction_project_additions`|8|否|t56, t57|
|`construction_project_budget`|8|否|t56, t57|
|`construction_project_budget_progress`|6|否|t57|
|`construction_project_budget_utilization`|1|否|t56|
|`construction_project_closing_balance`|8|否|t56, t57|
|`construction_project_completion_progress`|7|否|t56, t57|
|`construction_project_opening_balance`|7|否|t57|
|`construction_project_transfer_to_ppe`|7|否|t56, t57|
|`corporate_income_tax_rate_share`|2|否|t10, t11|
|`current_maturities_debt_investments`|1|否|t38|
|`current_maturity_debt_impairment`|3|否|t39|
|`current_maturity_debt_impairment_stage1`|4|否|t41|
|`current_maturity_debt_impairment_total`|4|否|t41|
|`current_maturity_debt_investment_gross`|3|否|t39|
|`current_maturity_debt_net`|3|否|t39|
|`current_maturity_impairment_closing`|7|否|t40, t46|
|`current_maturity_impairment_decrease`|8|否|t40, t46|
|`current_maturity_impairment_increase`|7|否|t40, t46|
|`current_maturity_impairment_opening`|5|否|t46|
|`debt_investment_gross`|11|否|t45|
|`debt_investment_impairment`|9|否|t45|
|`debt_investment_impairment_stage1`|5|否|t47|
|`debt_investment_impairment_total`|5|否|t47|
|`debt_investment_net`|11|否|t45|
|`debt_investments_fvtpl`|2|否|t16|
|`education_surcharge_rate_share`|1|否|t10|
|`eps`|3|是|t9|
|`eps_basic_growth_rate`|1|否|t9|
|`eps_diluted`|3|是|t9|
|`eps_diluted_growth_rate`|1|否|t9|
|`eps_ex_nonrecurring`|3|否|t9|
|`eps_ex_nonrecurring_growth_rate`|1|否|t9|
|`equity_fund_investment_maotai_jinshi`|2|否|t49|
|`equity_fund_investment_maotai_zhaohua`|2|否|t49|
|`equity_instrument_investments`|2|是|t48|
|`equity_parent_growth_rate`|1|否|t8|
|`financial_assets_fvtpl`|2|否|t48|
|`financial_assets_purchased_under_resale`|2|是|t35|
|`fixed_asset_book_value`|4|否|t53|
|`fixed_asset_rollforward_amount`|91|否|t52|
|`impairment_allowance`|6|是|t14, t34, t35|
|`input_tax_pending_invoice`|1|否|t42|
|`intangible_asset_rollforward_amount`|40|否|t59|
|`interbank_lending`|2|是|t14|
|`interbank_placements`|2|否|t14|
|`inventory_gross_cost`|10|否|t36|
|`inventory_net_value`|10|否|t36|
|`inventory_write_down`|4|否|t36|
|`inventory_write_down_closing`|2|否|t37|
|`inventory_write_down_opening`|2|否|t37|
|`investment_property_movement_amount`|11|否|t50|
|`investment_property_total_movement_amount`|11|否|t50|
|`loan_loss_allowance`|2|否|t44|
|`loans_and_advances_gross`|2|否|t44|
|`loans_and_advances_net`|4|否|t43, t44|
|`local_education_surcharge_rate_share`|1|否|t10|
|`net_profit_parent_ex_nonrecurring_growth_rate`|1|否|t8|
|`net_profit_parent_growth_rate`|1|否|t8|
|`noncurrent_assets_due_within_one_year`|1|是|t38|
|`notes_receivable`|2|是|t17|
|`notes_receivable_derecognized_amount`|2|否|t18|
|`operating_cash_flow_growth_rate`|1|否|t8|
|`other_accounts_receivable_total`|2|否|t28|
|`other_ar_aging_1to2y`|2|否|t28|
|`other_ar_aging_2to3y`|2|否|t28|
|`other_ar_aging_3to4y`|2|否|t28|
|`other_ar_aging_4to5y`|2|否|t28|
|`other_ar_aging_over5y`|2|否|t28|
|`other_ar_aging_under_1y`|2|否|t28|
|`other_ar_aging_under_1y_subtotal`|2|否|t28|
|`other_ar_allowance_closing_balance`|2|否|t31|
|`other_ar_allowance_opening_balance`|2|否|t31|
|`other_ar_allowance_provision`|2|否|t31|
|`other_ar_allowance_reversal`|2|否|t31|
|`other_ar_allowance_writeoff`|2|否|t31|
|`other_ar_loss_allowance_stage1`|2|否|t30|
|`other_ar_loss_allowance_stage2`|5|否|t30|
|`other_ar_loss_allowance_stage3`|4|否|t30|
|`other_ar_loss_allowance_total`|5|否|t30|
|`other_current_assets_component`|1|否|t42|
|`other_current_assets_total`|2|否|t42|
|`other_monetary_funds`|1|是|t12|
|`other_noncurrent_financial_assets`|2|是|t49|
|`other_noncurrent_financial_assets_total`|2|否|t48|
|`other_receivables_components`|4|否|t27|
|`other_receivables_current_accounts`|2|否|t29|
|`other_receivables_employee_advances`|2|否|t29|
|`other_receivables_total`|2|否|t29|
|`other_receivables_written_off`|1|否|t32|
|`prepaid_income_tax`|2|否|t42|
|`prepayment_top_vendor_balance`|6|否|t26|
|`prepayment_top_vendor_share`|6|否|t26|
|`prepayments_by_age`|10|否|t25|
|`prepayments_by_age_share`|10|否|t25|
|`property_plant_equipment`|4|是|t51|
|`resale_financial_assets_net_total`|2|否|t34|
|`resale_financial_assets_other_institutions`|2|否|t34|
|`resale_financial_assets_subtotal`|2|否|t34|
|`restricted_cash_reserve_requirement`|2|否|t13|
|`restricted_interbank_deposits`|2|否|t15|
|`revenue_growth_rate`|1|否|t8|
|`right_of_use_asset_rollforward`|44|否|t58|
|`roe`|3|是|t9|
|`roe_change_pp`|1|否|t9|
|`roe_ex_nonrecurring`|3|否|t9|
|`roe_ex_nonrecurring_change_pp`|1|否|t9|
|`share_capital`|3|是|t8|
|`top_customer_ar_balance`|6|否|t24|
|`top_customer_ar_contract_total`|6|否|t24|
|`top_customer_ar_share`|6|否|t24|
|`top_customer_bad_debt_allowance`|2|否|t24|
|`top_other_ar_balance`|6|否|t33|
|`top_other_ar_share`|6|否|t33|
|`trading_financial_assets`|2|是|t16|
|`trading_financial_assets_total`|2|否|t16|
|`urban_maintenance_tax_rate_share`|1|否|t10|
|`vat_input_tax_deductible`|2|否|t42|
|`vat_rate_share`|1|否|t10|

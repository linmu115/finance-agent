"""Hand-calculated examples and independent Fraction present-value references.

These are synthetic economics examples, not any extraction/holdout company.
"""
import copy
import csv
import io
import json
import unittest
from decimal import Decimal, localcontext
from fractions import Fraction

from service.research_models import (ValidationError, value_dcf, value_comparables,
                                     manufacturing_scenario, financial_quality,
                                     evaluate_model, export_json, export_csv)
from service.research_schema import SCHEMAS, get_model_schema, get_model_example


def dcf_spec():
    return {"currency": "CNY", "amount_scale": "1", "base_year": 2024,
            "base": {"revenue": "1000", "net_working_capital": "100"},
            "forecast": [{"year": 2025, "revenue_growth": "0", "ebit_margin": "0.2",
                          "tax_rate": "0.25", "da_ratio": "0.05", "capex_ratio": "0.05", "nwc_ratio": "0.1"}],
            "cash_tax_policy": "floor_at_zero",
            "discount": {"wacc": "0.1", "cashflow_timing": "year_end"},
            "terminal": {"growth": "0", "roic": "0.2", "ebit_margin": "0.2", "tax_rate": "0.25"},
            "bridge": {"net_debt": "200", "non_controlling_interest": "20", "preferred_equity": "10", "non_operating_assets_ex_cash": "30"},
            "shares": {"count": "100", "scale": "1"},
            "source_refs": {"base.revenue": [{"document_id": "synthetic", "page": 1, "row": 2}]}}


def scenario_spec():
    dcf = dcf_spec()
    return {"currency": "CNY", "amount_scale": "1", "base_year": 2024,
            "base": {"revenue": "1000", "net_working_capital": "100"}, "volume_unit": "units",
            "baseline": [{"year": year, "volume": "100", "unit_price": "10", "material_cost_per_unit": "4",
                          "other_variable_cost_per_unit": "2", "fixed_cash_opex": "100", "da": "50", "capex": "50",
                          "nwc_ratio": "0.1", "tax_rate": "0.25"} for year in (2025, 2026)],
            "scenario": {"exposed_material_share": "0.5", "pass_through_rate": "0.5", "lag_years": 1,
                         "price_elasticity": "-1", "material_cost_changes": ["0.2", "0.2"],
                         "volume_changes": ["0", "0"], "autonomous_price_changes": ["0", "0"]},
            "dcf": {key: dcf[key] for key in ("cash_tax_policy", "discount", "terminal", "bridge", "shares")}}


class DcfTests(unittest.TestCase):
    def assertDecimalClose(self, actual, expected, tolerance="1e-40"):
        self.assertLessEqual(abs(Decimal(actual)-Decimal(expected)), Decimal(tolerance))

    def test_constant_perpetuity_with_bridge(self):
        result = value_dcf(dcf_spec())
        # Every year's 150 cashflow perpetuity has operating value 150/10%=1500.
        # Equity=1500-200-20-10+30=1300; shares100 =>13.
        self.assertDecimalClose(result["results"]["enterprise_value"], "1500")
        self.assertDecimalClose(result["results"]["equity_value"], "1300")
        self.assertDecimalClose(result["results"]["value_per_share"], "13")
        self.assertEqual(result["tables"]["forecast"][0]["fcff"], "150.000")

    def test_independent_two_year_fraction_reference(self):
        spec = dcf_spec()
        spec["forecast"] = [
            {"year": 2025, "revenue": "1100", "ebit": "220", "tax_rate": "0.25", "da": "55", "capex": "77", "net_working_capital": "121"},
            {"year": 2026, "revenue": "1210", "ebit": "242", "tax_rate": "0.25", "da": "60.5", "capex": "84.7", "net_working_capital": "133.1"}]
        spec["terminal"]["growth"] = "0.02"
        # Manual operating bridge yields cashflows 122 and 145.2.
        # Terminal: revenue1234.2 * margin.2 * aftertax.75 = NOPAT185.13;
        # reinvestment10%=18.513 =>166.617. TV=2082.7125.
        expected = Fraction(122)*Fraction(10,11) + (Fraction(1452,10)+Fraction(20827125,10000))*Fraction(100,121)
        with localcontext() as ctx:
            ctx.prec = 50
            reference = Decimal(expected.numerator)/Decimal(expected.denominator)
        result = value_dcf(spec)
        self.assertDecimalClose(result["results"]["enterprise_value"], reference)
        self.assertEqual(Decimal(result["tables"]["forecast"][0]["fcff"]), Decimal("122"))
        self.assertEqual(Decimal(result["tables"]["forecast"][1]["fcff"]), Decimal("145.2"))
        self.assertEqual(Decimal(result["results"]["terminal_fcff"]), Decimal("166.617"))

    def test_midyear_discount_only_forecast_not_terminal(self):
        spec = dcf_spec(); spec["discount"] = {"wacc": "0.21", "cashflow_timing": "mid_year"}
        # sqrt(1.21)=1.1; explicit150/1.1; TV=(150/.21)/1.21.
        expected = Fraction(1500,11) + Fraction(15000,21)*Fraction(100,121)
        with localcontext() as ctx:
            ctx.prec = 50
            reference = Decimal(expected.numerator)/Decimal(expected.denominator)
        result = value_dcf(spec)
        self.assertDecimalClose(result["results"]["enterprise_value"], reference)
        self.assertEqual(result["tables"]["forecast"][0]["discount_exponent"], "0.5")
        self.assertEqual(result["results"]["terminal_discount_exponent"], 1)

    def test_amount_and_share_scaling(self):
        spec = dcf_spec(); spec["amount_scale"] = "10000"; spec["shares"]["scale"] = "100"
        result = value_dcf(spec)
        self.assertDecimalClose(result["results"]["value_per_share"], "1300")
        self.assertEqual(result["units"]["value_per_share"], "CNY/share")
        self.assertEqual(result["units"]["ratios"], "decimal fraction (0.10 = 10%)")

    def test_gross_margin_and_opex_match_ebit_margin(self):
        spec = dcf_spec(); row = spec["forecast"][0]; del row["ebit_margin"]
        row.update(gross_margin="0.4", opex_ratio="0.2")
        result = value_dcf(spec)
        self.assertDecimalClose(result["results"]["enterprise_value"], "1500")
        self.assertEqual(Decimal(result["tables"]["forecast"][0]["gross_profit"]), 400)

    def test_operating_losses_tax_policy_explicit(self):
        spec = dcf_spec(); spec["forecast"][0]["ebit_margin"] = "-0.1"
        floor = value_dcf(spec)["tables"]["forecast"][0]
        self.assertEqual(Decimal(floor["cash_tax"]), 0); self.assertEqual(Decimal(floor["fcff"]), -100)
        spec["cash_tax_policy"] = "immediate_credit"
        credit = value_dcf(spec)["tables"]["forecast"][0]
        self.assertEqual(Decimal(credit["cash_tax"]), -25); self.assertEqual(Decimal(credit["fcff"]), -75)

    def test_negative_working_capital_and_net_cash_supported(self):
        spec = dcf_spec(); spec["base"]["net_working_capital"] = "-100"; spec["forecast"][0]["nwc_ratio"] = "-0.1"
        spec["bridge"]["net_debt"] = "-100"
        result = value_dcf(spec)
        self.assertDecimalClose(result["results"]["equity_value"], "1600")

    def test_negative_equity_residual_not_clipped(self):
        spec = dcf_spec(); spec["bridge"]["net_debt"] = "2000"
        result = value_dcf(spec)
        self.assertDecimalClose(result["results"]["equity_value"], "-500")
        self.assertTrue(any("negative" in message for message in result["warnings"]))

    def test_sensitivity_invalid_cells_and_direction(self):
        spec = dcf_spec(); spec["sensitivity"] = {"wacc": ["0.08", "0.12"], "growth": ["0", "0.1"]}
        rows = value_dcf(spec)["tables"]["sensitivity"]
        self.assertEqual(rows[1]["status"], "invalid"); self.assertIsNone(rows[1]["value_per_share"])
        self.assertGreater(Decimal(rows[0]["value_per_share"]), Decimal(rows[2]["value_per_share"]))

    def test_roic_reinvestment_growth_not_free(self):
        spec = dcf_spec(); spec["terminal"].update(growth="0.04", roic="0.2")
        result = value_dcf(spec)
        self.assertEqual(Decimal(result["results"]["terminal_reinvestment_rate"]), Decimal("0.2"))
        self.assertEqual(Decimal(result["results"]["terminal_fcff"]), Decimal("124.8"))

    def test_boundary_inputs_plain_validation_error(self):
        changes = [("discount", "wacc", "0"), ("terminal", "growth", "0.1"),
                   ("terminal", "growth", "-0.01"), ("terminal", "roic", "0"),
                   ("terminal", "tax_rate", "1.01"), ("terminal", "ebit_margin", "-0.1"),
                   ("shares", "count", "0"), ("base", "revenue", "NaN"),
                   ("base", "revenue", True), ("base", "revenue", "Infinity")]
        for section, key, value in changes:
            with self.subTest(section=section, key=key, value=value):
                spec = dcf_spec(); spec[section][key] = value
                with self.assertRaises(ValidationError): value_dcf(spec)
        spec=dcf_spec(); spec["terminal"].update(growth="0.05",roic="0.04")
        with self.assertRaisesRegex(ValidationError, "ROIC"): value_dcf(spec)

    def test_no_double_cash_or_conflicting_forecasts(self):
        spec = dcf_spec(); spec["bridge"]["cash"] = "10"
        with self.assertRaisesRegex(ValidationError, "net_debt"): value_dcf(spec)
        spec = dcf_spec(); spec["forecast"][0]["revenue"] = "1000"
        with self.assertRaisesRegex(ValidationError, "exactly one"): value_dcf(spec)
        spec = dcf_spec(); spec["forecast"][0]["year"] = 2026
        with self.assertRaisesRegex(ValidationError, "contiguous"): value_dcf(spec)

    def test_determinism_no_mutation_source_refs_and_exports(self):
        spec = dcf_spec(); before = copy.deepcopy(spec)
        result = value_dcf(spec)
        self.assertEqual(spec, before); self.assertEqual(result, value_dcf(spec))
        self.assertEqual(result["input_assumptions"]["source_refs"], spec["source_refs"])
        self.assertEqual(result, json.loads(export_json(result)))
        csv_rows = list(csv.DictReader(io.StringIO(export_csv(result, "forecast"))))
        self.assertEqual(csv_rows[0]["fcff"], result["tables"]["forecast"][0]["fcff"])
        with self.assertRaises(ValidationError): export_csv(result, "not_a_table")


class ComparableTests(unittest.TestCase):
    def spec(self, method="pe"):
        return {"currency": "CNY", "amount_scale": "1", "method": method, "aggregation": "median", "metric_basis": "FY2026_forward_unadjusted",
                "subject": {"earnings": "100", "shares": {"count": "100", "scale": "1"}},
                "peers": [{"id": str(i), "metric_basis": "FY2026_forward_unadjusted", "multiple": value} for i, value in enumerate(("10", "14", "30"))]}

    def test_pe_direct_equity_no_debt_subtraction(self):
        result = value_comparables(self.spec())
        self.assertEqual(Decimal(result["results"]["equity_value"]), 1400)
        self.assertEqual(Decimal(result["results"]["value_per_share"]), 14)
        self.assertIsNone(result["results"]["enterprise_value"])

    def test_ev_ebitda_bridge(self):
        spec = self.spec("ev_ebitda"); spec["subject"] = {"ebitda": "200", "shares": {"count": "100", "scale": "1"}, "bridge": dcf_spec()["bridge"]}
        result = value_comparables(spec)
        self.assertEqual(Decimal(result["results"]["enterprise_value"]), 2800)
        self.assertEqual(Decimal(result["results"]["equity_value"]), 2600)

    def test_negative_or_wrong_basis_peers_excluded_with_reasons(self):
        spec = self.spec(); spec["peers"] += [{"id": "loss", "metric_basis": spec["metric_basis"], "price": "10", "eps": "-2"},
                                              {"id": "trailing", "metric_basis": "TTM", "multiple": "2"}]
        result = value_comparables(spec)
        self.assertEqual(result["results"]["excluded_peers"], 2)
        self.assertTrue(all(row["reason"] for row in result["tables"]["peers"][-2:]))
        self.assertEqual(Decimal(result["results"]["selected_multiple"]), 14)

    def test_subject_negative_denominators_rejected(self):
        for method, field in (("pe", "earnings"), ("ev_ebitda", "ebitda")):
            for value in ("0", "-1"):
                spec = self.spec(method); spec["subject"][field] = value
                with self.assertRaisesRegex(ValidationError, "nonpositive denominator"): value_comparables(spec)

    def test_pe_bridge_rejected(self):
        spec = self.spec(); spec["subject"]["bridge"] = dcf_spec()["bridge"]
        with self.assertRaisesRegex(ValidationError, "already values common equity"): value_comparables(spec)

    def test_computed_multiples_and_even_median(self):
        spec = self.spec(); spec["peers"] = [{"id": "a", "metric_basis": spec["metric_basis"], "price": "30", "eps": "3"},
                                            {"id": "b", "metric_basis": spec["metric_basis"], "price": "72", "eps": "4"}]
        self.assertEqual(Decimal(value_comparables(spec)["results"]["selected_multiple"]), 14)
        spec["aggregation"] = "mean"
        self.assertEqual(Decimal(value_comparables(spec)["results"]["selected_multiple"]), 14)

    def test_all_invalid_peers_and_duplicate_rejected(self):
        spec = self.spec(); spec["peers"] = [{"id": "loss", "metric_basis": spec["metric_basis"], "price": "10", "eps": "0"}]
        with self.assertRaisesRegex(ValidationError, "loss"): value_comparables(spec)
        spec = self.spec(); spec["peers"].append(copy.deepcopy(spec["peers"][0]))
        with self.assertRaisesRegex(ValidationError, "duplicate"): value_comparables(spec)


class ScenarioTests(unittest.TestCase):
    def test_provenance_mapping_preserves_numbers_and_forecasts_are_derived(self):
        spec=scenario_spec(); reference=manufacturing_scenario(spec)
        spec["input_basis"]={"base.revenue":{"basis":"disclosed","rationale":"已读取基期披露"},
                             "baseline.0.volume":{"basis":"assumption","rationale":"明确销量假设"},
                             "dcf.discount.wacc":{"basis":"assumption","rationale":"研究折现率"}}
        spec["source_refs"]={"base.revenue":[{"kind":"document","id":"d1","locator":"page:2"}],
                             "baseline[0].volume":[{"kind":"document","id":"d1","locator":"page:3"}],
                             "baseline.0.unit_price":[{"kind":"document","id":"d1","locator":"page:3"}],
                             "dcf.discount.wacc":[{"kind":"source","id":"s1","locator":"p4"}],
                             "scenario.material_cost_changes.0":[{"kind":"source","id":"s2","locator":"p6"}]}
        before=copy.deepcopy(spec); result=manufacturing_scenario(spec)
        self.assertEqual(spec,before)
        self.assertEqual(reference["tables"],result["tables"])
        self.assertEqual(reference["results"]["scenario_valuation"],result["results"]["scenario_valuation"])
        for name in ("baseline_dcf_spec","scenario_dcf_spec"):
            generated=result["results"][name]
            self.assertEqual(generated["input_basis"]["base.revenue"]["basis"],"disclosed")
            self.assertEqual(generated["input_basis"]["discount.wacc"]["basis"],"assumption")
            self.assertEqual(generated["source_refs"]["discount.wacc"][0]["locator"],"p4")
            self.assertEqual(generated["input_basis"]["forecast.0.revenue"]["basis"],"derived")
            self.assertEqual(len(generated["source_refs"]["forecast.0.revenue"]),1)
            self.assertTrue(all(record["basis"]=="derived" for key,record in generated["input_basis"].items() if key.startswith("forecast.")))
            self.assertEqual(value_dcf(generated)["results"],result["results"]["scenario_valuation" if name.startswith("scenario") else "baseline_valuation"])
        scenario=result["results"]["scenario_dcf_spec"]
        # The first year's material shock affects the following year's selling price.
        self.assertIn({"kind":"source","id":"s2","locator":"p6"},scenario["source_refs"]["forecast.1.revenue"])
        self.assertNotIn({"kind":"source","id":"s2","locator":"p6"},scenario["source_refs"]["forecast.0.revenue"])

    def test_hand_worked_lag_exposure_and_elasticity(self):
        result = manufacturing_scenario(scenario_spec())
        first, second = result["tables"]["scenario"]
        # Baseline100units*$10, raw4, other2, fixed100 =>EBITDA300, EBIT250.
        # Exposed half of raw4 inflated20%=+0.4/unit. Year1 no pass-through =>EBIT210.
        # Year2 price10+.4*.5=10.2; linear elasticity-1 =>98units;
        # revenue999.6, cash variable627.2, fixed100, DA50 =>EBIT222.4.
        self.assertEqual(Decimal(first["baseline_ebit"]), 250)
        self.assertEqual(Decimal(first["scenario_ebit"]), 210)
        self.assertEqual(Decimal(first["price_pass_through_per_unit"]), 0)
        self.assertEqual(Decimal(second["scenario_unit_price"]), Decimal("10.2"))
        self.assertEqual(Decimal(second["scenario_volume"]), 98)
        self.assertEqual(Decimal(second["scenario_ebit"]), Decimal("222.4"))
        self.assertEqual(result["results"]["scenario_valuation"], value_dcf(result["results"]["scenario_dcf_spec"])["results"])

    def test_zero_shock_matches_baseline(self):
        spec = scenario_spec(); spec["scenario"]["material_cost_changes"] = ["0", "0"]
        result = manufacturing_scenario(spec)
        baseline, scenario = result["results"]["baseline_valuation"], result["results"]["scenario_valuation"]
        for key, value in baseline.items():
            if isinstance(value, str) and key != "cashflow_timing":
                self.assertEqual(Decimal(value), Decimal(scenario[key]))
            else:
                self.assertEqual(value, scenario[key])

    def test_shocks_are_baseline_levels_not_repeated_compounding(self):
        spec = scenario_spec(); spec["scenario"]["pass_through_rate"] = "0"; spec["scenario"]["price_elasticity"] = "0"
        result = manufacturing_scenario(spec)
        self.assertEqual(Decimal(result["tables"]["scenario"][0]["scenario_ebit"]), Decimal(result["tables"]["scenario"][1]["scenario_ebit"]))

    def test_immediate_full_pass_through_restores_unit_profit_if_no_elasticity(self):
        spec = scenario_spec(); spec["scenario"].update(lag_years=0, pass_through_rate="1", price_elasticity="0")
        rows = manufacturing_scenario(spec)["tables"]["scenario"]
        self.assertEqual(Decimal(rows[0]["scenario_ebit"]), 250)
        self.assertEqual(Decimal(rows[0]["scenario_revenue"]), 1040)

    def test_unknown_exposure_or_elasticity_not_invented(self):
        for key in ("exposed_material_share", "price_elasticity"):
            spec = scenario_spec(); del spec["scenario"][key]
            with self.assertRaisesRegex(ValidationError, key): manufacturing_scenario(spec)

    def test_invalid_linear_demand_and_missing_shock_rejected(self):
        spec = scenario_spec(); spec["scenario"]["autonomous_price_changes"] = ["2", "2"]
        with self.assertRaisesRegex(ValidationError, "nonpositive demand"): manufacturing_scenario(spec)
        spec = scenario_spec(); spec["scenario"]["volume_changes"] = ["0"]
        with self.assertRaisesRegex(ValidationError, "exactly 2"): manufacturing_scenario(spec)


class QualityTests(unittest.TestCase):
    def spec(self):
        return {"currency": "CNY", "amount_scale": "10000", "period_basis": "FY", "receivables_sales_basis": "credit_sales", "payables_cost_basis": "purchases",
                "periods": [{"year": 2024, "days": "360", "revenue": "1000", "net_income": "100"},
                            {"year": 2025, "days": "360", "revenue": "1200", "net_income": "120", "cfo": "150", "credit_sales": "1000", "cogs": "600", "purchases": "660", "capex": "50",
                             "receivables_begin": "80", "receivables_end": "120", "inventory_begin": "80", "inventory_end": "120",
                             "payables_begin": "50", "payables_end": "70", "assets_begin": "900", "assets_end": "1100"}]}

    def test_manual_ratios_and_cash_cycle(self):
        row = financial_quality(self.spec())["tables"]["quality"][1]
        expected = {"revenue_yoy": ".2", "net_income_yoy": ".2", "cash_conversion": "1.25", "cfo_margin": ".125",
                    "receivables_turnover": "10", "inventory_turnover": "6", "payables_turnover": "11", "dso": "36", "dio": "60",
                    "accruals_to_assets": "-.03", "cfo_less_capex": "100"}
        for key, value in expected.items():
            with self.subTest(key=key): self.assertEqual(Decimal(row[key]), Decimal(value))
        with localcontext() as ctx:
            ctx.prec = 50
            self.assertEqual(Decimal(row["cash_conversion_cycle"]), Decimal(696)/11)

    def test_no_implied_revenue_proxy(self):
        spec = self.spec(); del spec["periods"][1]["credit_sales"]
        row = financial_quality(spec)["tables"]["quality"][1]
        self.assertIsNone(row["receivables_turnover"]); self.assertIn("missing", row["receivables_turnover_reason"])
        spec["receivables_sales_basis"] = "revenue_proxy"
        self.assertEqual(Decimal(financial_quality(spec)["tables"]["quality"][1]["receivables_turnover"]), 12)

    def test_prior_loss_does_not_turn_loss_reduction_into_negative_growth(self):
        spec = self.spec(); spec["periods"][0]["net_income"] = "-100"; spec["periods"][1]["net_income"] = "-20"
        row = financial_quality(spec)["tables"]["quality"][1]
        self.assertEqual(Decimal(row["net_income_change"]), 80)
        self.assertIsNone(row["net_income_yoy"]); self.assertIsNone(row["cash_conversion"])
        self.assertEqual(row["net_income_yoy_reason"], "nonpositive denominator")

    def test_year_gap_not_yoy_and_empty_balance_not_zero(self):
        spec = self.spec(); spec["periods"][1]["year"] = 2026; del spec["periods"][1]["inventory_begin"]
        row = financial_quality(spec)["tables"]["quality"][1]
        self.assertIsNone(row["revenue_yoy"]); self.assertIsNone(row["inventory_turnover"])
        self.assertIsNone(row["cash_conversion_cycle"])

    def test_zero_inventory_turnover_days_unavailable(self):
        spec = self.spec(); spec["periods"][1]["cogs"] = "0"
        row = financial_quality(spec)["tables"]["quality"][1]
        self.assertEqual(Decimal(row["inventory_turnover"]), 0)
        self.assertIsNone(row["dio"]); self.assertEqual(row["dio_reason"], "nonpositive denominator")

    def test_dispatch_and_no_missing_policy_defaults(self):
        self.assertEqual(evaluate_model("financial_quality", self.spec())["kind"], "financial_quality")
        with self.assertRaises(ValidationError): evaluate_model("guessed_model", {})
        spec = self.spec(); del spec["period_basis"]
        with self.assertRaisesRegex(ValidationError, "period_basis"): financial_quality(spec)


class PublicSchemaTests(unittest.TestCase):
    def test_input_basis_metadata_requires_explicit_kind_and_rationale(self):
        from jsonschema import Draft202012Validator
        validator=Draft202012Validator(get_model_schema("dcf")); example=get_model_example("dcf")
        self.assertEqual(example["input_basis"]["base.revenue"]["basis"],"assumption")
        for invalid in ({"basis":"disclosed"},{"basis":"maybe","rationale":"unknown"},{"basis":"derived","rationale":""}):
            example["input_basis"]={"base.revenue":invalid}
            self.assertFalse(validator.is_valid(example))
        del example["input_basis"]
        self.assertTrue(validator.is_valid(example))

    def test_schemas_and_examples_are_executable(self):
        from jsonschema import Draft202012Validator
        for kind in SCHEMAS:
            with self.subTest(kind=kind):
                schema, example = get_model_schema(kind), get_model_example(kind)
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(example)
                result = evaluate_model(kind, example)
                self.assertEqual(result["kind"], kind)
                self.assertEqual(json.loads(export_json(result))["schema_version"], "1.0")

    def test_schema_forecast_exclusive_modes_and_pe_bridge(self):
        from jsonschema import Draft202012Validator
        example = get_model_example("dcf"); example["forecast"][0]["revenue"] = "123"
        self.assertFalse(Draft202012Validator(get_model_schema("dcf")).is_valid(example))
        example = get_model_example("comparables"); example["subject"]["bridge"] = dcf_spec()["bridge"]
        self.assertFalse(Draft202012Validator(get_model_schema("comparables")).is_valid(example))

    def test_schema_and_example_objects_do_not_leak_mutation(self):
        schema = get_model_schema("dcf"); schema["properties"]["currency"]["description"] = "changed"
        self.assertNotEqual(get_model_schema("dcf")["properties"]["currency"]["description"], "changed")
        example = get_model_example("dcf"); example["base"]["revenue"] = "9"
        self.assertEqual(get_model_example("dcf")["base"]["revenue"], "1000")


if __name__ == "__main__":
    unittest.main()

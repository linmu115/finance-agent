"""Offline diagnosis of the frozen first synthetic Pi workflow. Never rescoring it.

No application imports, network access, database writes, or model calls. Fractions
provide an independent arithmetic reference; original reports are read only.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / "benchmark/results/research-models-pi-workflow-v05"


def read(suffix):
    return json.loads(Path(str(PREFIX) + suffix).read_text(encoding="utf-8-sig"))


def decimal(value):
    with localcontext() as context:
        context.prec = 65
        return Decimal(value.numerator) / Decimal(value.denominator)


def differences(expected, actual, path=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        result = []
        for key in sorted(set(expected) | set(actual)):
            name = f"{path}.{key}" if path else key
            if key not in expected:
                result.append({"path": name, "change": "added", "actual": actual[key]})
            elif key not in actual:
                result.append({"path": name, "change": "missing", "expected": expected[key]})
            else:
                result.extend(differences(expected[key], actual[key], name))
        return result
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [item for i, (left, right) in enumerate(zip(expected, actual))
                for item in differences(left, right, f"{path}.{i}")]
    try:
        equal = F(str(expected)) == F(str(actual))
    except (ValueError, TypeError, ZeroDivisionError):
        equal = expected == actual
    return [] if equal else [{"path": path, "change": "different", "expected": expected, "actual": actual}]


def main():
    protected = [Path(str(PREFIX) + suffix) for suffix in (
        ".before.json", ".json", ".run-1.audit.json", ".run-2.audit.json")]
    hashes_before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    report, frozen = read(".json"), read(".before.json")
    audit_1, audit_2 = read(".run-1.audit.json"), read(".run-2.audit.json")
    artifacts = {a["kind"]: a for a in report["artifacts_before"]}
    scenario, dcf = artifacts["manufacturing_scenario"], artifacts["dcf"]
    assumptions = frozen["assumptions"]
    shock = assumptions["scenario"]
    calculations = []

    def check(path, actual, expected):
        actual_decimal = Decimal(str(actual))
        expected_decimal = decimal(expected)
        error = abs(actual_decimal - expected_decimal)
        calculations.append({"path": path, "actual": str(actual),
                             "reference": str(expected_decimal),
                             "reference_fraction": str(expected),
                             "absolute_error": str(error), "passed": error <= Decimal("1e-40")})

    def forecast(apply_shock):
        previous_nwc = F(assumptions["base"]["net_working_capital"])
        rows = []
        for i, row in enumerate(assumptions["baseline"]):
            # The frozen case uses shock levels, not compounded annual shocks.
            cost_change = F(row["material_cost_per_unit"]) * F(shock["exposed_material_share"]) * F(shock["material_cost_changes"][i]) if apply_shock else F(0)
            lag_index = i - shock["lag_years"]
            pass_through = (F(assumptions["baseline"][lag_index]["material_cost_per_unit"]) * F(shock["exposed_material_share"]) * F(shock["material_cost_changes"][lag_index]) * F(shock["pass_through_rate"])) if apply_shock and lag_index >= 0 else F(0)
            price = F(row["unit_price"]) + pass_through
            volume = F(row["volume"]) * (1 + F(shock["price_elasticity"]) * (price / F(row["unit_price"]) - 1)) if apply_shock else F(row["volume"])
            revenue = price * volume
            ebit = revenue - volume * (F(row["material_cost_per_unit"]) + cost_change + F(row["other_variable_cost_per_unit"])) - F(row["fixed_cash_opex"]) - F(row["da"])
            tax = max(F(0), ebit * F(row["tax_rate"]))
            nwc = revenue * F(row["nwc_ratio"])
            fcff = ebit - tax + F(row["da"]) - F(row["capex"]) - (nwc - previous_nwc)
            rows.append({"year": F(row["year"]), "revenue": revenue, "ebit": ebit,
                         "cash_tax": tax, "nopat": ebit - tax, "fcff": fcff,
                         "net_working_capital": nwc, "delta_nwc": nwc - previous_nwc})
            previous_nwc = nwc
            if apply_shock:
                observed = scenario["result"]["tables"]["scenario"][i]
                for name, value in {"scenario_volume": volume, "scenario_unit_price": price,
                                    "price_pass_through_per_unit": pass_through,
                                    "exposed_material_cost_change_per_unit": cost_change}.items():
                    check(f"scenario.tables.scenario.{i}.{name}", observed[name], value)
        return rows

    def valuation(rows, wacc, growth):
        terminal = assumptions["dcf"]["terminal"]
        terminal_revenue = rows[-1]["revenue"] * (1 + growth)
        terminal_nopat = terminal_revenue * F(terminal["ebit_margin"]) * (1 - F(terminal["tax_rate"]))
        reinvestment = terminal_nopat * growth / F(terminal["roic"])
        terminal_fcff = terminal_nopat - reinvestment
        terminal_value = terminal_fcff / (wacc - growth)
        pv = sum(row["fcff"] / ((1 + wacc) ** i) for i, row in enumerate(rows, 1))
        terminal_pv = terminal_value / ((1 + wacc) ** len(rows))
        enterprise = pv + terminal_pv
        bridge = assumptions["dcf"]["bridge"]
        equity = enterprise - F(bridge["net_debt"]) - F(bridge["non_controlling_interest"]) - F(bridge["preferred_equity"]) + F(bridge["non_operating_assets_ex_cash"])
        shares = F(assumptions["dcf"]["shares"]["count"]) * F(assumptions["dcf"]["shares"]["scale"])
        return {"enterprise_value": enterprise, "equity_value": equity,
                "value_per_share": equity / shares, "explicit_forecast_pv": pv,
                "terminal_value": terminal_value, "terminal_pv": terminal_pv,
                "terminal_revenue": terminal_revenue, "terminal_nopat": terminal_nopat,
                "terminal_reinvestment": reinvestment, "terminal_fcff": terminal_fcff}

    baseline, changed = forecast(False), forecast(True)
    for label, rows in (("baseline", baseline), ("scenario", changed)):
        for i, row in enumerate(rows):
            for key, expected in row.items():
                check(f"scenario.tables.{label}_forecast.{i}.{key}",
                      scenario["result"]["tables"][f"{label}_forecast"][i][key], expected)
        for wacc, artifact_label, observed in (
            (F("0.1"), "original", scenario["result"]["results"][f"{label}_valuation"]),
            (F("0.11"), "edited", report["host_edit"]["result"]["results"][f"{label}_valuation"]),
        ):
            for key, expected in valuation(rows, wacc, F("0.02")).items():
                check(f"{artifact_label}.results.{label}_valuation.{key}", observed[key], expected)
    for i, row in enumerate(changed):
        for key, expected in row.items():
            check(f"dcf.tables.forecast.{i}.{key}", dcf["result"]["tables"]["forecast"][i][key], expected)
    for key, expected in valuation(changed, F("0.1"), F("0.02")).items():
        check(f"dcf.results.{key}", dcf["result"]["results"][key], expected)
    for i, observed in enumerate(dcf["result"]["tables"]["sensitivity"]):
        reference = valuation(changed, F(observed["wacc"]), F(observed["growth"]))
        for key in ("enterprise_value", "equity_value", "value_per_share"):
            check(f"dcf.tables.sensitivity.{i}.{key}", observed[key], reference[key])

    expected_spec = scenario["result"]["results"]["scenario_dcf_spec"]
    metadata_keys = {"input_basis", "source_refs", "scenario_assumptions"}
    computational_diffs = differences({k: v for k, v in expected_spec.items() if k not in metadata_keys},
                                     {k: v for k, v in dcf["spec"].items() if k not in metadata_keys})
    results_2 = [e for e in audit_2 if e["type"] == "tool_result"]
    listed = [e for e in results_2 if e["data"]["name"] == "list_research_artifacts"]
    read_events = [e for e in results_2 if e["data"]["name"] == "read_research_artifact"]
    compact = lambda a: {k: a.get(k) for k in ("id", "kind", "revision_id", "dependency_status", "changed_dependencies")}
    second_reads = [compact(e["data"]["result"]["data"]) for e in read_events]
    second_listed = [compact(a) for e in listed for a in e["data"]["result"]["data"]["artifacts"]]
    budget_events = [e for e in audit_2 if e["type"] == "evaluation_budget"]
    output = {
        "kind": "post_run_readonly_diagnosis", "accuracy_holdout": False,
        "original_report": str(Path(str(PREFIX) + ".json").relative_to(ROOT)),
        "original_status_unchanged": report["status"],
        "original_checks": {"passed": sum(c["status"] == "passed" for c in report["checks"]), "total": len(report["checks"])},
        "limitations": ["This diagnosis does not replace or relax the frozen first-run checks.",
                        "Synthetic arithmetic and workflow development verification only; no independent financial-data accuracy claim.",
                        "No application code imports, model calls, database access, or server lifecycle operations."],
        "project_id": report["project_id"], "task_sha256": report["task_sha256"],
        "runs": [{"id": run["id"], "status": run["status"], "usage": run.get("usage")} for run in report["runs"]],
        "budget_last_event": budget_events[-1] if budget_events else None,
        "actual_failures": report["failures"],
        "failure_diagnosis": [
            {"check": "Exact scenario-to-DCF input preservation", "frozen_result": "failed",
             "computational_fields_identical": not computational_diffs, "computational_differences": computational_diffs,
             "all_spec_differences": differences(expected_spec, dcf["spec"]),
             "explanation": "All calculation inputs were preserved. Pi omitted scenario_assumptions and forecast year basis, and rewrote basis/rationale for other fields. These provenance differences remain a real exact-preservation failure; numerical equivalence does not turn it into a pass."},
            {"check": "Second conversation individually reads all four artifacts", "frozen_result": "failed",
             "listed_artifacts_with_real_dependency_state": second_listed,
             "individual_reads": second_reads,
             "not_individually_read": [artifacts[k]["id"] for k in ("industry_chain", "investment_memo")],
             "explanation": "The model obtained all four real dependency states from list_research_artifacts, and read scenario old/new revisions plus DCF. It did not individually read chain and memo content, so the original strict check remains failed. Its stale-status explanation nevertheless had real list-tool evidence."},
        ],
        "independent_arithmetic": {"method": "Python Fraction exact rational arithmetic from frozen synthetic assumptions; no production model implementation imported.",
                                   "absolute_tolerance": "1e-40", "checks": calculations,
                                   "passed": sum(c["passed"] for c in calculations), "total": len(calculations)},
        "implementation_changed_during_original_run": report["implementation_changed"],
        "protected_file_hashes": hashes_before,
    }
    hashes_after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert hashes_before == hashes_after, "Readonly diagnostic unexpectedly changed a protected file"
    output["protected_files_unchanged"] = True
    destination = Path(str(PREFIX) + ".diagnosis.json")
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": str(destination), "original_status": report["status"],
                      "calculation_inputs_identical": not computational_diffs,
                      "arithmetic_passed": output["independent_arithmetic"]["passed"],
                      "arithmetic_total": len(calculations), "protected_files_unchanged": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()

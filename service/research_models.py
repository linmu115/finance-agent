"""Deterministic, assumption-driven finance models. No database or model access.

Amounts retain the declared amount_scale; value_per_share is always currency / share.
See research_models_methods.txt for conventions, source references and input examples.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_EVEN
from functools import wraps
from typing import Any

VERSION = "research-models-1.2.0"
SCHEMA_VERSION = "1.0"
PRECISION = 50
ZERO = Decimal(0)
ONE = Decimal(1)
METHOD_SOURCES = {
    "three_statement": ["https://github.com/anthropics/financial-services"],
    "dcf": ["https://people.stern.nyu.edu/adamodar/pdfiles/valn2ed/ch15.pdf",
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/noncashwc.htm",
            "https://www.ifrs.org/content/dam/ifrs/supporting-implementation/ifrs-13/education-ifrs-13-eng.pdf"],
    "comparables": ["https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples"],
    "financial_quality": ["https://pages.stern.nyu.edu/~hfried/fsapdf/Ratios.PDF",
                          "https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques",
                          "https://www.mof.gov.cn/gkml/caizhengwengao/wg201901/2019wg03/201907/P020190709345883677352.pdf",
                          "https://www.ifrs.org/content/dam/ifrs/publications/amendments/english/2024/effect-analysis-ifrs18-april2024.pdf"],
    "manufacturing_scenario": ["https://people.stern.nyu.edu/adamodar/pdfiles/valn2ed/ch15.pdf"],
}


class ValidationError(ValueError):
    """An explicit input or model-domain error, suitable for display to the user."""


def _decimal(value: Any, name: str) -> Decimal:
    # Decimal(str(float)) preserves the JSON number's visible decimal representation;
    # callers needing exact significant digits should send strings.
    if isinstance(value, bool) or value is None or not isinstance(value, (str, int, float, Decimal)):
        raise ValidationError(f"{name}: provide a finite decimal number, preferably a string")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f"{name}: invalid decimal number") from exc
    if not number.is_finite():
        raise ValidationError(f"{name}: NaN and infinity are not valid inputs")
    if number and (number.adjusted() > 100 or number.adjusted() < -100):
        raise ValidationError(f"{name}: magnitude outside supported decimal range 1e-100..1e100")
    return number


def _num(obj: dict, key: str, *, minimum=None, maximum=None, positive=False, path="") -> Decimal:
    name = f"{path}.{key}" if path else key
    value = _decimal(obj.get(key), name)
    if positive and value <= 0:
        raise ValidationError(f"{name}: must be greater than zero")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{name}: must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{name}: must be at most {maximum}")
    return value


def _obj(value, name):
    if not isinstance(value, dict):
        raise ValidationError(f"{name}: expected an object")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name}: nonempty text is required")
    return value


def _integer(value, name, minimum=0, maximum=9999):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f"{name}: expected integer {minimum}..{maximum}")
    return value


def _choice(value, choices, name):
    if value not in choices:
        raise ValidationError(f"{name}: choose one of {', '.join(choices)}")
    return value


def _rows(value, name):
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{name}: a nonempty array is required")
    for i, row in enumerate(value):
        _obj(row, f"{name}[{i}]")
    return value


def _json(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, float):
        return format(_decimal(value, "input"), "f")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValidationError(f"input: unsupported value type {type(value).__name__}")


def _calculation(fn):
    @wraps(fn)
    def wrapped(spec):
        _obj(spec, "spec")
        with localcontext() as ctx:
            ctx.prec = PRECISION
            ctx.rounding = ROUND_HALF_EVEN
            return _json(fn(copy.deepcopy(spec)))
    return wrapped


def _units(spec):
    currency = _text(spec.get("currency"), "currency")
    scale = _num(spec, "amount_scale", positive=True)
    return {"currency": currency, "amount_scale": scale, "amount": f"{currency} x {scale}",
            "ratios": "decimal fraction (0.10 = 10%)", "multiple": "times",
            "value_per_share": f"{currency}/share", "days": "days"}


def _result(kind, spec, formulas, results, tables, warnings=None):
    from .model_review import review_model
    checks, usage = review_model(kind, spec)
    return {"schema_version": SCHEMA_VERSION, "model_version": VERSION, "kind": kind,
            "input_assumptions": spec, "formulas": formulas, "units": _units(spec),
            "precision": {"arithmetic": "Decimal", "significant_digits": PRECISION,
                          "rounding": "ROUND_HALF_EVEN", "output": "decimal strings; no additional display rounding"},
            "method_sources": METHOD_SOURCES[kind][:],
            "results": results, "tables": tables, "warnings": warnings or [],
            "checks": checks, "input_usage": usage}


def _shares(shares):
    shares = _obj(shares, "shares")
    return _num(shares, "count", positive=True, path="shares") * _num(shares, "scale", positive=True, path="shares")


def _bridge(bridge):
    bridge = _obj(bridge, "bridge")
    allowed = {"net_debt", "non_controlling_interest", "preferred_equity", "non_operating_assets_ex_cash"}
    unknown = set(bridge) - allowed
    if unknown:
        raise ValidationError("bridge: use net_debt (debt less excess cash) once; unsupported fields: " + ", ".join(sorted(unknown)))
    return {name: _num(bridge, name, minimum=None if name == "net_debt" else ZERO, path="bridge") for name in sorted(allowed)}


def _equity(ev, bridge, shares, scale):
    equity = ev - bridge["net_debt"] - bridge["non_controlling_interest"] - bridge["preferred_equity"] + bridge["non_operating_assets_ex_cash"]
    return {"enterprise_value": ev, "equity_value": equity, "value_per_share": equity * scale / shares,
            "shares_outstanding": shares, **bridge}


def _cash_tax(ebit, rate, policy):
    return (max(ebit, ZERO) if policy == "floor_at_zero" else ebit) * rate


def _amount_or_ratio(row, amount_key, ratio_key, revenue, path, nonnegative=True):
    if (amount_key in row) == (ratio_key in row):
        raise ValidationError(f"{path}: provide exactly one of {amount_key}, {ratio_key}")
    minimum = ZERO if nonnegative else None
    return _num(row, amount_key, minimum=minimum, path=path) if amount_key in row else revenue * _num(row, ratio_key, minimum=minimum, path=path)


def _forecast(spec):
    base = _obj(spec.get("base"), "base")
    revenue = _num(base, "revenue", positive=True, path="base")
    nwc = _num(base, "net_working_capital", path="base")
    base_year = _integer(spec.get("base_year"), "base_year", 1900)
    policy = _choice(spec.get("cash_tax_policy"), ("floor_at_zero", "immediate_credit"), "cash_tax_policy")
    forecast = []
    for i, row in enumerate(_rows(spec.get("forecast"), "forecast")):
        path = f"forecast[{i}]"
        year = _integer(row.get("year"), f"{path}.year", 1900)
        if year != base_year + i + 1:
            raise ValidationError(f"{path}.year: annual forecasts must start base_year + 1 and remain contiguous")
        old_revenue = revenue
        if ("revenue" in row) == ("revenue_growth" in row):
            raise ValidationError(f"{path}: provide exactly one of revenue, revenue_growth")
        if "revenue" in row:
            revenue = _num(row, "revenue", positive=True, path=path)
        else:
            growth = _num(row, "revenue_growth", minimum=-ONE, path=path)
            revenue *= ONE + growth
            if revenue <= 0:
                raise ValidationError(f"{path}.revenue_growth: revenue must remain positive")
        modes = int("ebit" in row) + int("ebit_margin" in row) + int("gross_margin" in row or "opex_ratio" in row)
        if modes != 1:
            raise ValidationError(f"{path}: provide ebit OR ebit_margin OR gross_margin + opex_ratio")
        gross_profit = None
        if "ebit" in row:
            ebit = _num(row, "ebit", path=path)
        elif "ebit_margin" in row:
            ebit = revenue * _num(row, "ebit_margin", maximum=ONE, path=path)
        else:
            gross_profit = revenue * _num(row, "gross_margin", maximum=ONE, path=path)
            ebit = gross_profit - revenue * _num(row, "opex_ratio", minimum=ZERO, path=path)
        if ebit > revenue:
            raise ValidationError(f"{path}.ebit: operating EBIT cannot exceed revenue in this operating-only model")
        rate = _num(row, "tax_rate", minimum=ZERO, maximum=ONE, path=path)
        da = _amount_or_ratio(row, "da", "da_ratio", revenue, path)
        capex = _amount_or_ratio(row, "capex", "capex_ratio", revenue, path)
        new_nwc = _amount_or_ratio(row, "net_working_capital", "nwc_ratio", revenue, path, nonnegative=False)
        tax = _cash_tax(ebit, rate, policy)
        delta_nwc = new_nwc - nwc
        nopat = ebit - tax
        forecast.append({"year": year, "revenue": revenue, "revenue_growth": revenue / old_revenue - ONE,
                         "gross_profit": gross_profit, "ebit": ebit, "ebit_margin": ebit / revenue,
                         "ebitda": ebit + da, "cash_tax": tax, "nopat": nopat, "da": da, "capex": capex,
                         "net_working_capital": new_nwc, "delta_nwc": delta_nwc,
                         "fcff": nopat + da - capex - delta_nwc})
        nwc = new_nwc
    return forecast


DCF_FORMULAS = {
    "revenue": "revenue[t-1] * (1 + revenue_growth[t]), or explicit revenue[t]",
    "ebit": "explicit EBIT; or revenue * EBIT margin; or revenue * (gross margin - opex ratio). EBIT is after D&A.",
    "cash_tax": "floor_at_zero: max(EBIT,0)*tax_rate; immediate_credit: EBIT*tax_rate. No NOL carryforward is modeled.",
    "fcff": "EBIT - cash_tax + D&A - capex - (operating NWC[t] - operating NWC[t-1])",
    "nwc": "Operating non-cash, non-interest-bearing working capital. Negative balances are allowed.",
    "forecast_pv": "FCFF[t]/(1+WACC)^t; mid_year uses exponent t-0.5 for explicit forecast only",
    "terminal_fcff": "revenue[n]*(1+g)*terminal_EBIT_margin*(1-terminal_tax_rate)*(1-g/terminal_ROIC)",
    "terminal_value": "terminal_FCFF/(WACC-g); always measured at end of year n, discounted by (1+WACC)^n",
    "enterprise_value": "sum(explicit forecast PV) + terminal_value PV; value of operating assets",
    "equity_value": "EV - net_debt - non_controlling_interest - preferred_equity + non_operating_assets_ex_cash",
    "net_debt": "interest-bearing debt (consistent lease treatment) less excess cash; cash is not added again",
    "value_per_share": "equity_value * amount_scale / (shares.count * shares.scale)",
}


def _discounted(forecast, terminal, wacc, growth, timing, bridge, shares, scale):
    if wacc <= 0 or growth < 0 or growth >= wacc:
        raise ValidationError("discount/terminal: require WACC > 0 and 0 <= terminal growth < WACC")
    roic = _num(terminal, "roic", positive=True, path="terminal")
    if growth > roic:
        raise ValidationError("terminal: growth must not exceed ROIC (stable reinvestment fraction cannot exceed 1)")
    margin = _num(terminal, "ebit_margin", positive=True, maximum=ONE, path="terminal")
    rate = _num(terminal, "tax_rate", minimum=ZERO, maximum=ONE, path="terminal")
    rows = []
    for i, row in enumerate(forecast, 1):
        exponent = Decimal(i) - (Decimal("0.5") if timing == "mid_year" else ZERO)
        factor = ONE / ((ONE + wacc) ** exponent)
        rows.append({**row, "discount_exponent": exponent, "discount_factor": factor, "pv_fcff": row["fcff"] * factor})
    terminal_revenue = forecast[-1]["revenue"] * (ONE + growth)
    terminal_nopat = terminal_revenue * margin * (ONE - rate)
    reinvestment = terminal_nopat * growth / roic
    terminal_fcff = terminal_nopat - reinvestment
    terminal_value = terminal_fcff / (wacc - growth)
    terminal_pv = terminal_value / ((ONE + wacc) ** len(forecast))
    explicit_pv = sum((row["pv_fcff"] for row in rows), ZERO)
    ev = explicit_pv + terminal_pv
    result = {**_equity(ev, bridge, shares, scale), "explicit_forecast_pv": explicit_pv,
              "terminal_value": terminal_value, "terminal_pv": terminal_pv,
              "terminal_value_share": terminal_pv / ev if ev != 0 else None,
              "terminal_year": forecast[-1]["year"] + 1, "terminal_revenue": terminal_revenue,
              "terminal_nopat": terminal_nopat, "terminal_reinvestment": reinvestment,
              "terminal_reinvestment_rate": growth / roic, "terminal_fcff": terminal_fcff,
              "wacc": wacc, "terminal_growth": growth, "cashflow_timing": timing,
              "terminal_discount_exponent": len(forecast)}
    return result, rows


@_calculation
def value_dcf(spec):
    units = _units(spec)
    forecast = _forecast(spec)
    discount = _obj(spec.get("discount"), "discount")
    wacc = _num(discount, "wacc", positive=True, path="discount")
    timing = _choice(discount.get("cashflow_timing"), ("year_end", "mid_year"), "discount.cashflow_timing")
    terminal = _obj(spec.get("terminal"), "terminal")
    growth = _num(terminal, "growth", minimum=ZERO, path="terminal")
    bridge = _bridge(spec.get("bridge"))
    shares = _shares(spec.get("shares"))
    result, rows = _discounted(forecast, terminal, wacc, growth, timing, bridge, shares, units["amount_scale"])
    sensitivities = []
    if "sensitivity" in spec:
        sensitivity = _obj(spec["sensitivity"], "sensitivity")
        for key in ("wacc", "growth"):
            if not isinstance(sensitivity.get(key), list) or not sensitivity[key]:
                raise ValidationError(f"sensitivity.{key}: nonempty decimal array required")
        for raw_wacc in sensitivity["wacc"]:
            for raw_growth in sensitivity["growth"]:
                sw = _decimal(raw_wacc, "sensitivity.wacc")
                sg = _decimal(raw_growth, "sensitivity.growth")
                try:
                    sr, _ = _discounted(forecast, terminal, sw, sg, timing, bridge, shares, units["amount_scale"])
                    sensitivities.append({"wacc": sw, "growth": sg, "status": "ok", "reason": None,
                                          **{key: sr[key] for key in ("enterprise_value", "equity_value", "value_per_share")}})
                except ValidationError as exc:
                    sensitivities.append({"wacc": sw, "growth": sg, "status": "invalid", "reason": str(exc),
                                          "enterprise_value": None, "equity_value": None, "value_per_share": None})
    valid=[cell['value_per_share'] for cell in sensitivities if cell['status']=='ok']
    if valid:
        result['sensitivity_range']={'minimum':min(valid),'maximum':max(valid),'valid_cells':len(valid)}
    if 'reference_value_per_share' in spec:
        reference=_num(spec,'reference_value_per_share')
        result['reference_comparison']={'reference':reference,'model_minus_reference':result['value_per_share']-reference,
            'sensitivity_contains_reference':min(valid)<=reference<=max(valid) if valid else None,
            'range_position':('below' if reference<min(valid) else 'above' if reference>max(valid) else 'inside') if valid else 'unavailable'}
    warnings = ["Stable terminal model requires nonnegative growth, positive ROIC, and normalized operating earnings; banking/insurance balance-sheet models are outside this model."]
    if result["equity_value"] < 0:
        warnings.append("The arithmetic equity residual is negative; it is not an option-theoretic common-stock market price and has not been floored to zero.")
    if spec["cash_tax_policy"] == "immediate_credit":
        warnings.append("Negative EBIT produces an immediate tax credit by explicit assumption; tax-loss carryforwards are not modeled.")
    return _result("dcf", spec, DCF_FORMULAS, result, {"forecast": rows, "sensitivity": sensitivities}, warnings)


@_calculation
def value_comparables(spec):
    units = _units(spec)
    method = _choice(spec.get("method"), ("pe", "ev_ebitda"), "method")
    aggregation = _choice(spec.get("aggregation"), ("median", "mean"), "aggregation")
    basis = _text(spec.get("metric_basis"), "metric_basis")
    subject = _obj(spec.get("subject"), "subject")
    denominator_key = "earnings" if method == "pe" else "ebitda"
    denominator = _num(subject, denominator_key, path="subject")
    if denominator <= 0:
        raise ValidationError(f"subject.{denominator_key}: nonpositive denominator cannot support {method} valuation")
    shares = _shares(subject.get("shares"))
    if method == "pe" and "bridge" in subject:
        raise ValidationError("subject.bridge: P/E already values common equity; do not subtract net debt again")
    bridge = _bridge(subject.get("bridge")) if method == "ev_ebitda" else None
    rows, multiples, seen = [], [], set()
    for i, peer in enumerate(_rows(spec.get("peers"), "peers")):
        peer_id = _text(peer.get("id"), f"peers[{i}].id")
        if peer_id in seen:
            raise ValidationError(f"peers: duplicate peer id {peer_id}")
        seen.add(peer_id)
        try:
            if peer.get("metric_basis") != basis:
                raise ValidationError("metric_basis differs from the subject; trailing/forward and adjustment bases must match explicitly")
            numeric_fields = {"multiple", "price", "eps", "enterprise_value", "ebitda"} & set(peer)
            if "multiple" in peer:
                if numeric_fields != {"multiple"}:
                    raise ValidationError("provide a supplied multiple OR its matching numerator and denominator")
                multiple = _num(peer, "multiple", positive=True)
            elif method == "pe":
                if numeric_fields != {"price", "eps"}:
                    raise ValidationError("P/E peer requires price and eps in the same currency per share")
                multiple = _num(peer, "price", minimum=ZERO) / _num(peer, "eps", positive=True)
            else:
                if numeric_fields != {"enterprise_value", "ebitda"}:
                    raise ValidationError("EV/EBITDA peer requires enterprise_value and ebitda in the same amount unit")
                multiple = _num(peer, "enterprise_value", minimum=ZERO) / _num(peer, "ebitda", positive=True)
            if multiple <= 0:
                raise ValidationError("nonpositive multiple is outside the comparable valuation model")
            multiples.append(multiple)
            rows.append({"id": peer_id, "multiple": multiple, "status": "included", "reason": None})
        except ValidationError as exc:
            rows.append({"id": peer_id, "multiple": None, "status": "excluded", "reason": str(exc)})
    if not multiples:
        raise ValidationError("peers: no usable positive, same-basis multiple; " + "; ".join(f"{row['id']}: {row['reason']}" for row in rows))
    ordered = sorted(multiples)
    middle = len(ordered) // 2
    chosen = (sum(ordered, ZERO) / len(ordered)) if aggregation == "mean" else (ordered[middle] if len(ordered) % 2 else (ordered[middle-1] + ordered[middle]) / 2)
    def implied(multiple):
        raw_value = multiple * denominator
        if bridge is not None:
            return _equity(raw_value, bridge, shares, units["amount_scale"])
        return {"enterprise_value": None, "equity_value": raw_value,
                "value_per_share": raw_value * units["amount_scale"] / shares, "shares_outstanding": shares}
    result = {"method": method, "metric_basis": basis, "aggregation": aggregation,
              "selected_multiple": chosen, "included_peers": len(multiples), "excluded_peers": len(rows)-len(multiples), **implied(chosen)}
    for row in rows:
        if row["multiple"] is not None:
            row.update(implied(row["multiple"]))
    formulas = {"pe": "P/E=price/EPS; common equity=multiple*earnings attributable to ordinary shareholders; no EV-to-equity bridge",
                "ev_ebitda": "EV/EBITDA=enterprise value/EBITDA; subject EV=multiple*subject EBITDA; then apply EV-to-equity bridge",
                "aggregate": "Unweighted arithmetic mean or median of included positive, explicitly same-basis multiples",
                "equity_bridge": DCF_FORMULAS["equity_value"], "value_per_share": DCF_FORMULAS["value_per_share"]}
    return _result("comparables", spec, formulas, result, {"peers": rows},
                   ["Peer selection, dates, accounting adjustments, currency consistency within each peer, and business comparability are explicit analyst inputs; a matching basis label does not independently establish economic comparability."])


def _vector(scenario, key, count):
    values = scenario.get(key)
    if not isinstance(values, list) or len(values) != count:
        raise ValidationError(f"scenario.{key}: provide exactly {count} annual values, relative to each year's baseline")
    return [_decimal(value, f"scenario.{key}[{i}]") for i, value in enumerate(values)]


def _scenario_dcf_provenance(spec, scenario_applied):
    """Map evidence to computed DCF inputs without turning forecasts into disclosures."""
    def paths(value):
        if not isinstance(value, dict): return {}
        return {re.sub(r"\[(\d+)\]", r".\1", key.removeprefix("$.") if isinstance(key, str) else str(key)): item for key,item in value.items()}
    source_basis, source_refs = paths(spec.get("input_basis")), paths(spec.get("source_refs"))
    basis, refs = {}, {}
    for mapping, output in ((source_basis,basis),(source_refs,refs)):
        for key,value in mapping.items():
            target = key[4:] if key.startswith("dcf.") else key if key in {"currency","amount_scale","base_year"} or key.startswith("base.") else None
            if target is not None: output[target] = copy.deepcopy(value)
    def assign(target, inputs, rationale):
        basis[target] = {"basis":"derived","rationale":rationale + " 预测基线及冲击参数是建模输入；计算结果不代表未来已披露事实。"}
        evidence, seen = [], set()
        for key in inputs:
            for item in source_refs.get(key,[]) if isinstance(source_refs.get(key,[]),list) else []:
                signature=json.dumps(item,ensure_ascii=False,sort_keys=True)
                if signature not in seen: evidence.append(copy.deepcopy(item));seen.add(signature)
        if evidence: refs[target]=evidence
    lag=spec["scenario"]["lag_years"]
    for index,_ in enumerate(spec["baseline"]):
        prefix=f"baseline.{index}."
        revenue=[prefix+"volume",prefix+"unit_price"]
        shock=[]
        if scenario_applied:
            shock=[f"scenario.volume_changes.{index}",f"scenario.autonomous_price_changes.{index}","scenario.price_elasticity"]
            if index>=lag:
                shock += [f"baseline.{index-lag}.material_cost_per_unit",f"scenario.material_cost_changes.{index-lag}","scenario.exposed_material_share","scenario.pass_through_rate","scenario.lag_years"]
        assign(f"forecast.{index}.revenue",revenue+shock,"由预测销量乘销售单价计算收入" + ("，并应用提价、需求弹性和成本传导时滞。" if scenario_applied else "。"))
        ebit_inputs=revenue+shock+[prefix+key for key in ("material_cost_per_unit","other_variable_cost_per_unit","fixed_cash_opex","da")]
        if scenario_applied: ebit_inputs += ["scenario.exposed_material_share",f"scenario.material_cost_changes.{index}"]
        assign(f"forecast.{index}.ebit",ebit_inputs,"由预测收入扣除原料及其他变动成本、固定现金费用和一次折旧摊销计算 EBIT。")
        for key in ("year","da","capex","tax_rate","nwc_ratio"):
            assign(f"forecast.{index}.{key}",[prefix+key],f"从 {prefix+key} 预测输入映射；该情景不改变此项设定。")
    return {"input_basis":basis,"source_refs":refs}


@_calculation
def manufacturing_scenario(spec):
    _units(spec)
    baseline = _rows(spec.get("baseline"), "baseline")
    scenario = _obj(spec.get("scenario"), "scenario")
    base_year = _integer(spec.get("base_year"), "base_year", 1900)
    exposure = _num(scenario, "exposed_material_share", minimum=ZERO, maximum=ONE, path="scenario")
    pass_through = _num(scenario, "pass_through_rate", minimum=ZERO, maximum=ONE, path="scenario")
    lag = _integer(scenario.get("lag_years"), "scenario.lag_years", 0, len(baseline))
    elasticity = _num(scenario, "price_elasticity", maximum=ZERO, path="scenario")
    shocks = {key: _vector(scenario, key, len(baseline)) for key in ("material_cost_changes", "volume_changes", "autonomous_price_changes")}
    if any(value <= -ONE for values in shocks.values() for value in values):
        raise ValidationError("scenario: material cost, volume and autonomous price changes must be greater than -1")
    material_deltas = []
    rows, baseline_forecast, scenario_forecast = [], [], []
    for i, base_row in enumerate(baseline):
        path = f"baseline[{i}]"
        year = _integer(base_row.get("year"), path + ".year", 1900)
        if year != base_year+i+1:
            raise ValidationError("baseline: contiguous annual years starting base_year + 1 required")
        volume = _num(base_row, "volume", positive=True, path=path)
        price = _num(base_row, "unit_price", positive=True, path=path)
        material = _num(base_row, "material_cost_per_unit", minimum=ZERO, path=path)
        other = _num(base_row, "other_variable_cost_per_unit", minimum=ZERO, path=path)
        fixed = _num(base_row, "fixed_cash_opex", minimum=ZERO, path=path)
        da = _num(base_row, "da", minimum=ZERO, path=path)
        capex = _num(base_row, "capex", minimum=ZERO, path=path)
        tax = _num(base_row, "tax_rate", minimum=ZERO, maximum=ONE, path=path)
        nwc_ratio = _num(base_row, "nwc_ratio", path=path)
        delta = material * exposure * shocks["material_cost_changes"][i]
        material_deltas.append(delta)
        passed_cost = material_deltas[i-lag] * pass_through if i >= lag else ZERO
        changed_price = price * (ONE+shocks["autonomous_price_changes"][i]) + passed_cost
        if changed_price <= 0:
            raise ValidationError(f"{path}: scenario price is nonpositive after cost pass-through")
        price_change = changed_price/price - ONE
        demand_factor = ONE + elasticity * price_change
        if demand_factor <= 0:
            raise ValidationError(f"{path}: linear price-elasticity approximation produces nonpositive demand; revise explicit assumptions")
        changed_volume = volume * (ONE+shocks["volume_changes"][i]) * demand_factor
        brevenue = volume * price
        srevenue = changed_volume * changed_price
        bebitda = brevenue - volume*(material+other) - fixed
        sebitda = srevenue - changed_volume*(material+delta+other) - fixed
        common = {"year": year, "da": da, "capex": capex, "tax_rate": tax, "nwc_ratio": nwc_ratio}
        baseline_forecast.append({**common, "revenue": brevenue, "ebit": bebitda-da})
        scenario_forecast.append({**common, "revenue": srevenue, "ebit": sebitda-da})
        rows.append({"year": year, "baseline_volume": volume, "scenario_volume": changed_volume,
                     "baseline_unit_price": price, "scenario_unit_price": changed_price,
                     "exposed_material_cost_change_per_unit": delta, "price_pass_through_per_unit": passed_cost,
                     "demand_factor": demand_factor, "baseline_revenue": brevenue, "scenario_revenue": srevenue,
                     "baseline_ebitda": bebitda, "scenario_ebitda": sebitda,
                     "baseline_ebit": bebitda-da, "scenario_ebit": sebitda-da,
                     "revenue_change": srevenue-brevenue, "ebit_change": sebitda-bebitda})
    dcf = _obj(spec.get("dcf"), "dcf")
    allowed = {"cash_tax_policy", "discount", "terminal", "bridge", "shares", "sensitivity"}
    if set(dcf) - allowed:
        raise ValidationError("dcf: scenario supplies base/forecast/units; unknown or conflicting fields: " + ", ".join(sorted(set(dcf)-allowed)))
    common = {**dcf, "currency": spec["currency"], "amount_scale": spec["amount_scale"],
              "base_year": base_year, "base": _obj(spec.get("base"), "base"),
              "source_refs": spec.get("source_refs", {}), "scenario_assumptions": scenario}
    bspec = {**common, "forecast": baseline_forecast, **_scenario_dcf_provenance(spec, False)}
    sspec = {**common, "forecast": scenario_forecast, **_scenario_dcf_provenance(spec, True)}
    bvalue, svalue = value_dcf(bspec), value_dcf(sspec)
    results = {"baseline_dcf_spec": bspec, "scenario_dcf_spec": sspec,
               "baseline_valuation": bvalue["results"], "scenario_valuation": svalue["results"],
               "equity_value_change": _decimal(svalue["results"]["equity_value"], "scenario equity")-_decimal(bvalue["results"]["equity_value"], "baseline equity")}
    formulas = {"material_cost": "baseline_material_cost_per_unit * (1 + exposed_material_share * material_cost_change[t])",
                "price": "baseline_price[t]*(1+autonomous_price_change[t]) + pass_through_rate * exposed_absolute_material_cost_change_per_unit[t-lag]; pre-horizon changes are zero",
                "volume": "baseline_volume[t]*(1+exogenous_volume_change[t])*(1 + price_elasticity*(scenario_price[t]/baseline_price[t]-1))",
                "ebitda": "volume*(unit_price-material_cost_per_unit-other_variable_cost_per_unit)-fixed_cash_opex",
                "ebit": "EBITDA-D&A; forecast flows feed the same FCFF DCF function",
                "shock_basis": "All shock arrays are levels relative to that year's explicit baseline, not cumulatively compounded increments"}
    warnings = ["This is a user-specified linear demand and cost-pass-through scenario, not an estimated causal relationship.",
                "Other unit variable costs, fixed cash operating costs, D&A, capex and operating NWC/revenue ratios are held at each year's supplied baseline. Terminal margin/tax/ROIC assumptions are shared between scenarios."]
    out = _result("manufacturing_scenario", spec, formulas, results,
                  {"scenario": rows, "baseline_forecast": bvalue["tables"]["forecast"], "scenario_forecast": svalue["tables"]["forecast"]}, warnings)
    out["units"]["volume"] = _text(spec.get("volume_unit"), "volume_unit")
    out["units"]["unit_price"] = f"{spec['currency']} x {spec['amount_scale']}/{spec['volume_unit']}"
    return out


QUALITY_FORMULAS = {
    "revenue_yoy": "(revenue[t]-revenue[t-1])/revenue[t-1], consecutive fiscal years and positive prior base",
    "net_income_yoy": "(net_income[t]-net_income[t-1])/net_income[t-1], consecutive fiscal years and positive prior base",
    "cash_conversion": "cash flow from operations / net income (positive earnings denominator required)",
    "cfo_margin": "cash flow from operations / revenue",
    "receivables_turnover": "credit_sales / ((receivables_begin+receivables_end)/2); total revenue only if explicit revenue_proxy basis",
    "inventory_turnover": "cost_of_goods_sold / ((inventory_begin+inventory_end)/2)",
    "payables_turnover": "purchases / ((payables_begin+payables_end)/2); COGS only if explicit cogs_proxy basis",
    "dso": "period_days / receivables_turnover", "dio": "period_days / inventory_turnover",
    "dpo": "period_days / payables_turnover", "cash_conversion_cycle": "DSO+DIO-DPO",
    "accruals_to_assets": "(net_income-CFO)/((assets_begin+assets_end)/2)",
    "cfo_less_capex": "CFO-capex (not FCFF: interest/tax classification may differ)",
    "cash_profit_gap": "CFO - net_income, same period and entity scope",
    "recurring_net_income": "net_income - nonrecurring_net_income; both after-tax and same ownership scope",
    "working_capital_change": "receivables_end-receivables_begin + inventory_end-inventory_begin - payables_end+payables_begin; this is a disclosed-subset change, not all operating working capital",
    "profit_bridge": "Use the explicit reported_operating_profit or EBIT anchor, not an interchangeable label. Delta anchor = delta revenue - delta COGS - delta opex + delta other_operating_income - delta separately included finance_expense + delta explicit EBIT adjustments + residual. Finance already in opex is not deducted again; excluded finance is not part of this bridge.",
    "ebit_reconciliation": "EBIT = reported_operating_profit + sum(named signed ebit_adjustments). Each adjustment has a basis and rationale; no automatic addback of the entire finance_expense. Alternatively use explicitly disclosed EBIT or an explicitly labeled model assumption.",
    "finance_expense": "Signed statement expense: positive reduces profit, negative increases it when included. Net interest expense = interest_expense - interest_income only if both are supplied. Finance expense less net interest expense is an unclassified remainder; it is not automatically FX or interest income.",
    "price_volume": "volume effect=(Q1-Q0)*(P1+P0)/2; price effect=(P1-P0)*(Q1+Q0)/2; delta reported revenue - both effects = explicit residual. Symmetric allocation splits the price-volume interaction equally; never add this nested revenue bridge to the full profit bridge twice.",
}


def _quality_profit_contract(spec, periods):
    contract = spec.get("profit_bridge")
    has_profit = any(any(key in row for key in ("reported_operating_profit", "ebit", "ebit_adjustments")) for row in periods)
    if contract is None:
        if has_profit:
            raise ValidationError("profit_bridge: specify anchor, definition and expense scope; reported operating profit is not automatically EBIT. Existing saved results retain their original model version.")
        return None
    contract = _obj(contract, "profit_bridge")
    _choice(contract.get("anchor"), ("reported_operating_profit", "ebit"), "profit_bridge.anchor")
    for name in ("definition", "opex_definition", "other_operating_income_definition"):
        _text(contract.get(name), "profit_bridge." + name)
    _choice(contract.get("finance_expense_treatment"), ("separate", "included_in_opex", "excluded"), "profit_bridge.finance_expense_treatment")
    return contract


def _quality_basis(spec, value, path):
    value = _obj(value, path)
    basis = _choice(value.get("basis"), ("disclosed", "derived", "assumption"), path + ".basis")
    _text(value.get("rationale"), path + ".rationale")
    if basis != "assumption":
        refs = spec.get("source_refs", {}).get(path, [])
        if not isinstance(refs, list) or not any(isinstance(ref, dict) and ref.get("kind") in ("source", "document", "artifact") and ref.get("id") and ref.get("locator") for ref in refs):
            raise ValidationError(path + ": disclosed/derived EBIT basis requires a located reference in source_refs at this exact path; assumptions must be labeled assumption")
    return copy.deepcopy(value)


def _quality_profit_values(spec, contract, raw, values, path):
    """Keep source anchors distinct; reconcile only explicitly supplied adjustments."""
    extra = {}
    if not contract:
        return extra
    if contract["anchor"] == "reported_operating_profit":
        if "ebit" in raw or "ebit_adjustments" in raw or "ebit_basis" in raw:
            raise ValidationError(path + ": reported_operating_profit anchor must not use EBIT fields; choose the actual source subtotal")
        return extra
    if "ebit_adjustments" in raw:
        if "ebit_basis" in raw:
            raise ValidationError(path + ": choose disclosed/assumed EBIT or an adjustment reconciliation, not both")
        base = _num(raw, "reported_operating_profit", path=path)
        adjustments = _rows(raw["ebit_adjustments"], path + ".ebit_adjustments")
        total = ZERO
        checked = []
        for index, adjustment in enumerate(adjustments):
            apath = f"{path}.ebit_adjustments.{index}"
            _text(adjustment.get("label"), apath + ".label")
            basis = _quality_basis(spec, adjustment, apath)
            amount = _num(adjustment, "amount", path=apath)
            total += amount
            checked.append({**basis, "amount": amount})
        computed = base + total
        if "ebit" in values and values["ebit"] != computed:
            raise ValidationError(path + ".ebit: does not equal reported_operating_profit plus explicit adjustments")
        values["ebit"] = computed
        values["ebit_adjustments_total"] = total
        extra.update(ebit_basis="reconciled", ebit_adjustments=checked)
    elif "ebit" in values:
        if "reported_operating_profit" in raw:
            raise ValidationError(path + ": provide ebit_adjustments to reconcile a reported operating profit to EBIT")
        basis = _quality_basis(spec, raw.get("ebit_basis"), path + ".ebit_basis")
        if basis["basis"] == "derived":
            raise ValidationError(path + ".ebit_basis: derived EBIT requires explicit ebit_adjustments")
        values["ebit_adjustments_total"] = ZERO
        extra.update(ebit_basis=basis["basis"], ebit_basis_rationale=basis["rationale"])
    elif "reported_operating_profit" in raw or "ebit_basis" in raw:
        raise ValidationError(path + ": EBIT requires disclosed/assumed ebit or reported_operating_profit with ebit_adjustments")
    return extra


@_calculation
def financial_quality(spec):
    _units(spec)
    period_basis = _text(spec.get("period_basis"), "period_basis")
    ar_basis = _choice(spec.get("receivables_sales_basis"), ("credit_sales", "revenue_proxy"), "receivables_sales_basis")
    ap_basis = _choice(spec.get("payables_cost_basis"), ("purchases", "cogs_proxy"), "payables_cost_basis")
    periods = _rows(spec.get("periods"), "periods")
    profit_contract = _quality_profit_contract(spec, periods)
    rows, attribution, prior, years = [], [], None, set()
    cashflow_rows, cashflow_summaries = [], []
    amount_fields = ("revenue", "net_income", "cfo", "cogs", "credit_sales", "purchases", "capex",
                     "receivables_begin", "receivables_end", "inventory_begin", "inventory_end",
                     "payables_begin", "payables_end", "assets_begin", "assets_end",
                     "nonrecurring_net_income", "opex", "other_operating_income", "ebit", "reported_operating_profit",
                     "finance_expense", "interest_expense", "interest_income", "volume", "unit_price")
    nonnegative = set(amount_fields)-{"net_income", "cfo", "nonrecurring_net_income", "other_operating_income", "ebit", "reported_operating_profit", "finance_expense", "opex"}
    for i, raw in enumerate(periods):
        path = f"periods[{i}]"
        year = _integer(raw.get("year"), path+".year", 1900)
        if year in years or (prior and year <= prior["year"]):
            raise ValidationError("periods: years must be unique and ascending")
        years.add(year)
        days = _num(raw, "days", positive=True, maximum=Decimal(371), path=path)
        values = {key: _num(raw, key, minimum=ZERO if key in nonnegative else None, path=path) for key in amount_fields if key in raw}
        profit_extra = _quality_profit_values(spec, profit_contract, raw, values, f"periods.{i}")
        row = {"year": year, "days": days, **values, **profit_extra}
        if any(key in values for key in ("finance_expense", "interest_expense", "interest_income")):
            row["net_interest_expense"] = values["interest_expense"] - values["interest_income"] if all(key in values for key in ("interest_expense", "interest_income")) else None
            row["net_interest_expense_reason"] = None if row["net_interest_expense"] is not None else "requires separately supplied interest expense and interest income; finance expense sign alone is insufficient"
            row["finance_expense_noninterest_residual"] = values["finance_expense"] - row["net_interest_expense"] if "finance_expense" in values and row["net_interest_expense"] is not None else None
        def ratio(name, numerator, denominator, missing="missing required inputs"):
            reason = missing if numerator is None or denominator is None else ("nonpositive denominator" if denominator <= 0 else None)
            row[name] = numerator / denominator if reason is None else None
            row[name+"_reason"] = reason
        def avg(prefix):
            a, b = values.get(prefix+"_begin"), values.get(prefix+"_end")
            return (a+b)/2 if a is not None and b is not None else None
        ratio("cash_conversion", values.get("cfo"), values.get("net_income"))
        ratio("cfo_margin", values.get("cfo"), values.get("revenue"))
        if raw.get('cashflow_bridge') is not None:
            bridge=_obj(raw['cashflow_bridge'],path+'.cashflow_bridge')
            basis=_choice(bridge.get('profit_basis'),('consolidated_net_income','profit_before_tax'),'cashflow_bridge.profit_basis')
            start=_num(bridge,'starting_profit');subtotal=start;excluded=[];unclassified=[]
            cashflow_rows.append({'year':year,'label':basis,'category':'starting_profit','amount':start,'included':True})
            for adjustment in bridge.get('adjustments',[]):
                category=_choice(adjustment.get('category'),('non_cash','operating_working_capital','operating_other','tax','investing','financing','unclassified'),'cashflow_bridge.category')
                amount=_num(adjustment,'amount');label=_text(adjustment.get('label'),'cashflow_bridge.label')
                include=category not in {'investing','financing','unclassified'}
                if include:subtotal+=amount
                elif category=='unclassified':unclassified.append(label)
                else:excluded.append(label)
                cashflow_rows.append({'year':year,'label':label,'category':category,'amount':amount,'included':include})
            cfo=values.get('cfo');residual=cfo-subtotal if cfo is not None else None
            cashflow_summaries.append({'year':year,'profit_basis':basis,'starting_profit':start,'explained_cfo':subtotal,
                'reported_cfo':cfo,'unexplained_residual':residual,'excluded_non_operating':excluded,'unclassified':unclassified})
        ratio("receivables_turnover", values.get("credit_sales" if ar_basis == "credit_sales" else "revenue"), avg("receivables"))
        ratio("inventory_turnover", values.get("cogs"), avg("inventory"))
        ratio("payables_turnover", values.get("purchases" if ap_basis == "purchases" else "cogs"), avg("payables"))
        for metric, turnover in (("dso", "receivables_turnover"), ("dio", "inventory_turnover"), ("dpo", "payables_turnover")):
            ratio(metric, days, row[turnover], row[turnover+"_reason"] or "missing required inputs")
        row["cash_conversion_cycle"] = row["dso"]+row["dio"]-row["dpo"] if all(row[key] is not None for key in ("dso", "dio", "dpo")) else None
        row["cash_conversion_cycle_reason"] = None if row["cash_conversion_cycle"] is not None else "requires DSO, DIO and DPO"
        accruals = values["net_income"]-values["cfo"] if "net_income" in values and "cfo" in values else None
        ratio("accruals_to_assets", accruals, avg("assets"))
        row["cfo_less_capex"] = values["cfo"]-values["capex"] if "cfo" in values and "capex" in values else None
        row["cfo_less_capex_reason"] = None if row["cfo_less_capex"] is not None else "requires CFO and capex"
        row["cash_profit_gap"] = values["cfo"]-values["net_income"] if "cfo" in values and "net_income" in values else None
        row["recurring_net_income"] = values["net_income"]-values["nonrecurring_net_income"] if "net_income" in values and "nonrecurring_net_income" in values else None
        wc_keys=("receivables_begin","receivables_end","inventory_begin","inventory_end","payables_begin","payables_end")
        row["working_capital_change"] = values["receivables_end"]-values["receivables_begin"]+values["inventory_end"]-values["inventory_begin"]-values["payables_end"]+values["payables_begin"] if all(k in values for k in wc_keys) else None
        if prior and year==prior["year"]+1:
            bridge={"from_year":prior["year"],"to_year":year,"volume_effect":None,"price_effect":None,"revenue_residual":None}
            if profit_contract:
                anchor=profit_contract["anchor"]
                separate=profit_contract["finance_expense_treatment"] == "separate"
                bridge_keys=("revenue", "cogs", "opex", "other_operating_income", anchor) + (("finance_expense",) if separate else ())
                effects=("revenue_effect", "cogs_effect", "opex_effect", "other_operating_income_effect") + (("finance_expense_effect",) if separate else ()) + (("ebit_adjustments_effect",) if anchor == "ebit" else ())
                bridge.update(profit_anchor=anchor, **{key: None for key in (anchor + "_change", anchor + "_residual", *effects)})
                if all(k in values and k in prior for k in bridge_keys):
                    if anchor == "ebit" and (profit_extra.get("ebit_basis") == "reconciled") != (prior.get("ebit_basis") == "reconciled"):
                        raise ValidationError("profit_bridge: both periods must use the same disclosed/assumed or reconciled bridge construction")
                    bridge.update({anchor + "_change": values[anchor] - prior[anchor]}, revenue_effect=values["revenue"]-prior["revenue"], cogs_effect=prior["cogs"]-values["cogs"], opex_effect=prior["opex"]-values["opex"], other_operating_income_effect=values["other_operating_income"]-prior["other_operating_income"])
                    if separate:
                        bridge["finance_expense_effect"] = prior["finance_expense"] - values["finance_expense"]
                    if anchor == "ebit":
                        bridge["ebit_adjustments_effect"] = values["ebit_adjustments_total"] - prior["ebit_adjustments_total"]
                    bridge[anchor + "_residual"] = bridge[anchor + "_change"] - sum(bridge[key] for key in effects)
                bridge[anchor + "_reason"] = None if bridge[anchor + "_change"] is not None else "requires matching " + ", ".join(bridge_keys) + " for both years; absent data is not zero"
            if all(k in values and k in prior for k in ("revenue","volume","unit_price")):
                if not spec.get("volume_unit"):
                    raise ValidationError("volume_unit: explicit quantity unit required for price-volume attribution; unit_price uses amount_scale per one quantity unit")
                bridge["volume_effect"]=(values["volume"]-prior["volume"])*(values["unit_price"]+prior["unit_price"])/2
                bridge["price_effect"]=(values["unit_price"]-prior["unit_price"])*(values["volume"]+prior["volume"])/2
                bridge["revenue_residual"]=values["revenue"]-prior["revenue"]-bridge["volume_effect"]-bridge["price_effect"]
            bridge["price_volume_reason"]=None if bridge["volume_effect"] is not None else "requires explicit comparable volume and unit price; no inferred quantities"
            attribution.append(bridge)
        for metric in ("revenue", "net_income"):
            current = values.get(metric)
            previous = prior.get(metric) if prior and year == prior["year"]+1 else None
            change = current-previous if current is not None and previous is not None else None
            row[metric+"_change"] = change
            ratio(metric+"_yoy", change, previous, "requires consecutive fiscal years and both values")
        rows.append(row)
        prior = {"year": year, **values, **profit_extra}
    return _result("financial_quality", spec, QUALITY_FORMULAS,
                   {"period_count": len(rows), "period_basis": period_basis, "receivables_sales_basis": ar_basis, "payables_cost_basis": ap_basis,
                    "profit_bridge": copy.deepcopy(profit_contract),"cashflow_reconciliations":cashflow_summaries}, {"quality": rows,"attribution":attribution,"cashflow_bridge":cashflow_rows},
                   ["Ratios describe supplied data; they are not a fraud diagnosis. Opening/closing averages are a two-point approximation, and all flow/balance scopes must match."])


def evaluate_model(kind, spec):
    from .three_statement import three_statement
    functions = {"dcf": value_dcf, "comparables": value_comparables,
                 "manufacturing_scenario": manufacturing_scenario, "financial_quality": financial_quality, "three_statement": three_statement}
    if not isinstance(kind, str) or kind not in functions:
        raise ValidationError("kind: choose dcf, comparables, manufacturing_scenario or financial_quality")
    return functions[kind](spec)


def export_json(result, *, indent=2):
    """Return a standalone reproducible result, preserving decimal strings."""
    return json.dumps(_json(result), ensure_ascii=False, allow_nan=False, indent=indent)


def export_csv(result, table):
    """Return an explicitly chosen result table. Does not write files or round values."""
    tables = _obj(result.get("tables"), "result.tables")
    if table not in tables:
        raise ValidationError("table: unknown table; available: " + ", ".join(tables))
    rows = tables[table]
    if not isinstance(rows, list):
        raise ValidationError("table: expected an array of rows")
    if not rows:
        return ""
    keys = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=keys, lineterminator="\n")
    writer.writeheader()
    for row in _json(rows):
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return stream.getvalue()

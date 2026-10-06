"""Model-facing JSON schemas and completely synthetic runnable examples."""
from copy import deepcopy


DECIMAL = {"oneOf": [{"type": "string", "pattern": r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"}, {"type": "number"}],
           "description": "Finite decimal; use a decimal string to preserve digits. Ratios use fractions: 0.10 means 10%, not 10."}


def obj(properties, required):
    return {"type": "object", "properties": properties, "required": required}


COMMON = {"currency": {"type": "string", "minLength": 1, "description": "One currency for all subject amounts, e.g. CNY. No automatic currency conversion."},
          "amount_scale": {**DECIMAL, "description": "Positive multiplier for all aggregate amounts and scenario unit prices. '1'=base currency, '10000'=ten-thousands, '1000000'=millions. Value per share is ALWAYS base currency / one share."},
          "input_basis": {"type": "object", "description": "Optional per-input basis map using dot JSON paths, e.g. base.revenue, forecast.0.ebit_margin, dcf.discount.wacc. Disclosed means stated by an identified source; derived means computed from cited inputs; assumption means an explicitly proposed research choice. Each entry requires a rationale. Put citations only in source_refs at the SAME path; do not duplicate references here. Missing metadata means unclassified, never implicitly disclosed. After manually changing a sourced value, mark the new draft value as assumption unless independently re-established from a cited source.",
                          "propertyNames": {"pattern": r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$"},
                          "additionalProperties": {"type": "object", "properties": {"basis": {"enum": ["disclosed", "derived", "assumption"]}, "rationale": {"type": "string", "minLength": 1}, "source_kind": {"enum": ["disclosed_actual", "analyst_forecast", "management_guidance", "assumption", "unknown"], "description": "What the source states, separately from how the model uses it. A quoted finite-horizon forecast extended into terminal years remains a model assumption; result.input_usage records that use."}}, "required": ["basis", "rationale"], "additionalProperties": False}},
          "source_refs": {"type": "object", "description": "Map input JSON paths to arrays of {kind:'source'|'document'|'artifact',id,locator,quote?,revision_id?}. Use source paragraph IDs such as p1,p2; document page:physical-page; artifact existing fields such as results.value_per_share or tables.forecast[0].revenue (not results.tables). Optional quote must occur literally at that location, not be a paraphrase. The host verifies new structured locations/quotes and fixes the artifact revision actually read; revision_id is optional and only for artifact references. This checks citation existence, NOT whether the parameter value/meaning or disclosed classification is correct. Legacy references without locator remain dependency_only_unverified. The calculator itself preserves references without retrieval. source_model imports inherit the selected immutable scenario's original source audit and dependency versions, never rebind old evidence to latest. Analyst assumptions must be labeled explicitly; do not invent source IDs."}}
SHARES = obj({"count": DECIMAL, "scale": {**DECIMAL, "description": "Positive multiplier for share count: count='100', scale='1000000' means 100 million shares. Use diluted ordinary shares consistent with earnings; never use monetary amount_scale for shares implicitly."}}, ["count", "scale"])
BRIDGE = {**obj({name: DECIMAL for name in ("net_debt", "non_controlling_interest", "preferred_equity", "non_operating_assets_ex_cash")},
                ["net_debt", "non_controlling_interest", "preferred_equity", "non_operating_assets_ex_cash"]),
          "additionalProperties": False,
          "description": "All four amounts must be explicit, including zero. Net debt is debt less excess cash, and may be negative. Add only non-operating assets EXCLUDING that cash. NCI/preferred/non-operating assets are nonnegative. Consolidated operating valuation must deduct outside owners' claims. Debt/lease and earnings treatment must be consistent."}
BASE = obj({"revenue": DECIMAL, "net_working_capital": {**DECIMAL, "description": "Operating non-cash working capital, excluding interest-bearing debt. Negative working capital is supported."}}, ["revenue", "net_working_capital"])
DISCOUNT = obj({"wacc": {**DECIMAL, "description": "Positive annual WACC, consistent currency/inflation with FCFF; terminal growth must be lower."},
                "cashflow_timing": {"enum": ["year_end", "mid_year"], "description": "mid_year discounts explicit year t at t-0.5; terminal value is always measured/discounted at year n end."}}, ["wacc", "cashflow_timing"])
TERMINAL = obj({"growth": {**DECIMAL, "description": "Stable annual growth: 0 <= g < WACC and g <= ROIC. Negative-growth/liquidation models are outside this model."},
                "roic": {**DECIMAL, "description": "Explicit positive stable after-tax return on invested capital. Reinvestment fraction = g/ROIC."},
                "ebit_margin": {**DECIMAL, "description": "Explicit normalized stable EBIT/revenue, after D&A, greater than zero and <=1."}, "tax_rate": DECIMAL},
               ["growth", "roic", "ebit_margin", "tax_rate"])
SENSITIVITY = obj({"wacc": {"type": "array", "minItems": 1, "items": DECIMAL}, "growth": {"type": "array", "minItems": 1, "items": DECIMAL}}, ["wacc", "growth"])
CASH_TAX = {"enum": ["floor_at_zero", "immediate_credit"], "description": "floor_at_zero taxes only positive EBIT. immediate_credit allows same-year loss credits. Neither models NOL carryforwards."}
FORECAST_PROPERTIES = {"year": {"type": "integer", "minimum": 1900}, **{name: DECIMAL for name in
    ("revenue", "revenue_growth", "ebit", "ebit_margin", "gross_margin", "opex_ratio", "tax_rate", "da", "da_ratio", "capex", "capex_ratio", "net_working_capital", "nwc_ratio")}}
FORECAST = obj(FORECAST_PROPERTIES, ["year", "tax_rate"])
FORECAST["description"] = "Contiguous full fiscal years starting base_year+1. EBIT is after D&A; gross margin and opex must include relevant D&A once. No capex disposal proceeds modeled. Costs/capex/D&A nonnegative; EBIT may be negative. NWC may be negative. Choose each pair/mode explicitly."
FORECAST["allOf"] = [
    {"oneOf": [{"required": ["revenue"], "not": {"required": ["revenue_growth"]}}, {"required": ["revenue_growth"], "not": {"required": ["revenue"]}}]},
    {"oneOf": [{"required": ["ebit"], "not": {"anyOf": [{"required": [key]} for key in ("ebit_margin", "gross_margin", "opex_ratio")]}},
               {"required": ["ebit_margin"], "not": {"anyOf": [{"required": [key]} for key in ("ebit", "gross_margin", "opex_ratio")]}},
               {"required": ["gross_margin", "opex_ratio"], "not": {"anyOf": [{"required": ["ebit"]}, {"required": ["ebit_margin"]}]}}]},
    *[{"oneOf": [{"required": [a], "not": {"required": [b]}}, {"required": [b], "not": {"required": [a]}}]} for a, b in
      (("da", "da_ratio"), ("capex", "capex_ratio"), ("net_working_capital", "nwc_ratio"))]]
DCF_COMPONENTS = {"cash_tax_policy": CASH_TAX, "discount": DISCOUNT, "terminal": TERMINAL, "bridge": BRIDGE, "shares": SHARES, "sensitivity": SENSITIVITY}
DCF = obj({**COMMON, **DCF_COMPONENTS, "base_year": {"type": "integer", "minimum": 1900}, "base": BASE,
           "forecast": {"type": "array", "minItems": 1, "items": FORECAST}},
          ["currency", "amount_scale", "base_year", "base", "forecast", "cash_tax_policy", "discount", "terminal", "bridge", "shares"])
DCF["description"] = "Non-financial operating business FCFF DCF, end of base_year valuation, one constant WACC, explicit annual horizon plus stable ROIC-linked terminal phase."
DCF['properties']['reference_value_per_share']={**DECIMAL,'description':'Optional comparison price in currency per one share (not amount_scale). Records exact distance and whether the supplied sensitivity grid contains it; it does not calibrate or change the valuation.'}
PEER = obj({"id": {"type": "string", "minLength": 1}, "metric_basis": {"type": "string", "minLength": 1},
            **{name: DECIMAL for name in ("multiple", "price", "eps", "enterprise_value", "ebitda")}}, ["id", "metric_basis"])
PEER["description"] = "Provide positive multiple OR price+EPS for P/E OR enterprise_value+EBITDA for EV/EBITDA. Within each pair use the same currency/unit. Nonpositive denominator or mismatched basis is excluded with reason; cannot infer comparability from amounts."
COMPARABLES = obj({**COMMON, "method": {"enum": ["pe", "ev_ebitda"]}, "aggregation": {"enum": ["median", "mean"]},
                   "metric_basis": {"type": "string", "description": "Common valuation denominator basis, e.g. FY2027_forward_adjusted; must exactly match every included peer."},
                   "subject": obj({"earnings": {**DECIMAL, "description": "Positive earnings attributable to ordinary shareholders for P/E."},
                                    "ebitda": {**DECIMAL, "description": "Positive consolidated operating EBITDA for EV/EBITDA."}, "shares": SHARES, "bridge": BRIDGE}, ["shares"]),
                   "peers": {"type": "array", "minItems": 1, "items": PEER}},
                  ["currency", "amount_scale", "method", "aggregation", "metric_basis", "subject", "peers"])
COMPARABLES["allOf"] = [{"if": {"properties": {"method": {"const": "pe"}}}, "then": {"properties": {"subject": {"required": ["earnings"], "not": {"required": ["bridge"]}}}},
                          "else": {"properties": {"subject": {"required": ["ebitda", "bridge"]}}}}]
BASELINE = obj({"year": {"type": "integer"}, **{name: DECIMAL for name in ("volume", "unit_price", "material_cost_per_unit", "other_variable_cost_per_unit", "fixed_cash_opex", "da", "capex", "nwc_ratio", "tax_rate")}},
               ["year", "volume", "unit_price", "material_cost_per_unit", "other_variable_cost_per_unit", "fixed_cash_opex", "da", "capex", "nwc_ratio", "tax_rate"])
SCENARIO_PARAMETERS = obj({"exposed_material_share": {**DECIMAL, "description": "Explicit share (0..1) of baseline raw-material cost exposed to this shock; never inferred from company name."},
                           "pass_through_rate": {**DECIMAL, "description": "0..1 fraction of exposed absolute unit-cost change passed into selling price."},
                           "lag_years": {"type": "integer", "minimum": 0, "description": "Whole annual periods; pre-horizon material cost changes are explicitly assumed zero."},
                           "price_elasticity": {**DECIMAL, "description": "Explicit nonpositive coefficient for linear demand change relative to baseline; 0 means no demand effect."},
                           **{name: {"type": "array", "items": DECIMAL, "description": "One value per baseline year. Level relative to that year's baseline, not cumulative increment. Must exceed -1."} for name in ("material_cost_changes", "volume_changes", "autonomous_price_changes")}},
                          ["exposed_material_share", "pass_through_rate", "lag_years", "price_elasticity", "material_cost_changes", "volume_changes", "autonomous_price_changes"])
MANUFACTURING = obj({**COMMON, "base_year": {"type": "integer"}, "base": BASE, "volume_unit": {"type": "string", "minLength": 1},
                     "baseline": {"type": "array", "minItems": 1, "items": BASELINE}, "scenario": SCENARIO_PARAMETERS,
                     "dcf": obj(DCF_COMPONENTS, ["cash_tax_policy", "discount", "terminal", "bridge", "shares"])},
                    ["currency", "amount_scale", "base_year", "base", "volume_unit", "baseline", "scenario", "dcf"])
MANUFACTURING["description"] = "Explicit manufacturing cost/price/volume scenario. Returns baseline/scenario operating forecasts and directly runnable DCF specs. Other variable unit costs, fixed costs, D&A, capex, NWC ratio and terminal policies are held at supplied baseline. No estimated exposure, elasticity or causal effects."
QUALITY = obj({**COMMON, "period_basis": {"type": "string", "minLength": 1, "description": "Comparable flow period across years, e.g. FY or H1. All rows must have the same reporting scope/basis; year gaps do not produce YoY."},
               "receivables_sales_basis": {"enum": ["credit_sales", "revenue_proxy"]}, "payables_cost_basis": {"enum": ["purchases", "cogs_proxy"]},
               "periods": {"type": "array", "minItems": 1, "items": obj({"year": {"type": "integer"}, "days": {**DECIMAL, "description": "Explicit days in the comparable flow period, >0 and <=371; turnover itself is per supplied period, not automatically annualized."},
                    **{name: DECIMAL for name in ("revenue", "net_income", "cfo", "cogs", "credit_sales", "purchases", "capex", "receivables_begin", "receivables_end", "inventory_begin", "inventory_end", "payables_begin", "payables_end", "assets_begin", "assets_end")}}, ["year", "days"]) }},
              ["currency", "amount_scale", "period_basis", "receivables_sales_basis", "payables_cost_basis", "periods"])
QUALITY["properties"]["volume_unit"]={"type":"string","description":"Required when quantity and price are supplied. volume is number of this unit; unit_price is in amount_scale currency per one such unit."}
QUALITY["properties"]["periods"]["items"]["properties"].update({name:DECIMAL for name in ("opex","other_operating_income","ebit","volume","unit_price")})
QUALITY["properties"]["profit_bridge"] = obj({
    "anchor": {"enum": ["reported_operating_profit", "ebit"], "description": "Choose the actual subtotal. Reported operating profit (e.g. 营业利润 including finance expense under the applicable statement format) is not automatically EBIT."},
    "definition": {"type": "string", "minLength": 1, "description": "Exact reporting/entity scope and profit definition, including applicable source accounting basis. A reported source subtotal is not silently relabeled EBIT."},
    "opex_definition": {"type": "string", "minLength": 1, "description": "Enumerate what opex contains (e.g. taxes/selling/admin/R&D). State D&A and finance treatment; avoid double counting COGS/other income."},
    "other_operating_income_definition": {"type": "string", "minLength": 1, "description": "Enumerate the signed income/gain/loss components aggregated here; the field is an analyst aggregation, not necessarily the statement's line named other income."},
    "finance_expense_treatment": {"enum": ["separate", "included_in_opex", "excluded"], "description": "separate: subtract signed finance_expense once, opex excludes it; included_in_opex: do not deduct it again; excluded: not in this profit bridge. For reconciled EBIT these choices describe the underlying reported-profit bridge, then named adjustments are added."},
}, ["anchor", "definition", "opex_definition", "other_operating_income_definition", "finance_expense_treatment"])
EBIT_BASIS = obj({"basis": {"enum": ["disclosed", "assumption"]}, "rationale": {"type": "string", "minLength": 1}}, ["basis", "rationale"])
EBIT_BASIS["description"] = "Required for direct ebit. disclosed requires a located source_refs entry at periods.N.ebit_basis showing actual EBIT definition/value; assumption explicitly labels a synthetic or forecast input. To derive EBIT use named ebit_adjustments instead."
EBIT_ADJUSTMENT = obj({"label": {"type": "string", "minLength": 1}, "amount": {**DECIMAL, "description": "Signed amount added to reported_operating_profit. Never automatically add back all finance expense."}, "basis": {"enum": ["disclosed", "derived", "assumption"]}, "rationale": {"type": "string", "minLength": 1, "description": "What is added/removed and why, consistent with the exact EBIT definition."}}, ["label", "amount", "basis", "rationale"])
EBIT_ADJUSTMENT["description"] = "disclosed/derived adjustment needs located source_refs at periods.N.ebit_adjustments.M; assumption is explicitly hypothetical. Exact source/quote existence is checked by the host, meaning/value remains subject to financial review."
QUALITY["properties"]["periods"]["items"]["properties"].update({
    "reported_operating_profit": {**DECIMAL, "description": "Signed source statement operating-profit subtotal under its actual accounting convention. Not automatically EBIT."},
    "ebit": {**DECIMAL, "description": "Direct disclosed/assumed EBIT with ebit_basis; or optional checksum exactly equal to reported_operating_profit + sum(ebit_adjustments)."},
    "ebit_basis": EBIT_BASIS,
    "ebit_adjustments": {"type": "array", "minItems": 1, "items": EBIT_ADJUSTMENT, "description": "Derives EBIT from explicit reported_operating_profit. Cannot combine with ebit_basis. Both comparison periods must use the same bridge construction."},
    "finance_expense": {**DECIMAL, "description": "Signed reported finance expense: positive expense, negative net credit. Can include interest, exchange differences and fees. Its sign alone does NOT tell whether interest income exceeds interest expense."},
    "interest_expense": {**DECIMAL, "description": "Separately disclosed nonnegative interest expense, same period/scope as interest_income."},
    "interest_income": {**DECIMAL, "description": "Separately disclosed nonnegative interest income; do not substitute minus finance_expense."},
    "opex": {**DECIMAL, "description": "Signed expense aggregation, positive cost/negative reversal; components and finance inclusion are specified in profit_bridge.opex_definition."},
    "opex_components": {"type": "array", "minItems": 1, "items": obj({"label": {"type": "string", "minLength": 1}, "amount": DECIMAL, "kind": {"enum": ["finance_expense", "other"]}}, ["label", "amount", "kind"]), "description": "When available, supply the components included in opex, preserving signs and source_refs at each component's amount path. The host checks totals and duplicate finance deductions without overwriting source numbers; missing components do not mean zero."},
    "nonrecurring_net_income": {**DECIMAL, "description": "After-tax nonrecurring income with same owners/entity scope as net_income; negative loss allowed. Classification needs source evidence; changes in minority-profit allocation do not establish recurring/nonrecurring nature."},
})
QUALITY["description"] = "No missing amount is inferred as zero. Each unavailable ratio returns null plus a reason. Explicit denominator proxy opt-in; no unsupported fraud score. Optional profit bridge requires profit_bridge and comparable complete components for both years. Select reported_operating_profit vs EBIT, preserve the source finance-expense sign, and supply EBIT basis/reconciliation. Quantity/price decomposition is nested under revenue and not double added to the profit bridge. Balance changes in receivables (including current maturities) are not cash disbursements or finance-lease cash flows without reconciliation of collections, disposals, impairments and reclassifications."
QUALITY["properties"]["periods"]["items"]["properties"]["cashflow_bridge"] = obj({
    "profit_basis":{"enum":["consolidated_net_income","profit_before_tax"],"description":"Actual starting subtotal of the source cash-flow reconciliation; never substitute parent-only income."},
    "starting_profit":DECIMAL,
    "adjustments":{"type":"array","items":obj({"label":{"type":"string"},"amount":DECIMAL,
        "category":{"enum":["non_cash","operating_working_capital","operating_other","tax","investing","financing","unclassified"]}},["label","amount","category"])}
},["profit_basis","starting_profit","adjustments"])
QUALITY["properties"]["periods"]["items"]["properties"]["cashflow_bridge"]["description"] = "Signed adjustments from the same-period source cash-flow reconciliation. The calculator excludes investing/financing items, preserves unclassified items, and reports the residual against periods.N.cfo; no balancing plug or inference from balance changes. Use source_refs/bindings at adjustment amount paths."
SCHEMAS = {"dcf": DCF, "comparables": COMPARABLES, "manufacturing_scenario": MANUFACTURING, "financial_quality": QUALITY}

DCF_EXAMPLE = {"currency": "CNY", "amount_scale": "1", "base_year": 2024,
               "base": {"revenue": "1000", "net_working_capital": "100"},
               "forecast": [{"year": 2025, "revenue_growth": "0", "ebit_margin": "0.2", "tax_rate": "0.25", "da_ratio": "0.05", "capex_ratio": "0.05", "nwc_ratio": "0.1"}],
               "cash_tax_policy": "floor_at_zero", "discount": {"wacc": "0.1", "cashflow_timing": "year_end"},
               "terminal": {"growth": "0", "roic": "0.2", "ebit_margin": "0.2", "tax_rate": "0.25"},
               "bridge": {"net_debt": "200", "non_controlling_interest": "20", "preferred_equity": "10", "non_operating_assets_ex_cash": "30"},
               "shares": {"count": "100", "scale": "1"}, "sensitivity": {"wacc": ["0.08", "0.1", "0.12"], "growth": ["0", "0.02"]},
               "source_refs": {"base.revenue": [{"type": "synthetic_example", "note": "Illustrative input; not an observed company value"}]}}
EXAMPLES = {
    "dcf": DCF_EXAMPLE,
    "comparables": {"currency": "CNY", "amount_scale": "1", "method": "pe", "aggregation": "median", "metric_basis": "FY2025_forward",
                    "subject": {"earnings": "100", "shares": {"count": "100", "scale": "1"}},
                    "peers": [{"id": "synthetic-A", "metric_basis": "FY2025_forward", "price": "30", "eps": "3"}, {"id": "synthetic-B", "metric_basis": "FY2025_forward", "price": "72", "eps": "4"}]},
    "manufacturing_scenario": {"currency": "CNY", "amount_scale": "1", "base_year": 2024, "base": {"revenue": "1000", "net_working_capital": "100"}, "volume_unit": "units",
                               "baseline": [{"year": year, "volume": "100", "unit_price": "10", "material_cost_per_unit": "4", "other_variable_cost_per_unit": "2", "fixed_cash_opex": "100", "da": "50", "capex": "50", "nwc_ratio": "0.1", "tax_rate": "0.25"} for year in (2025, 2026)],
                               "scenario": {"exposed_material_share": "0.5", "pass_through_rate": "0.5", "lag_years": 1, "price_elasticity": "-1", "material_cost_changes": ["0.2", "0.2"], "volume_changes": ["0", "0"], "autonomous_price_changes": ["0", "0"]},
                               "dcf": {key: deepcopy(DCF_EXAMPLE[key]) for key in DCF_COMPONENTS if key in DCF_EXAMPLE}},
    "financial_quality": {"currency": "CNY", "amount_scale": "1", "period_basis": "FY", "receivables_sales_basis": "credit_sales", "payables_cost_basis": "purchases",
                          "profit_bridge": {"anchor": "reported_operating_profit", "definition": "合成企业营业利润：收入减成本、经营费用和单列财务费用，加其他经营净收益；不是 EBIT。", "opex_definition": "合成销售、管理、研发及税金费用；不含已在成本中的项目和单列财务费用。", "other_operating_income_definition": "合成其他收益与损益的净额，不与收入或费用重复。", "finance_expense_treatment": "separate"},
                          "periods": [{"year": 2024, "days": "365", "revenue": "1000", "net_income": "100", "cogs": "550", "opex": "200", "other_operating_income": "10", "finance_expense": "20", "reported_operating_profit": "240"},
                                      {"year": 2025, "days": "365", "revenue": "1200", "net_income": "120", "cfo": "150", "credit_sales": "1000", "cogs": "600", "opex": "220", "other_operating_income": "5", "finance_expense": "-15", "interest_expense": "30", "interest_income": "10", "reported_operating_profit": "395", "purchases": "660", "receivables_begin": "80", "receivables_end": "120", "inventory_begin": "80", "inventory_end": "120", "payables_begin": "50", "payables_end": "70"}]}}


from .three_statement import schema as three_statement_schema, EXAMPLE as THREE_STATEMENT_EXAMPLE
SCHEMAS['three_statement']=three_statement_schema(COMMON,DECIMAL,obj)
EXAMPLES['three_statement']=THREE_STATEMENT_EXAMPLE

def get_model_schema(kind):
    if kind not in SCHEMAS:
        raise ValueError("Unknown model kind")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **deepcopy(SCHEMAS[kind])}


def get_model_example(kind):
    if kind not in EXAMPLES:
        raise ValueError("Unknown model kind")
    example=deepcopy(EXAMPLES[kind])
    basis={}
    def mark(value, path=""):
        if isinstance(value, dict):
            for key,item in value.items():
                if key not in {"source_refs","input_basis"}:mark(item,f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index,item in enumerate(value):mark(item,f"{path}.{index}")
        else:basis[path]={"basis":"assumption","rationale":"合成示例的明确设定，用于演示模型；不是任何实际公司的披露数据。"}
    mark(example)
    example["input_basis"]=basis
    return example

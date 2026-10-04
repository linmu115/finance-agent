import json
import unittest

from service.semantic import materialize


class LongFinancialConceptTests(unittest.TestCase):
    def test_long_financial_concepts_preserve_distinct_exact_source_values(self):
        metrics = [
            "investment_property_original_value_transferred_from_inventory_fixed_assets_and_construction_in_progress",
            "investment_property_accumulated_depreciation_and_amortization_transferred_from_inventory_fixed_assets_and_construction_in_progress",
        ]
        values = ["4,665,316.93", "462,005.27"]
        rows = [["项目", "2024年"], *[[m, v] for m, v in zip(metrics, values)]]
        batch = [{"table": {"index": 0, "page": 97, "rows": rows}, "rows": [2, 3]}]
        columns = [{"column": 2, "period": "2024-FY", "start": "2024-01-01", "end": "2024-12-31", "unit": "元", "currency": "CNY"}]
        extracted = [{"class": "table_schema", "text": "[[T0]]", "span": [0, 6],
                      "attributes": {"company": "来源公司", "statement": "notes", "scope": "consolidated_CAS", "columns_json": json.dumps(columns)}}]
        for row, metric in enumerate(metrics, 2):
            extracted.append({"class": "financial_row", "text": f"[[T0:R{row}]]", "span": [10 * row, 10 * row + 9],
                              "attributes": {"metric": metric, "label": rows[row - 1][0], "dimensions_json": "{}"}})
        facts, issues = materialize(extracted, batch, "document", "deepseek-flash")
        self.assertEqual(issues, [])
        self.assertEqual([fact["metric"] for fact in facts], metrics)
        self.assertEqual([fact["value"] for fact in facts], ["4665316.93", "462005.27"])
        self.assertEqual([fact["source"]["cell"] for fact in facts], ["B2", "B3"])

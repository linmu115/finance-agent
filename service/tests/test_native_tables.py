"""Source-layout regressions, independent of financial model decisions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from service.native_tables import native_text_tables
from service.parser import parse_document
from service.semantic import table_batches


ROOT = Path(__file__).resolve().parents[2]


def put(page, x, y, text, right=False):
    if right:
        x -= fitz.get_text_length(text, fontsize=10)
    page.insert_text((x, y), text, fontsize=10)


class NativeTableLayoutTests(unittest.TestCase):
    def test_unruled_real_statement_preserves_source_words_and_year_headers(self):
        path = ROOT / "benchmark/versions/v0.4.1-holdout/inputs/shenhua_2024_holdout.pdf"
        if not path.exists():
            self.skipTest("development PDF unavailable")
        with patch("service.parser.ocr_image", side_effect=AssertionError("native PDF must not use OCR")):
            parsed = parse_document(path, path.name, lambda *_: None, lambda: False, {})
        tables = [table for table in parsed["tables"] if table["page"] == 3]
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(table["extraction_method"], "native_word_layout")
        self.assertIn(["附注", "2024 年度", "2023 年度"], table["rows"])
        expected = {"一、营业收入": ("338,375", "343,074"), "减：营业成本": ("223,192", "219,922"),
                    "二、营业利润": ("88,362", "91,367"), "三、利润总额": ("85,793", "87,176"),
                    "四、净利润": ("68,865", "69,598")}
        with fitz.open(path) as pdf:
            native_words = {(word[4], tuple(word[:4])) for word in pdf[2].get_text("words")}
        for label, values in expected.items():
            matches = [(r, row) for r, row in enumerate(table["rows"], 1) if row[0].startswith(label)]
            self.assertEqual(len(matches), 1, label)
            row_number, row = matches[0]
            self.assertEqual(tuple(row[1:]), values)
            for column, value in zip("BC", values):
                cell = table["cells"][f"{column}{row_number}"]
                self.assertEqual(cell["raw_text"], value)
                self.assertTrue(all((word["text"], tuple(word["bbox"])) in native_words for word in cell["source_words"]))
                self.assertEqual(cell["bbox"], cell["source_words"][0]["bbox"])
        self.assertEqual(len(table["layout"]["row_boxes"]), len(table["rows"]))
        slices = [batch[0] for batch in table_batches(parsed) if batch[0]["table"]["index"] == table["index"]]
        self.assertEqual([row for item in slices for row in item["rows"]], list(range(1, len(table["rows"]) + 1)))
        self.assertTrue(all(not page["ocr"] for page in parsed["pages"]))

    def test_right_aligned_values_missing_cell_and_wrapped_label(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=500)
            for x, text in [(40, "Item"), (250, "2024 FY"), (400, "2023 FY")]:
                put(page, x, 60, text)
            put(page, 40, 95, "Inventory")
            put(page, 300, 95, "9,876.54", True)
            put(page, 450, 95, "18.9", True)
            put(page, 40, 113, "Long wrapped")
            put(page, 40, 126, "expense label")
            put(page, 300, 126, "(12.34)", True)
            put(page, 40, 148, "Ratio")
            put(page, 300, 148, "8.1%", True)
            put(page, 450, 148, "6.7%", True)
            tables = native_text_tables(page)
            self.assertEqual(len(tables), 1)
            rows = tables[0]["rows"]
            self.assertIn(["Item", "2024 FY", "2023 FY"], rows)
            self.assertIn(["Inventory", "9,876.54", "18.9"], rows)
            self.assertIn(["Long wrapped", "", ""], rows)
            self.assertIn(["expense label", "(12.34)", ""], rows)
            self.assertIn(["Ratio", "8.1%", "6.7%"], rows)

    def test_left_aligned_numeric_columns_and_single_row_table(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=500)
            for y, label, first, second in [(70, "First item", "1234567.89", "2"), (92, "Next", "0", "234567.89")]:
                for x, value in [(40, label), (240, first), (410, second)]:
                    put(page, x, y, value)
            table = native_text_tables(page)[0]
            self.assertEqual(table["rows"], [["First item", "1234567.89", "2"], ["Next", "0", "234567.89"]])
            second = pdf.new_page(width=600, height=300)
            for x, value in [(40, "Single row"), (240, "81.35"), (410, "94.67")]:
                put(second, x, 80, value)
            self.assertEqual(native_text_tables(second)[0]["rows"], [["Single row", "81.35", "94.67"]])

    def test_existing_ruled_region_is_not_duplicated_and_separate_blocks_stay_separate(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=600)
            for y, label in [(60, "Ruled A"), (80, "Ruled B"), (210, "Unruled A"), (230, "Unruled B"),
                             (410, "Last A"), (430, "Last B")]:
                put(page, 40, y, label)
                put(page, 300, y, "13.2", True)
                put(page, 450, y, "23.1", True)
            tables = native_text_tables(page, [(30, 40, 480, 90)])
            self.assertEqual(len(tables), 2)
            self.assertEqual([table["rows"][0][0] for table in tables], ["Unruled A", "Last A"])
            self.assertNotIn("Ruled", str(tables))

    def test_plain_numbered_prose_and_page_number_are_not_tables(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=500)
            put(page, 40, 70, "1. We opened 12 offices during 2024.")
            put(page, 40, 90, "2. There are 35 participants in the annual meeting.")
            put(page, 300, 470, "42")
            self.assertEqual(native_text_tables(page), [])

    def test_parser_preserves_ruled_table_and_recovers_unruled_table_on_same_page(self):
        with tempfile.TemporaryDirectory() as tmp, fitz.open() as pdf:
            page = pdf.new_page(width=600, height=600)
            for y in [40, 65, 90, 115]:
                page.draw_line((30, y), (460, y))
            for x in [30, 210, 335, 460]:
                page.draw_line((x, 40), (x, 115))
            for y, values in [(57, ["Ruled item", "2024", "2023"]), (82, ["Alpha", "135", "246"]), (107, ["Beta", "35", "46"])]:
                for x, value in zip([40, 240, 365], values):
                    put(page, x, y, value)
            for y, values in [(210, ["Unruled item", "2024 FY", "2023 FY"]), (238, ["Gamma", "751.2", "853.4"]), (262, ["Delta", "52.3", "61.4"])]:
                for x, value in zip([40, 240, 410], values):
                    put(page, x, y, value)
            path = Path(tmp) / "layout-2024.pdf"
            pdf.save(path)
            parsed = parse_document(path, path.name, lambda *_: None, lambda: False, {})
            self.assertEqual(len(parsed["tables"]), 2)
            self.assertEqual(sum(cell == "135" for table in parsed["tables"] for row in table["rows"] for cell in row), 1)
            self.assertIn(["Gamma", "751.2", "853.4"], parsed["tables"][1]["rows"])


if __name__ == "__main__":
    unittest.main()

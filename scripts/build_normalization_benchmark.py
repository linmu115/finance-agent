"""Create fixed, public regression inputs. Gold below is independently specified.

This does not import production parsing/normalization code. Never upload gold to
the Agent. Synthetic fixtures intentionally vary labels, periods, scales and scope.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "benchmark/versions/v0.3-normalization"
INPUT = DEST / "inputs"

TABLES = {
 "01_current_prior_millions.csv": [
  ["澄海科技股份有限公司2025年年度报告"], ["合并利润表（中国企业会计准则）"], ["单位：人民币百万元"],
  ["项目", "本期发生额", "上期发生额"],
  ["对外销售商品及提供劳务确认的营业收入", "347.625", "281.4"],
  ["研发投入计入当期损益的费用", "19.375", "16.225"],
 ],
 "02_usd_million_cashflow.csv": [
  ["远帆国际股份有限公司2025年年度报告"], ["母公司现金流量表（国际财务报告准则 IFRS）"], ["单位：百万美元；保留原币，不进行汇率折算"],
  ["项目", "2025年度", "2024年度"],
  ["Net cash generated from operating activities", "8.125", "6.75"],
  ["Payments for acquisition of property plant and equipment", "(2.375)", "(1.625)"],
 ],
 "03_hkd_thousand_balance.csv": [
  ["星海商贸股份有限公司2025年年度报告"], ["母公司资产负债表（国际财务报告准则 IFRS）"], ["单位：千港元"],
  ["项目", "期末余额（2025年12月31日）", "年初余额（2025年1月1日）"],
  ["资产总额", "86,425.75", "80,010.5"],
  ["用于出售的库存商品和材料合计（存货）", "9,617.25", "8,823"],
 ],
 "04_quarter_and_ytd.csv": [
  ["启航制造股份有限公司2025年第三季度报告"], ["合并利润表（中国企业会计准则）"], ["单位：人民币万元"],
  ["项目", "本报告期（7月1日至9月30日）", "年初至报告期末（1月1日至9月30日）", "上年同期（7月1日至9月30日）", "上年年初至同期末（1月1日至9月30日）", "本报告期同比增减（%）"],
  ["营业收入", "458.2", "1234.7", "401.9", "1102.3", "14.01"],
 ],
 "05_restatement_versions.csv": [
  ["长风电子股份有限公司2024年年度报告"], ["合并利润表（中国企业会计准则）"], ["单位：人民币万元；2023年因前期差错进行重述"],
  ["项目", "2024年度", "2023年度（调整前）", "2023年度（调整后）"],
  ["营业收入", "723.6", "601.2", "614.8"],
  ["归属于母公司普通股股东的本年利润", "84.6", "67.1", "68.9"],
 ],
 "06_segment_dimensions.csv": [
  ["明川消费股份有限公司2025年年度报告"], ["合并报表附注：地区分部对外营业收入；中国企业会计准则"], ["单位：人民币百万元；本表各列均为2025年度"],
  ["项目", "华东分部", "华南分部", "合计"],
  ["营业收入", "137.25", "91.625", "228.875"],
  ["营业成本", "82.75", "55.5", "138.25"],
 ],
 "07_row_units.csv": [
  ["海岳制药股份有限公司2025年年度报告"], ["主要合并财务数据和指标（中国企业会计准则）"], ["金额单位：人民币百万元；每股指标及百分比依行名所列单位"],
  ["项目", "2025年度", "2024年度"],
  ["营业收入", "421.875", "380.625"],
  ["基本每股收益（元/股）", "2.375", "2.125"],
  ["加权平均净资产收益率（%）", "13.75", "12.625"],
 ],
 "08_sign_zero_missing.csv": [
  ["北辰材料股份有限公司2025年年度报告"], ["合并利润表（中国企业会计准则）"], ["单位：人民币千元；括号表示负数；横线表示未披露；0表示已披露为零"],
  ["项目", "2025年度", "2024年度"],
  ["净利润（净亏损以负数列示）", "(1,237.5)", "816.25"],
  ["信用减值损失（收益为正）", "0", "-"],
 ],
}

# Expected values were set from fixture definitions, not inferred by the parser.
# Row/column positions are one-based in the source input.
GOLD = []
def expect(file, cell, metric, period, value, currency="CNY", scope="consolidated_CAS", **kw):
    GOLD.append({"id": f"{Path(file).stem}_{cell}_{period}", "file": file, "cell": cell,
                 "metric": metric, "period": period, "value": value, "currency": currency,
                 "scope": scope, **kw})

expect("01_current_prior_millions.csv", "B5", "revenue", "2025-FY", "347625000")
expect("01_current_prior_millions.csv", "C5", "revenue", "2024-FY", "281400000")
expect("01_current_prior_millions.csv", "B6", None, "2025-FY", "19375000", label_regex="研发|研究.*开发", new_metric=True)
expect("01_current_prior_millions.csv", "C6", None, "2024-FY", "16225000", label_regex="研发|研究.*开发", new_metric=True)
expect("02_usd_million_cashflow.csv", "B5", "operating_cash_flow", "2025-FY", "8125000", "USD", "parent_IFRS")
expect("02_usd_million_cashflow.csv", "C5", "operating_cash_flow", "2024-FY", "6750000", "USD", "parent_IFRS")
expect("02_usd_million_cashflow.csv", "B6", None, "2025-FY", "-2375000", "USD", "parent_IFRS", label_regex="购建|购置|固定资产|资本.*支出", new_metric=True)
expect("03_hkd_thousand_balance.csv", "B5", "assets", "2025-12-31", "86425750", "HKD", "parent_IFRS")
expect("03_hkd_thousand_balance.csv", "C5", "assets", "2025-01-01", "80010500", "HKD", "parent_IFRS", period_alternatives=["2024-12-31"])
expect("03_hkd_thousand_balance.csv", "B6", None, "2025-12-31", "9617250", "HKD", "parent_IFRS", label_regex="存货", new_metric=True)
expect("04_quarter_and_ytd.csv", "B5", "revenue", "2025-Q3", "4582000", start="2025-07-01", end="2025-09-30")
expect("04_quarter_and_ytd.csv", "C5", "revenue", "2025-9M", "12347000", start="2025-01-01", end="2025-09-30")
expect("04_quarter_and_ytd.csv", "D5", "revenue", "2024-Q3", "4019000", start="2024-07-01", end="2024-09-30")
expect("04_quarter_and_ytd.csv", "E5", "revenue", "2024-9M", "11023000", start="2024-01-01", end="2024-09-30")
expect("05_restatement_versions.csv", "B5", "revenue", "2024-FY", "7236000", restatement="original")
expect("05_restatement_versions.csv", "C5", "revenue", "2023-FY", "6012000", restatement="original")
expect("05_restatement_versions.csv", "D5", "revenue", "2023-FY", "6148000", restatement="restated")
expect("05_restatement_versions.csv", "D6", "net_profit_parent", "2023-FY", "689000", restatement="restated")
expect("06_segment_dimensions.csv", "B5", None, "2025-FY", "137250000", label_regex="收入", dimension_values=["华东"])
expect("06_segment_dimensions.csv", "C5", None, "2025-FY", "91625000", label_regex="收入", dimension_values=["华南"])
expect("06_segment_dimensions.csv", "D5", None, "2025-FY", "228875000", label_regex="收入", consolidated_dimension=True)
expect("06_segment_dimensions.csv", "B6", None, "2025-FY", "82750000", label_regex="成本", dimension_values=["华东"])
expect("07_row_units.csv", "B5", "revenue", "2025-FY", "421875000")
expect("07_row_units.csv", "B6", "eps", "2025-FY", "2.375", "CNY/share")
expect("07_row_units.csv", "B7", "roe", "2025-FY", "13.75", "percent")
expect("08_sign_zero_missing.csv", "B5", "net_profit", "2025-FY", "-1237500")
expect("08_sign_zero_missing.csv", "C5", "net_profit", "2024-FY", "816250")
expect("08_sign_zero_missing.csv", "B6", None, "2025-FY", "0", label_regex="信用.*减值", new_metric=True)
expect("09_merged_headers.xlsx", "B6", "revenue", "2025-FY", "51475000", restatement="original")
expect("09_merged_headers.xlsx", "C6", "revenue", "2024-FY", "45625000", restatement="original")
expect("09_merged_headers.xlsx", "D6", "revenue", "2024-FY", "46250000", restatement="restated")
expect("09_merged_headers.xlsx", "B7", None, "2025-FY", "4175000", label_regex="销售.*费用", new_metric=True)

PDF_GOLD = [
 {"id":"native_revenue_2024", "file":"10_moutai_2024_pages5-6.pdf", "metric":"revenue", "period":"2024-FY", "value":"170899152276.34", "currency":"CNY", "page":1, "original_page":5},
 {"id":"native_revenue_2023", "file":"10_moutai_2024_pages5-6.pdf", "metric":"revenue", "period":"2023-FY", "value":"147693604994.14", "currency":"CNY", "page":1, "original_page":5},
 {"id":"native_assets_2024", "file":"10_moutai_2024_pages5-6.pdf", "metric":"assets", "period":"2024-12-31", "value":"298944579918.70", "currency":"CNY", "page":1, "original_page":5},
 {"id":"native_revenue_q3", "file":"10_moutai_2024_pages5-6.pdf", "metric":"revenue", "period":"2024-Q3", "value":"38845154206.94", "currency":"CNY", "page":2, "original_page":6},
 {"id":"native_cashflow_q4", "file":"10_moutai_2024_pages5-6.pdf", "metric":"operating_cash_flow", "period":"2024-Q4", "value":"48042305950.98", "currency":"CNY", "page":2, "original_page":6},
]

def main():
    INPUT.mkdir(parents=True, exist_ok=True)
    for name, rows in TABLES.items():
        with (INPUT / name).open("w", newline="", encoding="utf-8-sig") as out:
            csv.writer(out).writerows(rows)
    import fitz
    source=ROOT/"samples/native-pdf/贵州茅台2024年年度报告.pdf"
    with fitz.open(source) as original, fitz.open() as excerpt:
        excerpt.insert_pdf(original, from_page=4, to_page=5)
        excerpt.save(INPUT/"10_moutai_2024_pages5-6.pdf", garbage=4, deflate=True)
    (DEST/"gold.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in GOLD+PDF_GOLD),encoding="utf-8")
    forbidden=[{"file":"04_quarter_and_ytd.csv","cell":"F5","reason":"同比百分比列不能作为营业收入金额入库","metric":"revenue"},
               {"file":"08_sign_zero_missing.csv","cell":"C6","reason":"未披露不能编造为零或其他金额"}]
    (DEST/"forbidden.json").write_text(json.dumps(forbidden,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest={"version":"v0.3-normalization", "created_date":"2026-10-03", "kind":"developer_regression_not_competition_dataset",
      "scope":"9 synthetic tables and 2 unchanged original annual-report pages; no OCR. Tests normalization and Pi workflow, not whole-report completeness or investment analysis accuracy.",
      "gold_origin":"Synthetic expected values independently specified in the builder; public-PDF values transcribed from original table text. Not human blind-reviewed.",
      "expected_facts":len(GOLD)+len(PDF_GOLD), "forbidden_facts":len(forbidden),
      "sources":[{"file":"10_moutai_2024_pages5-6.pdf","original":"samples/native-pdf/贵州茅台2024年年度报告.pdf","original_pages":[5,6],"source_url":"https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}],
      "inputs":[{"file":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size} for p in sorted(INPUT.iterdir()) if p.suffix in {".csv",".xlsx",".pdf"}]}
    (DEST/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"fixtures":len(manifest["inputs"]),"gold":manifest["expected_facts"],"destination":str(DEST)},ensure_ascii=False))

if __name__=="__main__": main()

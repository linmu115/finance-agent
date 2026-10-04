"""Create a distinct, documented gold revision; never rewrite the frozen v0.3."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "benchmark/versions/v0.3-normalization"
NEW = ROOT / "benchmark/versions/v0.3.1-normalization"
TARGET = "02_usd_million_cashflow_B6_2025-FY"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# Acquisition of physical fixed assets with an outflow/payment meaning.
# Receipts, disposal, depreciation, intangible assets and non-cash acquisitions
# are different concepts, even when the label also mentions purchases or PPE.
NEGATIVE = r"收到|收回|收取|流入|处置|出售|卖出|变卖|收益|收入|折旧|减值|无形资产|其他长期资产|投资性房地产|非现金|应付|赊购|\b(?:proceeds|receipts?|received|sales?|disposal|depreciation|impairment|intangible|payables?)\b|\binvestment\s+property\b|\bnon[-\s]?cash\b"
ACQUISITION = r"购建|购置|购买|采购|\b(?:acquisition|purchases?|purchasing)\b"
PHYSICAL_ASSETS = r"固定资产|(?:物业|不动产)[、，,\s]*厂房(?:[、，,\s]|和|及|与)*设备|\bfixed\s+assets?\b|\bproperty[\s,，]+plant[\s,，]*(?:and|&)?\s*equipment\b|\bpp[&＆]e\b"
PAYMENT = r"支出|支付(?:的)?现金|\bpayments?\b|\bcash\s+(?:paid|outflows?)\b"
PATTERN = "^(?![\\s\\S]*(?:" + NEGATIVE + "))(?=[\\s\\S]*(?:" + ACQUISITION + "))(?=[\\s\\S]*(?:" + PHYSICAL_ASSETS + "))(?=[\\s\\S]*(?:" + PAYMENT + "))[\\s\\S]+$"

def main():
    if NEW.exists():
        raise RuntimeError("Revision already exists; do not overwrite a published benchmark revision")
    old_reports = [ROOT / "benchmark/results" / name for name in [
        "pi-workflow-v03-quick.json",
        "pi-workflow-01a20418-f585-48fd-acb4-2ab0b88431c9.json",
        "pi-workflow-0a2f1e99-5240-46f1-86c8-54e021f22ac4.json",
        "pi-workflow-4c1fddcc-8854-4415-b687-81fdc15ede67.json",
    ]]
    frozen = [OLD / "gold.jsonl", OLD / "manifest.json", OLD / "forbidden.json", ROOT / "samples/normalization-benchmark-v0.3.zip", *old_reports]
    before = {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in frozen}
    shutil.copytree(OLD, NEW)
    lines = (OLD / "gold.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    changed = 0
    for index, line in enumerate(lines):
        record = json.loads(line)
        if record["id"] != TARGET:
            continue
        assert record["label_regex"] == "购建|购置|固定资产|资本.*支出"
        old_pattern = record["label_regex"]
        record["label_regex"] = PATTERN
        lines[index] = json.dumps(record, ensure_ascii=False) + "\n"
        changed += 1
    assert changed == 1
    (NEW / "gold.jsonl").write_text("".join(lines), encoding="utf-8", newline="")
    positives = [
        "购建固定资产支付的现金", "购置固定资产的现金支出", "购买物业、厂房及设备支付的现金",
        "购置不动产、厂房和设备支付的现金", "固定资产购置支出",
        "Payments for acquisition of property plant and equipment",
        "Cash paid for purchases of property, plant and equipment", "Payments for purchase of fixed assets",
    ]
    negatives = [
        "处置物业、厂房及设备收到的现金", "购置固定资产收到的政府补助现金", "购买无形资产支付的现金",
        "购建固定资产及无形资产支付的现金", "购置固定资产发生的折旧费用", "非现金购买固定资产",
        "购买物业、厂房及设备的应付款", "购买存货支付的现金", "购置投资性房地产支付的现金",
        "Cash proceeds from sale of property plant and equipment", "Payments for acquisition of intangible assets",
        "Non-cash purchase of property plant and equipment", "Depreciation of property plant and equipment",
        "Proceeds from sales and payments for acquisition of property plant and equipment",
        "借款收到的现金（用于购建固定资产）", "资本支出",
    ]
    cases = {"gold_id": TARGET, "source_phrase": "Payments for acquisition of property plant and equipment", "positive": positives, "negative": negatives}
    (NEW / "label-equivalence-tests.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    change = {
        "revision": "v0.3.1-normalization", "gold_revision": 2, "parent_revision": "v0.3-normalization", "created_date": "2026-10-03",
        "reason": "Correct a demonstrated false rejection of the Chinese equivalent of the original English PPE purchase payment item. Tighten exclusions for inflows and different financial concepts.",
        "changed_gold_ids": [TARGET], "changed_fields": ["label_regex"], "previous_label_regex": old_pattern, "new_label_regex": PATTERN,
        "unchanged": "All 10 input files, 37 expected values, currencies, scopes, periods, source coordinates, remaining gold rows and both forbidden cases.",
        "source_phrase": cases["source_phrase"], "observed_valid_label": "购买物业、厂房及设备支付的现金",
        "review_type": "Developer-reviewed correction after observing a false negative; not a blind evaluation.",
        "old_official_result_retained": "The 2026-10-03 run 4c1fddcc-8854-4415-b687-81fdc15ede67 remains failed at 35/37. Its independent real total-assets period error is not waived.",
        "frozen_prior_sha256": before, "new_gold_sha256": digest(NEW / "gold.jsonl"),
    }
    (NEW / "revision.json").write_text(json.dumps(change, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(version="v0.3.1-normalization", gold_revision=2, parent_version="v0.3-normalization", revision_file="revision.json", gold_sha256=digest(NEW / "gold.jsonl"), forbidden_sha256=digest(NEW / "forbidden.json"), label_regression_file="label-equivalence-tests.json")
    (NEW / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    instructions=(OLD / "使用说明.txt").read_text(encoding="utf-8").replace("财报清洗测试包 v0.3", "财报清洗测试包 v0.3.1（标准答案修订 2）", 1)
    instructions += "\n本次修订\n仅纠正第 02 份现金流表 PPE 支付项的标签匹配误拒。英文原句为 Payments for acquisition of property plant and equipment；“购买物业、厂房及设备支付的现金”是含义相同的正确表述。新规则同时排除出售回款、折旧、无形资产和非现金购置等不同概念。\n没有改任何输入、数值、期间、来源位置或禁止事实。旧 v0.3 文件及历史 35/37 结果全部保留；该次总资产期间错误仍是程序错误。此次属于已见样本后的工程回归标准纠错，不是盲测。revision.json 保存旧文件和旧报告哈希，label-equivalence-tests.json 保存正反例。\n当前应用的自动验收默认使用此修订；读取旧报告时仍按报告原版本解释。下一轮真实结果另存新报告，不能把旧报告刷成通过。\n"
    (NEW / "使用说明.txt").write_text(instructions, encoding="utf-8")
    for relative, old_hash in before.items():
        assert digest(ROOT / relative) == old_hash, "Frozen artifact changed: " + relative
    for item in manifest["inputs"]:
        assert digest(NEW / "inputs" / item["file"]) == item["sha256"]
    old_gold=[json.loads(line) for line in (OLD / "gold.jsonl").read_text(encoding="utf-8").splitlines()]
    new_gold=[json.loads(line) for line in (NEW / "gold.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(new_gold)==len(old_gold)==37
    for old,new in zip(old_gold,new_gold):
        assert old == (new | {"label_regex": old["label_regex"]}) if old["id"] == TARGET else old == new
    print(json.dumps({"revision":manifest["version"],"gold_sha256":manifest["gold_sha256"],"changed_gold_rows":changed,"positive_cases":len(positives),"negative_cases":len(negatives)},ensure_ascii=False))

if __name__ == "__main__":
    main()

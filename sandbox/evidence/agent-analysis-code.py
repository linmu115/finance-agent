
import json, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

DOC = "7d2424c2368443edb9576c33d56e8d47"
raw = open("/input/tables.json", encoding="utf-8").read()
tables = json.loads(raw)

def norm(x):
    return re.sub(r"\s+", "", str(x)) if x is not None else ""

def iter_cells(o):
    if isinstance(o, dict):
        yield [v for v in o.values()]
        for v in o.values():
            yield from iter_cells(v)
    elif isinstance(o, list):
        if o and not any(isinstance(c, (list, dict)) for c in o):
            yield list(o)
        else:
            for v in o:
                yield from iter_cells(v)

cand = [c for c in iter_cells(tables)]
header = data = None
for c in cand:
    n = [norm(x) for x in c]
    if "2023" in n and "2024" in n and "营业收入" not in n:
        header = (n, c)
    if any(x == "营业收入" for x in n) and sum(1 for x in n if re.fullmatch(r"\d{5,}", x)) >= 2:
        data = (n, c)

years = [2023, 2024]
if data is not None:
    dn, dc = data
    if header is not None:
        hn = header[0]
        i23, i24 = hn.index("2023"), hn.index("2024")
        v23 = int(norm(dc[i23]).replace(",", ""))
        v24 = int(norm(dc[i24]).replace(",", ""))
        unit = norm(dc[hn.index("单位")]) if "单位" in hn else "元"
        curr = norm(dc[hn.index("币种")]) if "币种" in hn else "CNY"
    else:
        nums = [int(x.replace(",", "")) for x in dn if re.fullmatch(r"\d{5,}", x)]
        v23, v24 = nums[-2], nums[-1]
        unit, curr = "元", "CNY"
    row_text = dc
else:  # 兜底：直接从原始文本中定位“营业收入”所在记录的数值
    nums = re.findall(r'"(\d{6,})"', raw)
    assert len(nums) == 2, "无法从CSV导出中定位营业收入数值"
    v23, v24 = int(nums[0]), int(nums[1])
    unit, curr, row_text = "元", "CNY", []

assert v23 > 0 and v24 > 0, "营业收入数值缺失"

# 字体：优先容器预装 Noto Sans CJK JP
avail = sorted({f.name for f in font_manager.fontManager.ttflist})
font_used = None
try:
    font_manager.findfont("Noto Sans CJK JP", fallback_to_default=False)
    font_used = "Noto Sans CJK JP"
except Exception:
    for c in ["Noto Sans CJK SC", "Noto Sans CJK", "Noto Sans CJK TC", "DejaVu Sans"]:
        if c in avail:
            font_used = c
            break
font_used = font_used or "DejaVu Sans"
plt.rcParams["font.family"] = font_used
plt.rcParams["axes.unicode_minus"] = False

values_cny = [v23, v24]
values_yi = [v / 100000000 for v in values_cny]

fig, ax = plt.subplots(figsize=(7.2, 5), dpi=150)
bars = ax.bar([str(y) for y in years], values_yi, width=0.5, color=["#4C78A8", "#F58518"])
ax.set_ylim(0, max(values_yi) * 1.28)
ax.set_xlabel("年份")
ax.set_ylabel("营业收入（亿元）")
ax.set_title("验收示例公司营业收入对比（2023 vs 2024）\n合并口径，单位：亿元")
for b, v, r in zip(bars, values_yi, values_cny):
    ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f} 亿元\n（{r:,} 元）", ha="center", va="bottom", fontsize=9)
ax.grid(axis="y", linestyle="--", alpha=0.4)
ax.set_axisbelow(True)
fig.tight_layout()
os.makedirs("/output", exist_ok=True)
fig.savefig("/output/revenue.png")

chart = {
    "currency": curr if curr in ("CNY", "人民币") else "CNY",
    "source_unit": unit,
    "display_unit": "亿元",
    "years": years,
    "values_cny": values_cny,
    "company": row_text[0] if len(row_text) > 0 else None,
    "metric": "营业收入",
    "scope": norm(row_text[4]) if len(row_text) > 4 else None,
    "document_id": DOC,
    "physical_page": 1,
    "table_id": DOC + ":t0",
    "font_used": font_used,
    "yoy_pct": round((values_cny[1] / values_cny[0] - 1) * 100, 2),
}
with open("/output/chart_data.json", "w", encoding="utf-8") as f:
    json.dump(chart, f, ensure_ascii=False, indent=2)

png_size = os.path.getsize("/output/revenue.png")
fig_bytes = png_size
assert fig_bytes > 10000, "revenue.png 生成异常"
assert json.load(open("/output/chart_data.json", encoding="utf-8"))["values_cny"] == values_cny
with open("/output/run_summary.txt", "w", encoding="utf-8") as f:
    f.write(f"font_used={font_used}\nvalues_cny={values_cny}\nyoy={chart['yoy_pct']}%\npng_bytes={png_size}\n")
print("done", font_used, values_cny, png_size)

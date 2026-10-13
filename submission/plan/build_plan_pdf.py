"""Render 项目计划书.md to an A4 PDF via HTML + headless Chrome.

Usage: python submission/plan/build_plan_pdf.py
"""
import hashlib
import json
import re
from pathlib import Path

import markdown
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = HERE / "项目计划书.md"
HTML = HERE / "项目计划书.html"
PDF = HERE / "项目计划书.pdf"

CSS = """
@page { size: A4; margin: 20mm 18mm 18mm 18mm;
        @bottom-center { content: counter(page) " / " counter(pages); font-size: 8pt; color: #7a8a88; } }
@page :first { @bottom-center { content: none; } }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Microsoft YaHei", "DengXian", "SimHei", sans-serif; font-size: 10.5pt;
       line-height: 1.75; color: #1f2a2e; }
h1 { font-size: 24pt; line-height: 1.3; margin: 70mm 0 6mm; color: #12343b; letter-spacing: .5pt; }
h1 + p { font-size: 13pt; color: #3d5a60; margin-bottom: 18mm; }
h2 { font-size: 15pt; color: #12343b; border-bottom: 2px solid #2e6f6a; padding-bottom: 3pt;
     margin: 16pt 0 8pt; }
h3 { font-size: 12pt; color: #2e6f6a; margin: 12pt 0 4pt; }
h2, h3 { break-after: avoid; page-break-after: avoid; }
h2 + table, h3 + table, p + table { break-before: avoid; }
p { margin: 4pt 0 6pt; text-align: justify; }
ul, ol { margin: 3pt 0 6pt 0; padding-left: 18pt; }
li { margin: 2pt 0; }
strong { color: #12343b; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.5pt;
        page-break-inside: avoid; }
th, td { border: 1px solid #c9d6d4; padding: 4pt 6pt; vertical-align: top; text-align: left; min-width: 3.6em; }
td:first-child, th:first-child { min-width: 6.5em; }
tr { break-inside: avoid; }
th { background: #e8f1ef; color: #12343b; font-weight: 600; }
tr:nth-child(even) td { background: #f7faf9; }
code { font-family: "Consolas", monospace; font-size: 9pt; background: #f1f4f3; padding: 0 2pt; }
img { display: block; max-width: 100%; max-height: 95mm; margin: 6pt auto; }
hr { border: none; border-top: 1px solid #c9d6d4; margin: 12pt 0; }
.pagebreak { page-break-after: always; }
.placeholder { color: #a05a2c; }
.caption { text-align: center; font-size: 9pt; color: #5b6d6a; margin: 0 0 10pt; }
img { border: 1px solid #c9d6d4; }
"""


def render_html(md_text: str) -> str:
    md_text = md_text.replace("<!-- pagebreak -->", '<div class="pagebreak"></div>')
    body = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    # Highlight unfilled placeholders so they cannot slip through unnoticed.
    body = re.sub(r"【([^】]*)】", r'<span class="placeholder">【\1】</span>', body)
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            f"<title>项目计划书</title><style>{CSS}</style></head><body>{body}</body></html>")


def main() -> None:
    HTML.write_text(render_html(SRC.read_text(encoding="utf-8")), encoding="utf-8")
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    with tempfile.TemporaryDirectory() as profile:
        tmp = PDF.with_suffix(".tmp.pdf")
        tmp.unlink(missing_ok=True)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={profile}", f"--print-to-pdf={tmp}", HTML.as_uri()],
                       check=True, capture_output=True)
        if not tmp.exists():
            raise SystemExit("Chrome did not write the PDF")
        try:
            tmp.replace(PDF)
        except PermissionError:
            # A viewer is holding the old PDF open; keep the fresh build beside it.
            fallback = PDF.with_name(PDF.stem + "-最新.pdf")
            tmp.replace(fallback)
            print(f"WARNING: {PDF.name} is locked; wrote {fallback.name}")
            return report(fallback)
    report(PDF)


def report(path: Path) -> None:
    from pypdf import PdfReader  # noqa: WPS433 - optional dependency for page count
    pages = len(PdfReader(str(path)).pages)
    print(json.dumps({"pdf": str(path), "pages": pages,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "placeholders": len(re.findall(r"【[^】]*】", SRC.read_text(encoding="utf-8")))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Actual document parsers; all extracted numbers originate in uploaded files."""
from __future__ import annotations
import csv
import io
import json
import os
import re
import threading
import traceback
from pathlib import Path
from .normalization import compact, decimal_value, metric_id, number_text, period_for, unit_info

PARSER_VERSION = "0.1.4"
MAX_CELLS = 500_000
_OCR_LOCK = threading.Lock()


def _local_ocr_diagnostics(exc, image, cv2):
    """Only local OCR errors: never include config, credentials, or frame locals."""
    causes, current, seen = [], exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        item = {"type": type(current).__module__ + "." + type(current).__name__, "message": str(current)}
        if isinstance(current, cv2.error):
            item["opencv"] = {key: getattr(current, key, None) for key in ("code", "err", "func", "file", "line")}
        causes.append(item)
        current = current.__cause__ or (current.__context__ if not current.__suppress_context__ else None)
    return {"stage": "local_ocr", "image_shape": list(image.shape), "image_dtype": str(image.dtype),
            "opencv_threads": cv2.getNumThreads(), "onnx_intra_threads": 1, "onnx_inter_threads": 1,
            "causes": causes, "traceback": "".join(traceback.format_exception(exc))}

def discover_metadata(text, filename):
    company = None
    for pattern in [r"公司的中文名称[：:\s]*([\u4e00-\u9fffA-Za-z（）()·]+(?:股份有限公司|有限公司))",
                    r"([\u4e00-\u9fff]{2,40}股份有限公司)\s*(?:20\d{2}|年度报告)"]:
        found = re.search(pattern, text)
        if found:
            company = found.group(1)
            break
    years = re.findall(r"(20\d{2})\s*年(?:度)?报告", text[:5000])
    if not years:
        years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", filename)
    return company or Path(filename).stem, int(years[0]) if years else None

def printed_page(text):
    last = text.strip().splitlines()[-1:] or [""]
    m = re.fullmatch(r"\s*(?:-\s*)?(\d{1,4})(?:\s*/\s*\d{1,4}|\s*-)?\s*", last[0])
    return m.group(1) if m else None

def read_delimited(path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError("unsupported_text_encoding")
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        delim = csv.Sniffer().sniff(text[:8192], delimiters=",\t;").delimiter
    except csv.Error:
        pass
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if sum(map(len, rows)) > MAX_CELLS:
        raise ValueError("spreadsheet_exceeds_cell_limit")
    return rows

def excel_tables(path, warnings):
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    if path.suffix.lower() == ".xls":
        import xlrd
        book = xlrd.open_workbook(path)
        tables = []
        for sheet in book.sheets():
            if sheet.nrows * sheet.ncols > MAX_CELLS:
                raise ValueError("spreadsheet_exceeds_cell_limit")
            rows = [[str(sheet.cell_value(r,c)) if sheet.cell_value(r,c) != "" else "" for c in range(sheet.ncols)] for r in range(sheet.nrows)]
            tables.append({"sheet":sheet.name,"rows":rows,"cells":{},"page":len(tables)+1})
        return tables
    formula_book = load_workbook(path, data_only=False, read_only=False, keep_links=False)
    value_book = load_workbook(path, data_only=True, read_only=True, keep_links=False)
    tables = []
    try:
        for sheet in formula_book:
            if (sheet.max_row or 0) * (sheet.max_column or 0) > MAX_CELLS:
                raise ValueError("spreadsheet_exceeds_cell_limit")
            value_rows = iter(value_book[sheet.title].iter_rows())
            rows, cells = [], {}
            for merged in sheet.merged_cells.ranges:
                origin=sheet.cell(merged.min_row,merged.min_col)
                cells[origin.coordinate]={"merged_range":str(merged),"merged_label":str(origin.value or "")}
            for row in sheet.iter_rows():
                cached = next(value_rows)
                values = []
                for idx, cell in enumerate(row):
                    val = cell.value
                    if cell.data_type == "f":
                        cache = cached[idx].value
                        cells.setdefault(cell.coordinate,{}).update({"formula":val, "cached_value":cache})
                        if cache is None:
                            warnings.append(f"{sheet.title}!{cell.coordinate}: formula_without_cached_value")
                        val = cache
                    values.append("" if val is None else str(val))
                rows.append(values)
            tables.append({"sheet":sheet.title,"rows":rows,"cells":cells,"page":len(tables)+1})
    finally:
        formula_book.close()
        value_book.close()
    return tables

def ocr_image(image_bytes, config):
    if config.get("mode", "local") == "disabled":
        return "", [], ["ocr_disabled"]
    if config.get("mode") == "api":
        import base64
        import httpx
        endpoint = config.get("base_url") or config.get("endpoint")
        if not endpoint:
            return "", [], ["ocr_api_not_configured"]
        headers = {"Authorization":"Bearer "+config["api_key"]} if config.get("api_key") else {}
        # Generic OCR JSON contract: image_base64 in, text and optional lines out.
        with httpx.Client(timeout=60, trust_env=False) as client:
            response = client.post(endpoint, json={"image_base64":base64.b64encode(image_bytes).decode(),"language":"zh"}, headers=headers)
            response.raise_for_status()
            body = response.json()
        if not isinstance(body.get("text"), str):
            raise ValueError("ocr_api_invalid_response")
        return body["text"], body.get("lines", []), []
    import numpy as np
    import cv2
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR
    with Image.open(io.BytesIO(image_bytes)) as image:
        pixels = np.array(image.convert("RGB"))
    # Concurrency belongs to document workers, not three auto-sized ORT pools
    # plus an OpenCV pool inside every worker. Serialize the shared engine too.
    global _OCR_ENGINE
    with _OCR_LOCK:
        try:
            cv2.setNumThreads(1)
            if "_OCR_ENGINE" not in globals():
                _OCR_ENGINE = RapidOCR(det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False,
                                      intra_op_num_threads=1, inter_op_num_threads=1)
            result, _ = _OCR_ENGINE(pixels)
        except Exception as exc:
            exc.local_ocr_diagnostics = _local_ocr_diagnostics(exc, pixels, cv2)
            raise
    lines = [{"bbox":r[0], "text":r[1], "confidence":r[2]} for r in (result or [])]
    # Reading order based on line baseline, then x. The original OCR boxes remain available.
    lines.sort(key=lambda r:(round(sum(p[1] for p in r["bbox"])/4/12), min(p[0] for p in r["bbox"])))
    return "\n".join(r["text"] for r in lines), lines, []

def parse_document(path, name, progress, cancelled, config):
    pages, tables, warnings = [], [], []
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        os.environ["PYMUPDF_SUGGEST_LAYOUT_ANALYZER"] = "0"
        import fitz
        import sys
        fitz.set_messages(stream=sys.stderr)
        fitz.no_recommend_layout()
        with fitz.open(path) as pdf:
            if pdf.needs_pass:
                raise ValueError("password_protected_pdf")
            if len(pdf) > 1500:
                raise ValueError("pdf_exceeds_1500_pages")
            previous_year_columns = {}
            for n, page in enumerate(pdf, 1):
                if cancelled():
                    raise InterruptedError("cancelled")
                text = page.get_text("text", sort=True)
                ocr_lines = []
                did_ocr = len(re.sub(r"\s+", "", text)) < 25
                if did_ocr:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2,2))
                    image_bytes = pix.tobytes("png")
                    del pix  # Release the raster before PIL/NumPy allocate their copies.
                    try:
                        text, ocr_lines, new_warnings = ocr_image(image_bytes, config.get("ocr",{}))
                    except Exception as exc:
                        if hasattr(exc, "local_ocr_diagnostics"):
                            exc.local_ocr_diagnostics["page"] = n
                        raise
                    finally:
                        del image_bytes
                    warnings.extend(f"p{n}: {w}" for w in new_warnings)
                pages.append({"page":n, "text":text, "printed_page":printed_page(text), "width":page.rect.width,
                              "height":page.rect.height,"ocr":did_ocr,"ocr_lines":ocr_lines,
                              "words":[{"text":word[4],"bbox":list(word[:4])} for word in page.get_text("words")] if not did_ocr else []})
                if not did_ocr:
                    page_tables = []
                    try:
                        found = page.find_tables()
                        for index, table in enumerate(found.tables):
                            rows = table.extract()
                            if rows:
                                centers, cells = {}, {}
                                for row_number, extracted_row in enumerate(table.rows,1):
                                    for col, rect in enumerate(extracted_row.cells):
                                        if rect is not None:
                                            centers.setdefault(col, (rect[0]+rect[2])/2)
                                            cells[_column_name(col+1)+str(row_number)]={"bbox":list(rect)}
                                page_tables.append({"page":n,"rows":rows,"bbox":list(table.bbox),"sheet":None,"cells":cells,"index":index,"column_centers":centers})
                    except Exception as exc:
                        warnings.append(f"p{n}: table_detection_{type(exc).__name__}")
                    from .native_tables import native_text_tables
                    supplements = native_text_tables(page, [table["bbox"] for table in page_tables])
                    tables.extend(page_tables)
                    tables.extend({"page":n, **table} for table in supplements)
                else:
                    tables.extend({"page":n,"sheet":None,"ocr":True,**table} for table in ocr_tables(ocr_lines))
                progress(n / len(pdf) * .85, f"已解析 {n}/{len(pdf)} 页")
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        from PIL import Image
        img = Image.open(path)
        if img.width * img.height > 40_000_000:
            raise ValueError("image_exceeds_pixel_limit")
        text, lines, new_warnings = ocr_image(path.read_bytes(), config.get("ocr", {}))
        warnings.extend(new_warnings)
        pages = [{"page":1,"text":text,"width":img.width,"height":img.height,"ocr":True,"ocr_lines":lines}]
        tables = [{"page":1,"sheet":None,"ocr":True,**table} for table in ocr_tables(lines)]
    elif suffix in {".xlsx",".xls",".csv",".tsv"}:
        tables = excel_tables(path, warnings) if suffix in {".xlsx",".xls"} else [{"sheet":Path(name).stem,"rows":read_delimited(path),"page":1,"cells":{}}]
        for table in tables:
            pages.append({"page":table["page"],"text":"\n".join("\t".join(str(c or "") for c in row) for row in table["rows"]),"ocr":False})
    elif suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("document_json_requires_object")
        source_id = data.get("source_id", Path(name).stem)
        segments = []
        for key in ("pre_text", "post_text", "text"):
            for entry in data.get(key, []) if isinstance(data.get(key), list) else []:
                if isinstance(entry, dict):
                    segments.append({"source_id":entry.get("id"),"text":entry.get("text","")})
                else:
                    segments.append({"source_id":f"{source_id}:text_{len(segments)}","text":str(entry)})
        raw_rows = data.get("table", [])
        rows = [r.get("cells",[]) if isinstance(r,dict) else r for r in raw_rows]
        source_rows = [r.get("id",f"{source_id}:table_{i}") if isinstance(r,dict) else f"{source_id}:table_{i}" for i,r in enumerate(raw_rows)]
        tables = [{"page":1,"rows":rows,"cells":{},"sheet":None,"source_rows":source_rows}]
        pages = [{"page":1,"text":"\n".join(s["text"] for s in segments)+"\n"+"\n".join(" | ".join(str(c) for c in r) for r in rows),
                  "segments":segments,"ocr":False}]
    else:
        raise ValueError("unsupported_document_type")
    all_text = "\n".join(p["text"] for p in pages[:20])
    company, report_year = discover_metadata(all_text, name)
    if not pages or not any(p["text"].strip() for p in pages):
        warnings.append("no_text_extracted")
    for index, table in enumerate(tables):
        table["index"] = index
        table["rows"] = [["" if c is None else str(c) for c in row] for row in table.get("rows", [])]
    return {"pages":pages,"tables":tables,"company":company,"report_year":report_year,"warnings":warnings,"kind":suffix}

def ocr_rows(lines):
    if not lines:
        return []
    groups = []
    for line in sorted(lines, key=lambda a:sum(p[1] for p in a["bbox"])/4):
        y = sum(p[1] for p in line["bbox"])/4
        h = max(p[1] for p in line["bbox"]) - min(p[1] for p in line["bbox"])
        target = next((g for g in reversed(groups[-3:]) if abs(g["y"]-y) < max(9,h*.7)), None)
        if target is None:
            target = {"y":y, "items":[]}
            groups.append(target)
        target["items"].append(line)
    return [[line["text"] for line in sorted(g["items"],key=lambda a:min(p[0] for p in a["bbox"]))] for g in groups]

def ocr_tables(lines):
    """Align OCR financial columns by physical year-header coordinates, never token-list positions."""
    if not lines: return []
    enriched=[dict(r,x=sum(p[0] for p in r["bbox"])/4,y=sum(p[1] for p in r["bbox"])/4) for r in lines]
    headers=[]
    for item in sorted(enriched,key=lambda r:r["y"]):
        match=re.fullmatch(r"(20\d{2})年?(?:末|度)?",compact(item["text"]))
        if not match:continue
        group=next((g for g in headers if abs(g["y"]-item["y"])<12),None)
        if group is None:
            group={"y":item["y"],"items":[]};headers.append(group)
        group["items"].append(item|{"year":int(match.group(1))})
    headers=[h for h in headers if len(h["items"])>=2]
    result=[]
    for header_index,header in enumerate(headers):
        anchors=sorted(header["items"],key=lambda a:a["x"])
        spacing=min(b["x"]-a["x"] for a,b in zip(anchors,anchors[1:]))
        if spacing<=0:continue
        tolerance=spacing*.47
        lower=header["y"]+10
        upper=headers[header_index+1]["y"]-10 if header_index+1<len(headers) else float("inf")
        numeric=[]
        for item in enriched:
            if not lower<item["y"]<upper or decimal_value(item["text"]) is None:continue
            best=min(range(len(anchors)),key=lambda i:abs(item["x"]-anchors[i]["x"]))
            if abs(item["x"]-anchors[best]["x"])<=tolerance:
                numeric.append(item|{"column":best+1})
        groups=[]
        for item in sorted(numeric,key=lambda r:r["y"]):
            group=next((g for g in reversed(groups[-2:]) if abs(g["y"]-item["y"])<12),None)
            if group is None:group={"y":item["y"],"items":[]};groups.append(group)
            group["items"].append(item)
        groups=[g for g in groups if len({i["column"] for i in g["items"]})>=2]
        rows=[["指标"]+[str(a["year"])+"年" for a in anchors]];cells={}
        for idx,group in enumerate(groups):
            low=(groups[idx-1]["y"]+group["y"])/2 if idx else lower
            high=(group["y"]+groups[idx+1]["y"])/2 if idx+1<len(groups) else min(upper,group["y"]+25)
            labels=[i for i in enriched if low<i["y"]<high and i["x"]<anchors[0]["x"]-tolerance]
            label="".join(i["text"] for i in sorted(labels,key=lambda r:r["y"]))
            row=[label]+[""]*len(anchors)
            for item in group["items"]:
                col=item["column"]
                row[col]=item["text"]
                cells[f"{_column_name(col+1)}{len(rows)+1}"]={"bbox":item["bbox"],"confidence":item.get("confidence"),"raw_text":item["text"]}
            rows.append(row)
        if len(rows)>1:result.append({"rows":rows,"cells":cells,"bbox":None})
    return result or [{"rows":ocr_rows(lines),"cells":{},"bbox":None}]

def extract_facts(parsed, document_id):
    facts = []
    pages = {p["page"]:p for p in parsed["pages"]}
    inherited = None
    def subannual_header(cell):
        text = compact(cell).lower()
        # December 31 and January–December are valid annual balance/flow headers.
        text = re.sub(r"20\d{2}年12月31日", "年末", text)
        text = re.sub(r"(?<!\d)1月?[-—–~至到]12月份?", "全年", text)
        if re.search(r"季度|[一二三四1-4]季|半年|月度|[本上当]月|"
                     r"quarter|semiannual|halfyear|(?:three|six|nine|3|6|9)months?|"
                     r"(?:^|[^a-z])(?:q[1-4]|h[12])(?!\d)|(?<!\d)(?:0?[1-9]|1[0-2])月", text):
            return True
        return any((int(month),int(day)) != (12,31)
                   for month,day in re.findall(r"20\d{2}[-/](\d{1,2})[-/](\d{1,2})", text))
    for table in parsed["tables"]:
        rows = table["rows"]
        context = pages[table["page"]]["text"]
        table_id = f"{document_id}:t{table['index']}"
        header_map = {}
        prior_header = {}
        for row_index, row in enumerate(rows):
            if not any(metric_id(c) for c in row[:3]) and any(subannual_header(c) for c in row):
                # An explicit new period header terminates annual inheritance.
                # Keep the raw table/page unchanged; this fact schema is annual-only.
                inherited = None
                break
            row_years = {}
            for col, cell in enumerate(row):
                yrs = re.findall(r"(?<!\d)(20\d{2})(?:年|年度|[/-]12[/-]31)?(?!\d)", compact(cell))
                if len(yrs) == 1 and decimal_value(cell) is None or (len(yrs)==1 and compact(cell)==yrs[0]):
                    row_years[col] = int(yrs[0])
            if len(row_years) >= 2:
                header_map = row_years
                inherited = (table["page"], len(row), header_map.copy(),table.get("column_centers",{}))
                continue
            if not header_map and inherited and inherited[0] == table["page"]-1:
                # Continuation requires a leading metric AND matching physical column centers.
                # PDF table detectors may insert different empty columns on adjacent pages.
                if any(metric_id(c) for c in row[:3]):
                    centers = table.get("column_centers",{})
                    if centers and inherited[3]:
                        for old_col, year in inherited[2].items():
                            if old_col not in inherited[3]: continue
                            best=min(centers,key=lambda c:abs(centers[c]-inherited[3][old_col]))
                            if abs(centers[best]-inherited[3][old_col]) < 12:
                                header_map[best]=year
                    elif inherited[1] == len(row):
                        header_map = inherited[2]
            metric, label_col = None, None
            for col, cell in enumerate(row[:3]):
                candidate = metric_id(cell)
                if candidate:
                    metric, label_col = candidate, col
                    break
            if metric is None or not header_map:
                continue
            # Annual records require explicit year columns. A quarterly table has no such map.
            label = row[label_col]
            raw_unit, factor, currency = unit_info(label, metric)
            if raw_unit is None:
                # Prefer declared unit near the table, then explicit spreadsheet unit column.
                explicit = re.findall(r"单位[：:]\s*([^\n]{1,30})", context[:max(0, context.find(label.replace("\n",""))) or len(context)])
                unit_context = explicit[-1] if explicit else ""
                for i, value in enumerate(row):
                    if compact(value) in {"元", "千元", "万元", "亿元", "CNY", "USD"}:
                        unit_context = value
                raw_unit, factor, currency = unit_info(unit_context, metric)
            if factor is None:
                continue  # Unknown units are not silently treated as RMB yuan.
            scope = "parent_CAS" if "母公司" in context[:300] and "合并" not in context[:300] else "consolidated_CAS"
            if parsed.get("kind") in {".xlsx",".xls",".csv",".tsv",".json"} and "合并" not in context and "母公司" not in context:
                scope = "unspecified"
            priority = 100 if "主要会计数据" in context else 80 if "合并" in context[:400] else 50
            if "国际财" in context and priority < 100:
                priority = 30
            for col, year in header_map.items():
                if col >= len(row) or col == label_col:
                    continue
                value = decimal_value(row[col])
                if value is None:
                    continue
                if "%" in row[col] and currency != "percent":
                    continue  # A growth column must never become a currency amount.
                source = {"document_id":document_id,"page":table["page"],"table_id":table_id,
                          "row":row_index+1,"column":col+1,"cell":f"{_column_name(col+1)}{row_index+1}","text":f"{label}: {row[col]} {raw_unit}"}
                if table.get("sheet"):
                    source["sheet"] = table["sheet"]
                cell_metadata = table.get("cells",{}).get(source["cell"],{})
                if cell_metadata.get("bbox") is not None:
                    source["bbox"] = cell_metadata["bbox"]
                    source["ocr_confidence"] = cell_metadata.get("confidence")
                if table.get("source_rows") and row_index < len(table["source_rows"]):
                    source["source_id"] = table["source_rows"][row_index]
                facts.append({"metric":metric,"year":year,"period":period_for(year,metric),"scope":scope,
                              "currency":currency,"raw_value":row[col],"raw_unit":raw_unit,"value":number_text(value*factor),
                              "source":source,"priority":priority,"quality":"ocr_review" if table.get("ocr") else "parsed"})
    return facts

def _column_name(index):
    chars = ""
    while index:
        index, rem = divmod(index-1,26)
        chars = chr(65+rem)+chars
    return chars

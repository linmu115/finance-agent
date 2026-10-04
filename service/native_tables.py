"""Recover unruled native PDF tables from word coordinates, without semantics.

The layout proposes source cells only. Financial status, headings, labels,
dates and units are still decided by the model reading these rows and the page.
"""
from __future__ import annotations

from statistics import median

from .normalization import decimal_value, numeric_candidate


def _bbox(words):
    return [min(word["bbox"][0] for word in words), min(word["bbox"][1] for word in words),
            max(word["bbox"][2] for word in words), max(word["bbox"][3] for word in words)]


def _cell_name(column, row):
    name = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        name = chr(65 + remainder) + name
    return name + str(row)


def _lines(words):
    lines = []
    for word in sorted(words, key=lambda item: ((item["bbox"][1] + item["bbox"][3]) / 2, item["bbox"][0])):
        box = word["bbox"]
        y, height = (box[1] + box[3]) / 2, box[3] - box[1]
        target = next((line for line in reversed(lines[-3:]) if abs(line["y"] - y) <= min(line["height"], height) * .45), None)
        if target is None:
            target = {"y": y, "height": height, "words": []}
            lines.append(target)
        target["words"].append(word)
    for line in lines:
        line["words"].sort(key=lambda item: item["bbox"][0])
        line["bbox"] = _bbox(line["words"])
        runs = []
        for word in line["words"]:
            if not runs or word["bbox"][0] - runs[-1][-1]["bbox"][2] > max(8, line["height"] * 1.15):
                runs.append([])
            runs[-1].append(word)
        line["runs"] = [{"text": " ".join(word["text"] for word in run), "bbox": _bbox(run), "words": run} for run in runs]
    return sorted(lines, key=lambda item: item["y"])


def _numeric_runs(line):
    # A page number or numbered paragraph alone is not a tabular value.
    # This is a geometric/text-shape test, with no financial vocabulary.
    return [run for index, run in enumerate(line["runs"]) if index > 0 and numeric_candidate(run["text"])]


def _anchors(lines):
    clusters = []
    for row, line in enumerate(lines):
        for run in _numeric_runs(line):
            left, _, right, _ = run["bbox"]
            tolerance = max(2.5, line["height"] * .3)
            match = next((group for group in clusters if row not in group["rows"]
                          and (abs(group["left"] - left) <= tolerance or abs(group["right"] - right) <= tolerance)), None)
            if match is None:
                match = {"left": left, "right": right, "rows": set(), "runs": []}
                clusters.append(match)
            match["rows"].add(row)
            match["runs"].append(run)
            # Keep median edges so ragged, left-aligned and right-aligned
            # numerical columns all preserve their original whole tokens.
            match["left"] = median(item["bbox"][0] for item in match["runs"])
            match["right"] = median(item["bbox"][2] for item in match["runs"])
    return sorted(clusters, key=lambda group: (group["left"] + group["right"]) / 2)


def _table(lines, candidates, page_width):
    groups = _anchors(candidates)
    if not groups:
        return None
    # One row needs at least two numeric columns. A single numeric column
    # needs repeated physical alignment across at least two labelled rows.
    if not (any(len(group["rows"]) >= 2 for group in groups) or any(len(_numeric_runs(line)) >= 2 for line in candidates)):
        return None
    numeric_left = min(run["bbox"][0] for group in groups for run in group["runs"])
    prefix_rights = [run["bbox"][2] for line in candidates for run in line["runs"]
                    if run["bbox"][2] < numeric_left - 2 and decimal_value(run["text"]) is None]
    if not prefix_rights:
        return None
    boundaries = [(max(prefix_rights) + numeric_left) / 2]
    for left, right in zip(groups, groups[1:]):
        boundaries.append((max(item["bbox"][2] for item in left["runs"])
                           + min(item["bbox"][0] for item in right["runs"])) / 2)
    if any(a >= b for a, b in zip(boundaries, boundaries[1:])):
        return None
    rows, cells = [], {}
    for line in lines:
        columns = [[] for _ in range(len(groups) + 1)]
        for run in line["runs"]:
            x = (run["bbox"][0] + run["bbox"][2]) / 2
            column = sum(x >= boundary for boundary in boundaries)
            columns[column].extend(run["words"])
        rows.append([" ".join(word["text"] for word in column) for column in columns])
        for column, words in enumerate(columns, 1):
            if words:
                cells[_cell_name(column, len(rows))] = {"bbox": _bbox(words), "raw_text": rows[-1][column - 1],
                    "source_words": words, "extraction_method": "native_word_layout"}
    if not any(numeric_candidate(cell) for row in rows for cell in row):
        return None
    bounds = _bbox([word for line in lines for word in line["words"]])
    edges = [bounds[0], *boundaries, max(bounds[2], boundaries[-1])]
    return {"rows": rows, "cells": cells, "bbox": bounds, "sheet": None,
            "extraction_method": "native_word_layout",
            "column_centers": {index: (left + right) / 2 for index, (left, right) in enumerate(zip(edges, edges[1:]))},
            "layout": {"column_boundaries": boundaries, "row_boxes": [line["bbox"] for line in lines],
                       "page_width": page_width}}


def native_text_tables(page, existing_boxes=()):
    """Supplement ruled tables with word-aligned regions not already covered.

    No native word is split at a guessed grid boundary. In particular a header
    such as '2024 年度' cannot become '20' and '24 年度' in adjacent cells.
    """
    words = []
    for raw in page.get_text("words"):
        x0, y0, x1, y1, text = raw[:5]
        if not str(text).strip():
            continue
        center = ((x0 + x1) / 2, (y0 + y1) / 2)
        if any(box[0] - .5 <= center[0] <= box[2] + .5 and box[1] - .5 <= center[1] <= box[3] + .5 for box in existing_boxes if box):
            continue
        words.append({"text": str(text), "bbox": [x0, y0, x1, y1]})
    if not words:
        return []
    lines = _lines(words)
    candidates = [index for index, line in enumerate(lines) if _numeric_runs(line)]
    if not candidates:
        return []
    height = median(line["height"] for line in lines)
    regions = []
    for index in candidates:
        if not regions or lines[index]["y"] - lines[regions[-1][-1]]["y"] > max(40, height * 4):
            regions.append([])
        regions[-1].append(index)
    result = []
    used = set()
    for region in regions:
        begin, end = region[0], region[-1]
        # Keep nearby headings/continuation labels as raw context rows. The
        # program does not assert these rows are headers or assign their units.
        first = begin
        while first > 0 and first - 1 not in used and begin - first < 4:
            if lines[first]["y"] - lines[first - 1]["y"] > max(40, height * 3.5):
                break
            first -= 1
        table = _table(lines[first:end + 1], [lines[index] for index in region], page.rect.width)
        if table:
            result.append(table)
            used.update(range(first, end + 1))
    return result

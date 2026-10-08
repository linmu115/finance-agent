"""Read known statement labels aligned with original PDF amounts.

Merged PDF cells can pack many logical rows. Pair by original text geometry,
not numeric order or a guessed row count. Unknown/wrapped labels stay unmapped.
"""
from collections import defaultdict
import json
import re

from .normalization import decimal_value
from .standard_metrics import standard_metric, STANDARD_METRICS
from .cleaning_sdk import Cleaner


def geometry_rows(parsed, table, schema):
    words = next(p for p in parsed['pages'] if p['page'] == table['page']).get('words', [])
    cells = table.get('cells') or {}
    label_boxes = [v['bbox'] for k, v in cells.items() if re.fullmatch(r'A\d+', k) and v.get('bbox')]
    if not words or not label_boxes: return []
    left = min(b[0] for b in label_boxes); right = min(b[2] for b in label_boxes)
    columns = json.loads(schema['columns_json'])
    cleaner = Cleaner.__new__(Cleaner); cleaner.tables = {table['index']: table}
    mapped = defaultdict(list)
    for c in columns:
        if c['period'] == 'unknown': continue
        for ri, row in enumerate(table['rows'], 1):
            ci = c['column']
            if ci > len(row): continue
            # Existing parser cell names are Excel-style, one-based.
            column = ''; n = ci
            while n: n, v = divmod(n - 1, 26); column = chr(65 + v) + column
            box = cells.get(column + str(ri), {}).get('bbox')
            if not box: continue
            spans = cleaner.numeric_spans(table['index'], ri, ci)
            for span in spans:
                value = decimal_value(span['text'])
                matches = [w for w in words if decimal_value(w['text']) == value
                           and box[0] <= (w['bbox'][0] + w['bbox'][2]) / 2 <= box[2]
                           and box[1] <= (w['bbox'][1] + w['bbox'][3]) / 2 <= box[3]]
                peers = [s for s in spans if decimal_value(s['text']) == value]
                if len(matches) != len(peers): continue
                amount_word = sorted(matches, key=lambda w: w['bbox'][1])[peers.index(span)]
                y = sum(amount_word['bbox'][1::2]) / 2
                tolerance = (amount_word['bbox'][3] - amount_word['bbox'][1]) / 5
                aligned = sorted([w for w in words if left <= w['bbox'][0] < right
                                  and abs(sum(w['bbox'][1::2]) / 2 - y) <= tolerance], key=lambda w: w['bbox'][0])
                label = ' '.join(w['text'] for w in aligned)
                metric = standard_metric(label)
                if metric not in STANDARD_METRICS or metric in ('eps', 'eps_diluted', 'roe'): continue
                mapped[ri].append(c | {'metric': metric, 'label': label, 'numeric_span': span,
                    'source_geometry': {'label': label, 'label_bbox': [min(w['bbox'][0] for w in aligned),
                        min(w['bbox'][1] for w in aligned), max(w['bbox'][2] for w in aligned), max(w['bbox'][3] for w in aligned)],
                        'amount_bbox': amount_word['bbox'], 'method': 'PDF原字坐标横向对齐'}})
    return [{'row': ri, 'attributes': {'metric': values[0]['metric'], 'label': values[0]['label'],
                                      'row_subject': False, 'columns_json': json.dumps(values, ensure_ascii=False)}}
            for ri, values in mapped.items()]

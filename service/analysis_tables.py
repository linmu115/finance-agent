"""Read completed, verified artifacts as exact numeric tables. Never execute them."""
import csv
from decimal import Decimal, InvalidOperation
import json
import re
from .analysis_report import canonical_unit, format_cell


def numeric(value):
    if value is None or isinstance(value, bool): return False
    try: return Decimal(str(value).replace(',', '')).is_finite()
    except InvalidOperation: return False


def header_column(header):
    """Only explicit units are parsed; an unlabelled column stays unlabelled."""
    col = {'label': header}
    candidates = re.findall(r'[（(]([^()（）]+)[）)]', header)
    candidates += [match.group(0) for match in re.finditer(r'(?:人民币|港币|港元|美元|CNY|RMB|HKD|USD|HK\$)(?:[/ _\w股元百千亿万%.-]*)$', header, re.I)]
    candidates += [header]
    for text in candidates:
        try: unit, currency = canonical_unit(text)
        except ValueError: continue
        col.update(unit=unit)
        if currency: col['currency'] = currency
        break
    return col


def with_row_keys(table):
    if 'row_keys' in table: return table
    rows, columns = table['rows'], table['columns']
    if table.get('row_key'):
        keys = [str(row[table['row_key']]) for row in rows]
    else:
        # Use explicit text dimensions (often metric + period), not a numeric result.
        dimensions = [k for k, col in columns.items() if not col.get('unit') and
                      (k.casefold() in ('period', 'year', 'date', '期间', '年度', '年份') or any(row.get(k) not in (None, '') and not numeric(row.get(k)) for row in rows))
                      and k.casefold() not in ('unit', '单位', 'source', '来源')]
        keys = []
        for size in range(1, len(dimensions) + 1):
            keys = ['|'.join(str(row.get(k, '')) for k in dimensions[:size]) for row in rows]
            if len(set(keys)) == len(rows): break
        if not keys and len(columns) > 1:
            first = next(iter(columns)); keys = [str(row.get(first, '')) for row in rows]
        if not keys or len(set(keys)) != len(rows): keys = [str(i) for i in range(len(rows))]
    return {**table, 'row_keys': keys}


def csv_table(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        if len(set(headers)) != len(headers):
            raise ValueError('CSV 表头有重复列名，不能唯一引用；请使用 get_artifact 读取原文')
        rows = list(reader)
    if not rows or not any(numeric(v) for row in rows for v in row.values()): return None
    columns = {key: header_column(key) for key in headers}
    for key, col in columns.items():
        if any(numeric(row.get(key)) for row in rows) and not re.search(r'year|date|period|年度|财年|期间|年份', key, re.I): col['numeric'] = True
    cell_units = []
    unit_key = next((k for k in headers if k.casefold() in ('unit', '单位')), None)
    for row in rows:
        units = {}
        if unit_key and row[unit_key]:
            stated = header_column(row[unit_key])
            if 'unit' in stated:
                for key, col in columns.items():
                    if col.get('numeric') and 'unit' not in col:
                        units[key] = {k: v for k, v in stated.items() if k != 'label'}
        cell_units.append(units)
        for key, value in row.items():
            if numeric(value): row[key] = value.replace(',', '')
            elif value == '': row[key] = None
    return with_row_keys({'columns': columns, 'rows': rows, 'cell_units': cell_units,
                          'unit_note': '单位仅按文件的显式标注读取；混合行单位不能证明同比列是比例还是百分点。' if unit_key else None})


def collect_tables(paths):
    """paths are already authorized, manifest-verified outputs, supplied by the runner."""
    tables, warnings = {}, []
    for name, path in paths.items():
        if path.suffix.lower() != '.csv': continue
        try: table = csv_table(path)
        except (ValueError, csv.Error, UnicodeError) as exc:
            warnings.append({'file': name, 'error': str(exc)}); continue
        if table: tables[path.stem] = {**table, 'artifact': name, 'origin': 'csv'}
    # Typed metadata takes precedence over its CSV export. save_table and reports
    # share this file; chart_data supports reports made before the registry existed.
    for name in ('chart_data.json', 'numeric_tables.json'):
        if name not in paths: continue
        try: value = json.loads(paths[name].read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            warnings.append({'file': name, 'error': str(exc)}); continue
        for key, table in value.get('tables', {}).items() if isinstance(value, dict) and isinstance(value.get('tables'), dict) else []:
            if not isinstance(table, dict) or not isinstance(table.get('columns'), dict) or not isinstance(table.get('rows'), list): continue
            tables[key] = {**with_row_keys(table), 'artifact': name, 'origin': 'report'}
    if 'models.json' in paths:
        from .analysis_report import model_quantity
        models = json.loads(paths['models.json'].read_text(encoding='utf-8-sig'))
        for alias, model in models.items():
            for name, rows in model['result'].get('tables', {}).items():
                key = alias + '_' + name
                if key not in tables: continue
                table = tables[key]
                for column in table['columns']:
                    if not rows or not numeric(rows[0].get(column)): continue
                    try: quantity = model_quantity(model, f'tables.{name}.0.{column}')
                    except ValueError as exc:
                        warnings.append({'table': key, 'column': column, 'error': str(exc)}); continue
                    # Model CSV values use model scale; resolve every numeric cell to
                    # canonical base units, preserving exact values and input provenance.
                    table['columns'][column].update(unit=quantity['unit'], currency=quantity.get('currency'))
                    for i, row in enumerate(rows):
                        table['rows'][i][column] = model_quantity(model, f'tables.{name}.{i}.{column}')['value']
    return tables, warnings


def table_view(table):
    """Exact values plus rendered cells; source evidence remains in the artifact."""
    result = {key: table[key] for key in ('columns', 'rows', 'row_keys', 'cell_units', 'artifact', 'origin', 'unit_note') if key in table}
    result['display_rows'] = [{k: format_cell(v, {**table['columns'][k], **table.get('cell_units', [{}] * len(table['rows']))[i].get(k, {})}, with_unit=True)
                               for k, v in row.items() if numeric(v)} for i, row in enumerate(table['rows'])]
    return result


def artifact_content(path, rows=None):
    """Zero-based [start,end) CSV records / JSON array items / text lines."""
    if path.suffix.lower() not in ('.csv', '.json', '.md', '.txt'): return {}
    start = (rows or {}).get('start', 0)
    end = (rows or {}).get('end')
    if not isinstance(start, int) or start < 0 or end is not None and (not isinstance(end, int) or end < start):
        raise ValueError('rows 使用从 0 开始的 {start,end}，end 不包含在范围内')
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f); items = list(reader); headers = reader.fieldnames
        return {'columns': headers, 'content': items[start:end], 'rows': {'start': start, 'end': min(end if end is not None else len(items), len(items)), 'total': len(items)}}
    if path.suffix.lower() == '.json':
        value = json.loads(text)
        if isinstance(value, list):
            return {'content': value[start:end], 'rows': {'start': start, 'end': min(end if end is not None else len(value), len(value)), 'total': len(value)}}
        if not rows: return {'content': value}
    lines = text.splitlines()
    return {'content': '\n'.join(lines[start:end]), 'rows': {'start': start, 'end': min(end if end is not None else len(lines), len(lines)), 'total': len(lines)}}

"""One numeric presentation shared by CSV, Markdown and charts in every profile.

Runs inside the analysis sandbox. It does not evaluate expressions or fetch data.
Custom Python can supply derived quantities; record/model references use the
mounted snapshots. Values stay Decimal until Matplotlib needs a float.
"""
from copy import deepcopy
import csv
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re
import unicodedata
import zipfile


MONEY = {'元': '1', '千元': '1000', '万元': '10000', '百万元': '1000000',
         '亿元': '100000000', '十亿元': '1000000000', '千亿元': '100000000000',
         'units': '1', 'thousand': '1000', 'million': '1000000', 'billion': '1000000000'}
UNITS = {**{k: ('money', v) for k, v in MONEY.items()},
         '股': ('shares', '1'), '万股': ('shares', '10000'), '百万股': ('shares', '1000000'), '亿股': ('shares', '100000000'),
         'ratio': ('ratio', '1'), '%': ('ratio', '0.01'),
         '个百分点': ('percentage_points', '1'), 'pp': ('percentage_points', '1'),
         '元/股': ('per_share', '1'), 'currency/share': ('per_share', '1'),
         '倍': ('multiple', '1'), 'times': ('multiple', '1'), '个': ('count', '1'), '天': ('days', '1')}


# Other ways the same units are commonly written. Matching ignores case, spaces, brackets and full-width forms.
SPELLINGS = {'percent': '%', 'pct': '%', '百分比': '%', '百分数': '%',
             '百分点': '个百分点', 'ppt': '个百分点', 'ppts': '个百分点', 'percentagepoint': '个百分点', 'percentagepoints': '个百分点',
             '比例': 'ratio', '比率': 'ratio', '小数': 'ratio',
             'x': '倍', '×': '倍', 'shares': '股', 'share': '股', '日': '天', 'day': '天', 'days': '天'}
CURRENCIES = {'人民币': 'CNY', 'rmb': 'CNY', 'cny': 'CNY', '¥': 'CNY', '港元': 'HKD', '港币': 'HKD', 'hkd': 'HKD', 'hk$': 'HKD',
              '美元': 'USD', 'usd': 'USD', 'us$': 'USD', '欧元': 'EUR', 'eur': 'EUR', '€': 'EUR', '日元': 'JPY', 'jpy': 'JPY',
              '英镑': 'GBP', 'gbp': 'GBP', '£': 'GBP'}
MAGNITUDES = {'': '元', '千': '千元', '万': '万元', '百万': '百万元', '亿': '亿元', '十亿': '十亿元', '千亿': '千亿元',
              'thousand': 'thousand', '000': 'thousand', 'k': 'thousand', 'million': 'million', 'mn': 'million', 'mm': 'million', 'm': 'million',
              'billion': 'billion', 'bn': 'billion', 'b': 'billion'}
ACCEPTED = ('金额：元/千元/万元/百万元/亿元/十亿元、thousand/million/billion，可带币种（人民币百万元、RMB million、亿港元）；'
            '每股：元/股、人民币/股；股数：股/万股/百万股/亿股；比例：ratio（0.10=10%）、%；百分点：个百分点、百分点、pp；倍；个；天')


def canonical_unit(text):
    """(unit, currency) for any accepted spelling. currency is None unless the text names one.

    '人民币百万元' -> ('百万元', 'CNY'); 'RMB million' -> ('million', 'CNY'); '港元/股' -> ('元/股', 'HKD');
    '百分点' -> ('个百分点', None). An amount needs 元 or a currency: a bare '百万' could be shares.
    """
    if text in UNITS:
        return text, None
    folded = re.sub(r'[\s()\[\]【】]', '', unicodedata.normalize('NFKC', str(text))).casefold()
    for unit in UNITS:
        if unit.casefold() == folded:
            return unit, None
    if folded in SPELLINGS:
        return SPELLINGS[folded], None
    currency, rest = None, folded
    for word in sorted(CURRENCIES, key=len, reverse=True):
        if word in rest:
            currency, rest = CURRENCIES[word], rest.replace(word, '', 1)
            break
    per_share = re.fullmatch(r'(.*)/(?:股|shares?)', rest)
    if per_share:
        rest = per_share.group(1)
    named_yuan = rest.endswith('元')
    magnitude = (rest[:-1] if named_yuan else rest).strip("'’")
    # million/mn/k and the like are amounts only next to a currency; on their own they are the plain units above.
    english = magnitude != '' and magnitude.isascii()
    if (currency or named_yuan) and magnitude in MAGNITUDES and not (english and not currency):
        if not per_share:
            return MAGNITUDES[magnitude], currency
        if magnitude == '':
            return '元/股', currency
    raise ValueError(f'未知单位 {text!r}。{ACCEPTED}')


def stated_quantity(quantity):
    """An explicit {value, unit, currency} cell with its unit in canonical form."""
    unit, currency = canonical_unit(quantity['unit'])
    if currency and quantity.get('currency') and quantity['currency'] != currency:
        raise ValueError(f'单位 {quantity["unit"]!r} 与 currency {quantity["currency"]!r} 的币种不一致')
    return {**quantity, 'unit': unit, 'currency': quantity.get('currency') or currency}


def unit_info(unit):
    dimension, scale = UNITS[canonical_unit(unit)[0]]
    return dimension, Decimal(scale)


def convert(value, source_unit, display_unit):
    source_dimension, source_scale = unit_info(source_unit)
    dimension, scale = unit_info(display_unit)
    if dimension != source_dimension:
        raise ValueError(f'不能把 {source_unit} 换算为 {display_unit}；百分比与百分点、金额与每股金额分别处理')
    if value is None:
        return None
    text = unicodedata.normalize('NFKC', str(value)).strip().replace(',', '')
    if text.endswith('%') and source_dimension == 'ratio':
        source_scale = Decimal('0.01'); text = text[:-1]
    try: number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f'数值 {value!r} 不是可解析数字；单位列为 {source_unit}。缺失写 null；百分数可写 12.2% 或 {{value:0.122,unit:"ratio"}}') from None
    if not number.is_finite():
        raise ValueError('非有限数值不能作为报告金额；缺失请用 null')
    with localcontext() as ctx:
        ctx.prec = max(50, len(number.as_tuple().digits) + 20)
        return format(number * source_scale / scale, 'f')


def at_path(value, path):
    for key in path.split('.'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def record_quantity(record):
    currency = record['currency']
    special = {'percent': '%', 'percentage_points': '个百分点', 'shares': '股', '股': '股',
               'multiple': '倍', '倍': '倍', 'count': '个', 'days': '天'}
    if currency in special:
        unit, money = special[currency], None
    elif currency.endswith('/share'):
        unit, money = '元/股', currency.removesuffix('/share')
    elif re.fullmatch('[A-Z]{3}', currency):
        unit, money = '元', currency
    else:
        raise ValueError(f'记录 {record.get("record_id", record.get("fact_id"))} 的规范单位不明：{currency}')
    return {'value': record['value'], 'unit': unit, 'currency': money,
            'source': {k: record[k] for k in ('fact_id', 'record_id', 'document_id', 'metric', 'period', 'scope',
                       'data_kind', 'quality', 'dimensions', 'source_ref') if k in record}}


def model_quantity(model, path, source_unit=None):
    if __package__:
        from .model_units import quantity_unit
    else:
        from model_units import quantity_unit
    info = quantity_unit(model, path)
    source_currency = None
    if source_unit:
        source_unit, source_currency = canonical_unit(source_unit)
    if source_unit and info and source_unit != info['unit']:
        dimension, scale = unit_info(info['unit'])
        # The model's own unit restated at its scale (百万元 for amount_scale 1000000) changes nothing; anything else would relabel the value.
        if unit_info(source_unit) != (dimension, scale * Decimal(str(info.get('scale', '1')))):
            raise ValueError(f'{path} 已有单位 {info["unit"]}，不能改写为 {source_unit}')
    if info is None:
        if source_unit is None:
            raise ValueError(f'{path} 尚无单位元数据；提供明确 source_unit 或用 Python 定义派生量')
        info = {'unit': source_unit, 'scale': '1'}
    currency = None
    if unit_info(info['unit'])[0] in {'money', 'per_share'}:
        # A comparable's own currency is independent of the subject company.
        # If it is not stated here, the report column must state it explicitly.
        peer_input = model['kind'] == 'comparables' and path.startswith('spec.peers.')
        currency = source_currency if peer_input else model['spec']['currency']
        if source_currency and currency != source_currency:
            raise ValueError(f'{path} 的模型币种为 {currency}，source_unit 写的是 {source_currency}；不做隐含换汇')
    # "spec.…" reads a saved input (e.g. spec.discount.wacc); every other path reads the result.
    value = at_path(model['spec'], path[5:]) if path.startswith('spec.') else at_path(model['result'], path)
    if value is not None:
        with localcontext() as ctx:
            ctx.prec = 50
            value = str(Decimal(str(value)) * Decimal(info.get('scale', '1')))
    return {'value': value, 'unit': info['unit'], 'currency': currency,
            'source': {'artifact_id': model['id'], 'revision_id': model['revision_id'], 'path': path,
                       'data_kind': 'model_calculation', 'amount_scale': model['spec']['amount_scale']}}


def match_key(text, mapping, kind='键'):
    if text in mapping: return text
    folded = str(text).strip().casefold()
    found = [key for key, col in mapping.items() if str(key).strip().casefold() == folded or
             isinstance(col, dict) and str(col.get('label', '')).strip().casefold() == folded]
    if len(found) == 1: return found[0]
    raise ValueError(f'{kind} {text!r} 不唯一或不存在；可用：{list(mapping)}')


def row_keys(table):
    if 'row_keys' in table: return table['row_keys']
    rows = table['rows']
    if table.get('row_key'): return [str(row[table['row_key']]) for row in rows]
    labels = [k for k, col in table['columns'].items() if not col.get('unit') and not col.get('per_cell_unit')
              and any(isinstance(r.get(k), str) and not re.fullmatch(r'[-+0-9.,]+', r[k]) for r in rows)]
    for n in range(1, len(labels) + 1):
        keys = ['|'.join(str(r.get(k, '')) for k in labels[:n]) for r in rows]
        if len(set(keys)) == len(rows): return keys
    return [str(i) for i in range(len(rows))]


def cell_column(table, row, key):
    return {**table['columns'][key], **table.get('cell_units', [{}] * len(table['rows']))[row].get(key, {})}


def reference_inventory(tables):
    return {name: {'columns': {k: {a: col[a] for a in ('unit', 'currency', 'per_cell_unit') if a in col}
                               for k, col in t['columns'].items()}, 'row_keys': row_keys(t)} for name, t in tables.items()}


def render_table(table):
    columns = table['columns']
    escape = lambda s: str(s).replace('|', '\\|').replace('\n', ' ')
    headers = [column_label(col) or key for key, col in columns.items()]
    lines = ['| ' + ' | '.join(map(escape, headers)) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines += ['| ' + ' | '.join(escape(format_cell(row[k], cell_column(table, i, k), with_unit=bool(col.get('per_cell_unit'))))
                               for k, col in columns.items()) + ' |' for i, row in enumerate(table['rows'])]
    return '\n'.join(lines)


def bind_text(body, tables, charts=None):
    parts, position = [], 0
    for match in re.finditer(r'\{\{\s*([^{}]+?)\s*\}\}', body):
        token = match.group(1); column = None; value = None
        try:
            if token.startswith('table:'):
                name = match_key(token[6:], tables, '表'); rendered = render_table(tables[name])
            elif token.startswith('chart:'):
                name = match_key(token[6:], charts or {}, '图片'); rendered = f'![{name}]({charts[name]})'
            else:
                name, rest = token.split('.', 1); name = match_key(name, tables, '表'); table = tables[name]
                # Rows and CSV column names may themselves contain decimal points.
                matches = [(rest[:-len(k)-1], k) for k in table['columns'] if rest.endswith('.'+k)]
                if len(matches) == 1: row, key = matches[0]
                else:
                    row, key = rest.rsplit('.', 1); key = match_key(key, table['columns'], '列')
                keys = row_keys(table)
                if row in keys: index = keys.index(row)
                elif row.isdigit() and int(row) < len(table['rows']): index = int(row)
                else: raise ValueError(f'行 {row!r} 不存在；可用行键：{keys}；或从 0 开始的行号')
                column = cell_column(table, index, key); value = table['rows'][index][key]
                rendered = format_cell(value, column, with_unit=True)
        except (ValueError, KeyError, IndexError) as exc:
            raise ValueError(f'占位符 {{{{{token}}}}} 无法解析：{exc}。可用引用：{json.dumps(reference_inventory(tables), ensure_ascii=False)}；可用图片：{list(charts or {})}') from exc
        parts += [body[position:match.start()], rendered]; position = match.end()
        if column and value is not None and column.get('unit'):
            following = body[position:]; text = following.lstrip(' \t')
            for repeated in unit_spellings(column):
                if text.startswith(repeated):
                    position += len(following) - len(text) + len(repeated); break
    return ''.join(parts) + body[position:]


def compile_report(report, records=(), models=None):
    """Resolve typed quantities once. Mixed metric tables retain per-cell units."""
    index = {r.get('fact_id') or r.get('record_id'): r for r in records}
    compiled = deepcopy(report); compiled.setdefault('tables', {})
    for name, table in compiled['tables'].items():
        if not re.fullmatch(r'[\w-]+', name):
            raise ValueError('表名用于文件名，请使用中文、字母、数字、下划线或连字符')
        columns = table['columns']; normalized = []
        for i, row in enumerate(table['rows']):
            new = {}
            for key, cell in row.items():
                try: target = match_key(key, columns, f'{name}.{i} 列键')
                except ValueError:
                    if row.keys() & columns.keys(): continue  # Extra source metadata is not a declared column.
                    raise
                if target in new: raise ValueError(f'{name}.{i} 多个数据键映射到 {target}；请只保留一个')
                new[target] = cell
            normalized.append(new)
        table['rows'] = normalized
        quantities = [{} for _ in normalized]; mixed_columns = set()
        for key, col in columns.items():
            declared = col.get('unit'); named = None
            if declared:
                try: col['unit'], named = canonical_unit(declared)
                except ValueError:
                    if not re.search(r'或|见.*单位|每股除外', declared): raise
                    col.pop('unit'); mixed_columns.add(key)
                if named and col.get('currency') and col['currency'] != named:
                    raise ValueError(f'{name}.{key} 的单位与 currency 写了不同币种')
                if named: col['currency'] = named
            for i, row in enumerate(normalized):
                cell = row.get(key)
                if not isinstance(cell, dict) and not col.get('unit'):
                    if key in mixed_columns and cell is not None:
                        raise ValueError(f'{name}.{i}.{key} 混合列须给每个数值 {{value,unit,currency}}；不能从 {declared!r} 猜单位')
                    continue
                ref = cell if isinstance(cell, dict) else {'value': cell, 'unit': col.get('source_unit', col['unit']), 'currency': col.get('currency')}
                rid = ref.get('fact_id') or ref.get('record_id')
                if rid:
                    if rid not in index: raise ValueError(f'当前导出数据没有记录 {rid}；将所属文档加入 document_ids')
                    quantity = record_quantity(index[rid])
                elif 'model' in ref:
                    quantity = model_quantity((models or {})[ref['model']], ref['path'], ref.get('source_unit'))
                else:
                    if 'unit' not in ref: raise ValueError(f'{name}.{i}.{key} 缺少 unit；给单元格明确单位或给整列 unit。{ACCEPTED}')
                    quantity = stated_quantity(ref)
                dimension = unit_info(quantity['unit'])[0]
                if dimension in {'money', 'per_share'}:
                    quantity['currency'] = quantity.get('currency') or col.get('currency')
                    if not quantity['currency'] and quantity['value'] is not None:
                        raise ValueError(f'{name}.{i}.{key} 需要 currency；在该单元格或列写 currency，例如 CNY / HKD / USD，或用明确单位 人民币百万元 / 港元/股；币种不能从金额大小推断')
                    if col.get('currency') and quantity['currency'] != col['currency']:
                        raise ValueError(f'{name}.{i}.{key} 包含不同币种：列={col["currency"]}，单元格={quantity["currency"]}；请分列或显式换汇计算')
                quantities[i][key] = quantity
            stated = [q[key] for q in quantities if key in q and q[key]['value'] is not None]
            dimensions = {(unit_info(q['unit'])[0], q.get('currency')) for q in stated}
            declared_dimension = unit_info(col['unit'])[0] if col.get('unit') else None
            if not col.get('unit') and stated: mixed_columns.add(key)
            if len(dimensions) > 1 or stated and any(unit_info(q['unit'])[0] != declared_dimension for q in stated):
                # A named row identifies each metric. Without it, incompatible quantities
                # in a single series remain an error, not a silent unit change.
                named_rows = any(not c.get('unit') and all(not isinstance(r.get(k), dict) for r in normalized) for k,c in columns.items() if k != key)
                if named_rows: mixed_columns.add(key)
            if key in mixed_columns:
                if declared: col['declared_unit'] = declared
                col.pop('unit', None); col.pop('currency', None); col['per_cell_unit'] = True
            elif len({q.get('currency') for q in stated if q.get('currency')}) > 1:
                raise ValueError(f'{name}.{key} 包含不同币种；请分列或用带指标行键和明确单元格单位的混合表')
            elif stated and not col.get('currency') and stated[0].get('currency'):
                col['currency'] = stated[0]['currency']
        values, evidence, cell_units = [], [], []
        for i, row in enumerate(normalized):
            displayed, sources, units = {}, {}, {}
            for key, col in columns.items():
                if key not in quantities[i]: displayed[key] = row.get(key); continue
                q = quantities[i][key]
                if key in mixed_columns:
                    # Explicit cell units override a mixed column label; ratio stays ratio,
                    # unless a ratio column explicitly asks for percent display.
                    unit = q['unit']; currency = q.get('currency')
                    units[key] = {'unit': unit, **({'currency': currency} if currency else {})}
                else: unit = col['unit']
                try: displayed[key] = convert(q['value'], q['unit'], unit)
                except ValueError as exc: raise ValueError(f'{name}.{i}.{key}: {exc}；按不同计量对象分列，或用明确单元格单位的指标行') from exc
                sources[key] = q
            values.append(displayed); evidence.append(sources); cell_units.append(units)
        table['rows'], table['evidence'], table['cell_units'] = values, evidence, cell_units
        table['row_keys'] = row_keys(table)
    compiled['body'] = bind_text(compiled.get('body', ''), compiled['tables'],
                                 {f'chart_{i}.png': f'chart_{i}.png' for i,_ in enumerate(compiled.get('charts', []), 1)})
    return compiled


def unit_spellings(column):
    """How the unit of a column may be typed straight after its placeholder, longest first."""
    unit, currency = column['unit'], column.get('currency')
    forms = [unit]
    if unit in ('%', '个百分点'):
        # Only these have other spellings that cannot be an ordinary word: "比例" or "日" right after a number may start the next phrase.
        forms += [spelling for spelling, canonical in SPELLINGS.items() if canonical == unit and not spelling.isascii()]
    if unit == '%':
        forms.append('％')
    if currency:
        words = [currency] + [word for word, code in CURRENCIES.items() if code == currency and not word.isascii()]
        forms += [word + gap + unit for word in words for gap in ('', ' ')]
        if unit == '元/股':
            forms += [word + '/股' for word in words]
        elif unit.endswith('元'):
            forms += [unit[:-1] + word for word in words if not word.isascii()]
    return sorted(set(forms), key=len, reverse=True)


def column_label(column):
    unit = ' '.join(x for x in (column.get('currency'), column.get('unit')) if x)
    return column.get('label', '') + (f'（{unit}）' if unit else '')


def format_cell(value, column, with_unit=False):
    if value is None:
        return '—'
    if not column.get('unit'):
        return str(value)
    text = f'{Decimal(value):,.{column.get("decimals", 2)}f}'
    return text + (' ' + ' '.join(x for x in (column.get('currency'), column['unit']) if x) if with_unit else '')


def render_chart(table, chart):
    """Returns editable fig/ax; custom layouts use these same converted rows."""
    import matplotlib.pyplot as plt
    xs, ys = chart['x'], chart['y']
    columns, rows = table['columns'], table['rows']
    labels = {(columns[k].get('currency'), columns[k].get('unit')) for k in ys}
    if len(labels) != 1 or next(iter(labels))[1] is None:
        choices = {k: columns[k] for k in ys}
        mixed = [{k: cell_column(table, i, k) for k in ys} for i in range(len(rows))] if any(columns[k].get('per_cell_unit') for k in ys) else []
        raise ValueError(f'图表 {chart.get("title", "")} 的 y={ys} 不是同币种同单位。列定义：{choices}；逐行单位：{mixed}。请把金额、利润率与百分点分别放入单位一致的表，再让 charts[].table/y 引用相应表列')
    fig, ax = plt.subplots(figsize=chart.get('size', [8.4, 4.8]), layout='constrained')
    background = '#fdfcf9' if chart.get('theme') == 'report' else '#ffffff'
    fig.set_facecolor(background); ax.set_facecolor(background)
    colors = ['#315447', '#608976', '#ae7455', '#748079'] if chart.get('theme') == 'report' else ['#35658e', '#438478', '#b57d58', '#6d7f8b']
    x = list(range(len(rows)))
    for i, key in enumerate(ys):
        y = [float(r[key]) if r[key] is not None else float('nan') for r in rows]
        args = {'label': columns[key].get('label', key), 'color': colors[i % len(colors)]}
        forecast = []
        for j, row in enumerate(rows):
            source = table.get('evidence', [{} for _ in rows])[j].get(key, {}).get('source', {})
            forecast.append(source.get('data_kind') in {'analyst_forecast', 'company_guidance', 'assumption', 'model_calculation'}
                            or ('forecast_from' in chart and j >= chart['forecast_from']))
        if chart.get('kind', 'line') == 'bar':
            width = .72 / len(ys)
            bars = ax.bar([n - .36 + width * (i + .5) for n in x], y, width, **args)
            for bar, predicted in zip(bars, forecast):
                if predicted:bar.set_facecolor('none'); bar.set_edgecolor(args['color']); bar.set_linewidth(1.6)
        elif chart.get('kind', 'line') == 'line':
            ax.plot(x, [v if not forecast[j] else float('nan') for j, v in enumerate(y)], marker='o', linewidth=2, **args)
            if any(forecast):
                ax.plot(x, [v if forecast[j] or (j+1<len(rows) and forecast[j+1]) else float('nan') for j, v in enumerate(y)],
                        marker='o', markerfacecolor=background, linestyle='--', linewidth=2, color=args['color'])
        else:
            raise ValueError('自动图支持 line/bar；其他图形用 compile_report 的 rows 编写 Python')
    currency, unit = next(iter(labels))
    ax.set_ylabel(' '.join(x for x in (currency, unit) if x))
    ax.set_xticks(x, [str(r[xs]) for r in rows]); ax.set_title(chart.get('title', ''), loc='left', pad=14)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True); ax.grid(axis='y', alpha=.18)
    if len(ys) > 1: ax.legend(loc='best', frameon=False)
    if any('forecast' in str(e.get('source', {}).get('data_kind', '')) or e.get('source', {}).get('data_kind') in {'model_calculation', 'assumption', 'company_guidance'}
           for row in table.get('evidence', []) for e in row.values()) or 'forecast_from' in chart:
        fig.supxlabel('虚线／空心：预测或假设', fontsize=9, color='#637269')
    return fig, ax


def write_csv(path, table):
    """Exact converted values under headers that state unit and currency."""
    columns = table['columns']
    headers = [column_label(col) or key for key, col in columns.items()]
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(headers)
        writer.writerows(['' if row[k] is None else str(row[k]) + ' ' + ' '.join(str(v) for v in (cell_column(table,i,k).get('currency'),cell_column(table,i,k).get('unit')) if v) if columns[k].get('per_cell_unit') else row[k] for k in columns] for i, row in enumerate(table['rows']))
    return headers


def save_table(name, columns, rows, title=None, input_dir='/input', output_dir='/output'):
    """Write <name>.csv from a custom script through the same unit conversion as a report.

    Cells are {fact_id}/{record_id}, {model, path}, or {value, unit, currency}; each column names its
    display unit. Returns the compiled table (converted rows, canonical units) for plotting.
    """
    root = Path(input_dir)
    records = [r for filename in ('facts.json', 'research_records.json') if (root / filename).exists()
               for r in json.loads((root / filename).read_text(encoding='utf-8'))]
    models = json.loads((root / 'models.json').read_text(encoding='utf-8')) if (root / 'models.json').exists() else {}
    table = {'columns': columns, 'rows': rows, **({'title': title} if title else {})}
    compiled = compile_report({'tables': {name: table}}, records, models)['tables'][name]
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    write_csv(output / (name + '.csv'), compiled)
    save_numeric_tables({name: compiled}, output)
    return compiled


def save_numeric_tables(tables, output):
    path = Path(output) / 'numeric_tables.json'
    saved = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'tables': {}}
    saved['tables'].update(tables)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')


def render_report(compiled, output_dir):
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    save_numeric_tables(compiled['tables'], output)
    markdown = ['# ' + compiled.get('title', '分析报告'), compiled.get('body', '')]
    for name, table in compiled['tables'].items():
        columns, rows = table['columns'], table['rows']
        headers = write_csv(output / (name + '.csv'), table)
        markdown += ['## ' + table.get('title', name), render_table(table)]
    charts = []
    for i, chart in enumerate(compiled.get('charts', []), 1):
        fig, _ = render_chart(compiled['tables'][chart['table']], {**chart, 'theme': chart.get('theme', compiled.get('theme', 'analysis'))})
        name = f'chart_{i}.png'; fig.savefig(output / name, dpi=180, bbox_inches='tight', pad_inches=.2)
        import matplotlib.pyplot as plt
        plt.close(fig); charts.append(name); markdown.append(f'![{chart.get("title", "图表")}]({name})')
    (output / 'report.md').write_text('\n\n'.join(markdown), encoding='utf-8')
    (output / 'chart_data.json').write_text(json.dumps(compiled, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'report': 'report.md', 'tables': [name + '.csv' for name in compiled['tables']], 'charts': charts,
            'numbers': {name: {'columns': t['columns'], 'rows': t['rows']} for name, t in compiled['tables'].items()}}


def deliver(report=None, input_dir='/input', output_dir='/output'):
    root, output = Path(input_dir), Path(output_dir)
    if report is None:
        # A custom calculation may write its derived quantities into this file.
        candidate = output / 'analysis_report.json'
        if not candidate.exists(): candidate = root / 'analysis_report.json'
        if not candidate.exists(): return
        report = json.loads(candidate.read_text(encoding='utf-8'))
    records = []
    for filename in ('facts.json', 'research_records.json'):
        records += json.loads((root / filename).read_text(encoding='utf-8'))
    models = json.loads((root / 'models.json').read_text(encoding='utf-8')) if (root / 'models.json').exists() else {}
    compiled = compile_report(report, records, models)
    result = render_report(compiled, output)
    # Re-render from exact resolved data; no DB, secrets or model call required.
    with zipfile.ZipFile(output / 'presentation_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(output / 'chart_data.json', 'chart_data.json')
        for filename in ('analysis_report.py', 'model_units.py', 'plot_runtime.py'):
            z.write(root / filename, filename)
        z.writestr('render.py', "import json\nfrom pathlib import Path\nfrom plot_runtime import setup\nfrom analysis_report import render_report\nsetup()\nrender_report(json.loads(Path('chart_data.json').read_text(encoding='utf-8')), 'output')\n")
        z.writestr('README.txt', 'Python 3 + matplotlib. Run: python render.py\nchart_data.json contains exact display values and original evidence. Calculations are in executed_script.py or model_bundle.zip when supplied.\n')
    print(json.dumps({'delivery': result}, ensure_ascii=False))
    return result

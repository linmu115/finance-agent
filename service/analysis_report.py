"""One numeric presentation shared by CSV, Markdown and charts in every profile.

Runs inside the analysis sandbox. It does not evaluate expressions or fetch data.
Custom Python can supply derived quantities; record/model references use the
mounted snapshots. Values stay Decimal until Matplotlib needs a float.
"""
from copy import deepcopy
import csv
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re
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


def unit_info(unit):
    if unit not in UNITS:
        raise ValueError(f'未知单位 {unit!r}；可用单位：{", ".join(UNITS)}')
    dimension, scale = UNITS[unit]
    return dimension, Decimal(scale)


def convert(value, source_unit, display_unit):
    source_dimension, source_scale = unit_info(source_unit)
    dimension, scale = unit_info(display_unit)
    if dimension != source_dimension:
        raise ValueError(f'不能把 {source_unit} 换算为 {display_unit}；百分比与百分点、金额与每股金额分别处理')
    if value is None:
        return None
    number = Decimal(str(value))
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
    if source_unit and info and source_unit != info['unit']:
        raise ValueError(f'{path} 已有单位 {info["unit"]}，不能改写为 {source_unit}')
    if info is None:
        if source_unit is None:
            raise ValueError(f'{path} 尚无单位元数据；提供明确 source_unit 或用 Python 定义派生量')
        info = {'unit': source_unit, 'scale': '1'}
    value = at_path(model['result'], path)
    if value is not None:
        with localcontext() as ctx:
            ctx.prec = 50
            value = str(Decimal(str(value)) * Decimal(info.get('scale', '1')))
    return {'value': value, 'unit': info['unit'], 'currency': model['spec']['currency'] if unit_info(info['unit'])[0] in {'money', 'per_share'} else None,
            'source': {'artifact_id': model['id'], 'revision_id': model['revision_id'], 'path': path,
                       'data_kind': 'model_calculation', 'amount_scale': model['spec']['amount_scale']}}


def compile_report(report, records=(), models=None):
    """Resolve every numeric cell once; all consumers use this immutable result."""
    index = {r.get('fact_id') or r.get('record_id'): r for r in records}
    compiled = deepcopy(report)
    for name, table in compiled['tables'].items():
        if not re.fullmatch(r'[\w-]+', name):
            raise ValueError('表名用于文件名，请使用中文、字母、数字、下划线或连字符')
        columns = table['columns']
        values, evidence = [], []
        for row_index, row in enumerate(table['rows']):
            displayed, sources = {}, {}
            for key, col in columns.items():
                cell = row.get(key)
                if 'unit' not in col:
                    if isinstance(cell, dict):
                        raise ValueError(f'{name}.{row_index}.{key} 是数值引用，请为该列指定 unit')
                    displayed[key] = cell
                    continue
                ref = cell if isinstance(cell, dict) else {'value': cell, 'unit': col.get('source_unit', col['unit']), 'currency': col.get('currency')}
                if 'fact_id' in ref or 'record_id' in ref:
                    rid = ref.get('fact_id') or ref.get('record_id')
                    if rid not in index:
                        raise ValueError(f'当前导出数据没有记录 {rid}；将所属文档加入 document_ids')
                    quantity = record_quantity(index[rid])
                elif 'model' in ref:
                    quantity = model_quantity((models or {})[ref['model']], ref['path'], ref.get('source_unit'))
                else:
                    quantity = ref
                dimension, _ = unit_info(col['unit'])
                if dimension in {'money', 'per_share'}:
                    currency = quantity.get('currency') or col.get('currency')
                    if not currency and quantity['value'] is not None:
                        raise ValueError(f'{name}.{key} 需要 currency；币种不能从金额大小推断')
                    if col.get('currency') and col['currency'] != currency:
                        raise ValueError(f'{name}.{key} 包含不同币种，不能共用一列；请分列或显式换汇计算')
                    if currency:col['currency'] = currency
                displayed[key] = convert(quantity['value'], quantity['unit'], col['unit'])
                sources[key] = quantity
            values.append(displayed)
            evidence.append(sources)
        table['rows'], table['evidence'] = values, evidence
    def replacement(match):
        token = match.group(1).split('.')
        if len(token) != 3:
            raise ValueError('数字占位符使用 {{表名.行号.列名}}，行号从 0 开始')
        name, row, key = token
        table = compiled['tables'][name]
        return format_cell(table['rows'][int(row)][key], table['columns'][key], with_unit=True)
    compiled['body'] = re.sub(r'\{\{\s*([^{}]+?)\s*\}\}', replacement, compiled.get('body', ''))
    return compiled


def column_label(column):
    unit = ' '.join(x for x in (column.get('currency'), column.get('unit')) if x)
    return column.get('label', '') + (f'（{unit}）' if unit else '')


def format_cell(value, column, with_unit=False):
    if value is None:
        return '—'
    if 'unit' not in column:
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
        raise ValueError('同一坐标轴上的数列须为同币种、同单位；不同量请分图')
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


def render_report(compiled, output_dir):
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    markdown = ['# ' + compiled.get('title', '分析报告'), compiled.get('body', '')]
    for name, table in compiled['tables'].items():
        columns, rows = table['columns'], table['rows']
        headers = [column_label(col) or key for key, col in columns.items()]
        with (output / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f); writer.writerow(headers)
            writer.writerows(['' if row[k] is None else row[k] for k in columns] for row in rows)
        escape = lambda s: str(s).replace('|', '\\|').replace('\n', ' ')
        markdown += ['## ' + table.get('title', name), '| ' + ' | '.join(map(escape, headers)) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
        markdown += ['| ' + ' | '.join(escape(format_cell(row[k], col)) for k, col in columns.items()) + ' |' for row in rows]
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

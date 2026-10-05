"""Wire compression only: expand into the existing complete mapping contract.

Legacy row columns_json always means complete replacement. Only the new,
explicit column_overrides_json field inherits; it never hides a legacy gap.
No values, periods or units are inferred by this codec.
"""
import copy
import json
import re

COLUMN_FIELDS={'column','period','start','end','unit','currency','version','dimensions','metric','label','scope','statement','numeric_span'}

def _read(value,kind,empty):
    if value in (None,''):return copy.deepcopy(empty)
    try:result=json.loads(value) if isinstance(value,str) else copy.deepcopy(value)
    except (TypeError,ValueError):raise ValueError('invalid_compact_mapping') from None
    if not isinstance(result,kind):raise ValueError('invalid_compact_mapping')
    return result

def _fields(value,*,column=False):
    if not isinstance(value,dict) or set(value)-COLUMN_FIELDS:raise ValueError('invalid_column_fields')
    if column and (type(value.get('column')) is not int or value['column']<1):raise ValueError('invalid_column_id')
    if not column and 'column' in value:raise ValueError('invalid_column_defaults')
    return value

def expand_mappings(extractions):
    result=copy.deepcopy(extractions);schemas={}
    for ex in result:
        marker=re.fullmatch(r'\[\[T(\d+)\]\]',ex.get('text',''))
        if ex.get('class')!='table_schema' or not marker:continue
        attrs=ex['attributes']
        if attrs.get('column_defaults_json'):
            defaults=_fields(_read(attrs.pop('column_defaults_json'),dict,{}))
            if 'numeric_span' in defaults:raise ValueError('row_span_in_column_defaults')
            columns=_read(attrs.get('columns_json'),list,[]);seen=set();expanded=[]
            for column in columns:
                _fields(column,column=True)
                if column['column'] in seen:raise ValueError('duplicate_column_id')
                seen.add(column['column']);expanded.append({**defaults,**column})
            attrs['columns_json']=json.dumps(expanded,ensure_ascii=False,separators=(',',':'))
        schemas[int(marker[1])]=attrs
    for ex in result:
        marker=re.fullmatch(r'\[\[T(\d+):R\d+\]\]',ex.get('text',''))
        if ex.get('class')!='financial_row' or not marker:continue
        attrs=ex['attributes'];override=attrs.pop('column_overrides_json',None)
        if not override:continue
        if _read(attrs.get('columns_json'),list,[]):raise ValueError('ambiguous_row_columns')
        patch=_read(override,dict,{})
        if set(patch)-{'all','columns'}:raise ValueError('invalid_column_override')
        common=_fields(patch.get('all',{}))
        if 'numeric_span' in common:raise ValueError('span_requires_exact_column')
        columns=_read(schemas.get(int(marker[1]),{}).get('columns_json'),list,[])
        by_id={c['column']:{**c,**common} for c in columns if isinstance(c,dict) and type(c.get('column')) is int}
        patches=patch.get('columns',[])
        if not isinstance(patches,list):raise ValueError('invalid_column_override')
        seen=set()
        for column in patches:
            _fields(column,column=True);key=column['column']
            if key in seen or key not in by_id:raise ValueError('unknown_or_duplicate_override_column')
            seen.add(key);by_id[key].update(column)
        if not by_id:raise ValueError('missing_inherited_columns')
        attrs['columns_json']=json.dumps(list(by_id.values()),ensure_ascii=False,separators=(',',':'))
    return result

COMPACT_RULES='''
采用显式继承减少重复输出：table_schema 可加 column_defaults_json（JSON对象字符串），集中定义各列共有的 unit/currency/version/dimensions 等；columns_json 仍必须列出每个数据列的 column、不同的 period/start/end 等。程序合并默认值与逐列差异，禁止省略数据列。
financial_row 无差异时不写列定义；有差异时使用 column_overrides_json（JSON对象字符串）：{"all":{所有列共同修改字段},"columns":[{"column":列号,具体差异字段}]}。未修改列会明确继承表级完整定义；百分率/每股行通常只需 unit，混合金额与同比列须按列给指标和单位。不要重复其他不变字段。
列级覆盖必须引用表级已有列。numeric_span 必须放对应列，不能放默认值或all。若使用旧 columns_json，则它仍是完整替换，不能只写差异，也不能与 column_overrides_json 同时使用。
期初余额、本期增加/减少、期末余额混在同表时，以原文覆盖期间为准，分别处理期初时点、当期期间和期末时点（年度表通常对应上年末、本年度、当年末）；不得全表共用一个时点。可用行 column_overrides_json 的 all 一次覆盖所有列的 period/start/end；各年份列不同的，按列分别覆盖。
主体名称可以是维度：子公司投资账面价值、注册资本、持股比例、股本数量及其变动、经营产销量都是财务或经营数据，不能因为第一列是公司或股东类别就当作非财务名单跳过。只有没有定量财务或经营信息的名单/索引等才用nonfinancial。
'''

def compact_prompt(legacy):
    return legacy.replace('columns_json（仅行内日期/单位/重述口径不同于表级时覆盖完整列定义，否则空字符串）。',
                          'column_overrides_json（仅有差异时提供显式列覆盖，结构见后文）。')+COMPACT_RULES

def compact_examples(examples):
    result=copy.deepcopy(examples)
    for example in result:
        schemas={}
        for ex in example.extractions:
            attrs=ex.attributes
            if ex.extraction_class=='table_schema':
                columns=_read(attrs.get('columns_json'),list,[])
                defaults={k:v for k,v in columns[0].items() if k in {'unit','currency','version','dimensions'} and all(c.get(k)==v for c in columns)} if columns else {}
                attrs['column_defaults_json']=json.dumps(defaults,ensure_ascii=False)
                attrs['columns_json']=json.dumps([{k:v for k,v in c.items() if k not in defaults} for c in columns],ensure_ascii=False)
                schemas[ex.extraction_text]=columns
            elif ex.extraction_class=='financial_row' and attrs.get('columns_json'):
                key=ex.extraction_text.split(':')[0]+']]';base={c['column']:c for c in schemas.get(key,[])}
                patches=[{k:v for k,v in c.items() if k=='column' or base.get(c['column'],{}).get(k)!=v} for c in _read(attrs.pop('columns_json'),list,[])]
                attrs['column_overrides_json']=json.dumps({'columns':patches},ensure_ascii=False)
    return result

"""Small helper copied into /input. Runs only in the existing analysis sandbox.

The host validates every coordinate and re-reads every numeric value. No database
or credentials are available here. Models may also produce the same JSON directly.
"""
import json
from functools import wraps
import re
from pathlib import Path


class MappingError(ValueError):
    """A table's declared mapping cannot match its source coordinates."""


def table_mapping(method):
    @wraps(method)
    def apply(self, index, *args, **kwargs):
        try:
            return method(self, index, *args, **kwargs)
        except MappingError as error:
            # Preserve a concrete per-table failure; later tables in the same
            # script still run. Unexpected Python errors remain fatal.
            if not self.results.get(index,{}).get('mapping_error'):
                self.results[index]={'index':index,'mapping_error':str(error),'schema':{},'rows':[]}
            return {}
    return apply


class Cleaner:
    def __init__(self):
        self.source = json.loads(Path('/input/cleaning_source.json').read_text())
        self.tables = {t['index']: t for t in self.source['tables']}
        self.results = {}

    def table(self, index):
        return self.tables[index]

    @table_mapping
    def apply_draft(self, index, *, row_overrides=None, columns=None, **changes):
        """Keep standard/learned rows and supply only the missing meanings."""
        draft=self.source.get('mapping_drafts',{}).get(str(index))
        if not draft:raise MappingError(f'Table {index} has no mapping draft; use map_table or map_series.')
        schema=dict(draft['schema'])
        defaults=json.loads(schema.pop('columns_json'))
        skip={v['row']:v['reason'] for v in json.loads(schema.pop('skipped_rows_json','[]'))}
        ignored={v['column']:v['reason'] for v in json.loads(schema.pop('skipped_columns_json','[]'))}
        rows={v['row']:dict(v['attributes']) for v in draft['rows']}
        for row,attrs in (row_overrides or {}).items():rows[int(row)]={**rows.get(int(row),{}),**attrs}
        schema.update(changes)
        self.map_table(index,columns if columns is not None else defaults,
                       row_overrides=rows,skip_rows=skip,skip_columns=ignored,**schema)

    def numeric_spans(self, index, row, column):
        """One-based source coordinates; choose financial meanings in the script.
        Each returned span contains original offsets/text, not rewritten values.
        """
        raw=str(self.table(index)['rows'][row-1][column-1])
        number=r'[+\-−]?\d[\d,，]*(?:\.\d+)?'
        return [{'text':m.group(),'start':m.start(),'end':m.end(),'polarity':'as_written'}
                for m in re.finditer(rf'(?:\({number}\)|（{number}）|{number})[%％]?',raw)]

    def series_slots(self, index, row, column):
        """Standalone source dashes occupy a logical row, without becoming zero."""
        raw=str(self.table(index)['rows'][row-1][column-1])
        slots=self.numeric_spans(index,row,column)
        slots.extend({'text':m.group().strip(),'start':m.start(),'end':m.end(),'missing':True}
                     for m in re.finditer(r'(?m)^[ \t]*[–—-][ \t]*$',raw))
        return sorted(slots,key=lambda slot:slot['start'])

    @table_mapping
    def packed_row(self, index, row, columns, metrics):
        """Map a packed logical row using semantic labels chosen by the model.
        Columns retain dates/units; this helper performs only coordinate pairing.
        """
        definitions=[]
        for column in columns:
            spans=self.series_slots(index,row,column['column'])
            if not spans:continue  # Empty original cells are not zero.
            if len(spans)!=len(metrics):
                raise MappingError(f'Table {index} row {row} column {column["column"]}: {len(spans)} source numbers but {len(metrics)} meanings; read source rows and pair explicitly.')
            definitions.extend({**column,**metric,'numeric_span':span} for metric,span in zip(metrics,spans) if not span.get('missing'))
        return {'metric':metrics[0]['metric'],'label':metrics[0].get('label',metrics[0]['metric']),'row_subject':False,'columns_json':definitions}

    @table_mapping
    def map_series(self, index, columns, metrics, *, data_rows, **schema):
        """Pair each declared data column's source numbers with semantic rows.
        PDF columns may pack all numbers in one cell or spread them across blank
        physical rows. The model supplies the logical meanings once, not digits.
        """
        selected=list(data_rows);overrides={}
        for column in columns:
            locations=[(row,span) for row in selected for span in self.series_slots(index,row,column['column'])]
            if len(locations)!=len(metrics):
                raise MappingError(f'Table {index} column {column["column"]}: {len(locations)} source numbers but {len(metrics)} logical meanings; adjust data_rows or map the ambiguous cells explicitly.')
            for metric,(row,span) in zip(metrics,locations):
                if span.get('missing'):continue
                attrs=overrides.setdefault(row,{'metric':metric['metric'],'label':metric.get('label',metric['metric']),'row_subject':False,'columns_json':[]})
                attrs['columns_json'].append({**column,**metric,'numeric_span':span})
        skip=dict(schema.pop('skip_rows',{}))
        for row in range(1,len(self.table(index)['rows'])+1):
            if row not in selected:
                if selected and row>min(selected) and row not in skip and any(self.numeric_spans(index,row,c['column']) for c in columns):
                    raise MappingError(f'Table {index} row {row} contains numbers after data_rows starts. Include all data rows/period columns together; use explicit skip_rows only for a non-data row.')
                skip.setdefault(row,'Header outside the declared data_rows')
        self.map_table(index,[],row_overrides=overrides,skip_rows=skip,**schema)

    @table_mapping
    def map_table(self, index, columns, *, statement, scope, currency, unit,
                  metrics=None, skip_rows=None, row_overrides=None, label_column=1,
                  company=None, dimensions=None, data_kind=None, entity_kind='company',
                  scenario=None, attribution=None, skip_columns=None):
        """One-based columns/rows. metrics maps exact row labels to metric IDs or
        {metric,label,dimensions_json,...}. row_overrides maps one-based rows to
        attributes; columns_json may override a table's complete column mapping.
        Numeric header rows must be explicitly listed in skip_rows with a reason.
        English labels can use a deterministic ID when metrics is None; Chinese
        labels require a mapping. Units/dates/scope are always explicit.
        Set row_subject=False in a packed row's attributes when its numeric spans
        represent separate logical rows rather than measures of one row subject.
        """
        from decimal import Decimal, InvalidOperation
        if index in self.results:
            raise MappingError(f'Table {index} already mapped in this script. Supply all periods/columns and row_overrides in one map_table/map_series call; a second call would discard the first mapping.')
        if not company and self.source.get('company_from_filename') and (not row_overrides or not all(a.get('company') for a in row_overrides.values())):
            raise MappingError('Specify company from the report title; the source company hint is only a filename.')
        def numeric(value):
            text=str(value).strip().replace(',', '').replace('，','').replace('−','-')
            if text in {'','-','–','—','N/A'}:return False
            text=text.strip('()（）%％')
            try:Decimal(text);return True
            except InvalidOperation:return False
        table=self.tables[index];rows=[];skipped=[]
        for number,row in enumerate(table['rows'],1):
            reason=(skip_rows or {}).get(number) or (skip_rows or {}).get(str(number))
            attributes=(row_overrides or {}).get(number) or (row_overrides or {}).get(str(number)) or {}
            if reason and attributes:
                raise MappingError(f'Row {index}:{number} has both skip_rows and row_overrides. Remove the skip for financial data; a mapped row must not be silently discarded.')
            if reason:skipped.append({'row':number,'reason':reason});continue
            if not attributes and not any(numeric(c) for c in row):continue
            label=str(row[label_column-1]).strip() if len(row)>=label_column else ''
            mapped=(metrics or {}).get(label)
            if isinstance(mapped,str):mapped={'metric':mapped}
            if mapped is None:
                name=re.sub('[^a-z0-9]+','_',label.lower()).strip('_')
                if not name or not name[0].isalpha():
                    if not attributes.get('metric') and not attributes.get('unresolved_cells'):raise MappingError(f'Row {index}:{number} needs an explicit metric: {label}')
                mapped={'metric':name}
            attrs={'label':label,'dimensions_json':json.dumps(dimensions or {},ensure_ascii=False),**mapped,**attributes}
            if 'unresolved_cells' in attrs:attrs['unresolved_cells_json']=json.dumps(attrs.pop('unresolved_cells'),ensure_ascii=False)
            effective=attrs.get('columns_json') or columns
            if isinstance(effective,str):effective=json.loads(effective)
            typed=[]
            for definition in effective:
                definition=dict(definition)
                span=definition.get('numeric_span')
                if span and 'start' not in span and 'end' not in span:
                    text=span.get('text','');raw=str(row[definition['column']-1]);start=raw.find(text)
                    if not text or start<0 or raw.find(text,start+len(text))>=0:
                        raise MappingError(f'Table {index} row {number} column {definition["column"]}: numeric_span.text must occur exactly once, otherwise supply explicit offsets.')
                    definition['numeric_span']={**span,'start':start,'end':start+len(text),'polarity':span.get('polarity','as_written')}
                kind=definition.get('semantic_type')
                if kind in {'ratio','growth_rate','percentage_points','change_amount'}:
                    suffix={'ratio':'_share','growth_rate':'_growth_rate','percentage_points':'_change_pp','change_amount':'_change_amount'}[kind]
                    definition.setdefault('metric',attrs.get('metric','')+suffix)
                    if kind!='change_amount':
                        definition.setdefault('unit','个百分点' if kind=='percentage_points' else '%')
                        definition.setdefault('currency','percentage_points' if kind=='percentage_points' else 'percent')
                    definition.setdefault('label',label+{'ratio':' 构成比例','growth_rate':' 变动比例','percentage_points':' 变动百分点','change_amount':' 变动额'}[kind])
                typed.append(definition)
            if any(c.get('semantic_type') or c.get('numeric_span') for c in effective):attrs['columns_json']=typed
            if isinstance(attrs.get('columns_json'),list):attrs['columns_json']=json.dumps(attrs['columns_json'],ensure_ascii=False)
            if isinstance(attrs.get('dimensions_json'),dict):attrs['dimensions_json']=json.dumps(attrs['dimensions_json'],ensure_ascii=False)
            rows.append({'row':number,'attributes':attrs})
        self.results[index]={'index':index,'schema':{'company':company or self.source['company'],'statement':statement,
            'scope':scope,'currency':currency,'unit':unit,'columns_json':json.dumps(columns,ensure_ascii=False),
            'skipped_rows_json':json.dumps(skipped,ensure_ascii=False),
            'label_column':label_column,'skipped_columns_json':json.dumps([{'column':int(c),'reason':reason} for c,reason in (skip_columns or {}).items()],ensure_ascii=False),
            **({'data_kind':data_kind} if data_kind else {}),'entity_kind':entity_kind,
            **({'scenario':scenario} if scenario else {}),**({'attribution':attribution} if attribution else {})},'rows':rows}

    def exclude_table(self,index,reason):
        if not reason.strip():raise MappingError('exclusion requires a reason')
        self.results[index]={'index':index,'schema':{'statement':'nonfinancial'},'rows':[], 'exclusion_reason':reason}

    def save(self):
        Path('/output/cleaning_result.json').write_text(json.dumps({'tables':list(self.results.values())},ensure_ascii=False),encoding='utf-8')

"""Small helper copied into /input. Runs only in the existing analysis sandbox.

The host validates every coordinate and re-reads every numeric value. No database
or credentials are available here. Models may also produce the same JSON directly.
"""
import json
import re
from pathlib import Path


class Cleaner:
    def __init__(self):
        self.source = json.loads(Path('/input/cleaning_source.json').read_text())
        self.tables = {t['index']: t for t in self.source['tables']}
        self.results = {}

    def table(self, index):
        return self.tables[index]

    def map_table(self, index, columns, *, statement, scope, currency, unit,
                  metrics=None, skip_rows=None, row_overrides=None, label_column=1,
                  company=None, dimensions=None, data_kind=None, entity_kind='company',
                  scenario=None, attribution=None):
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
        if not company and self.source.get('company_from_filename') and (not row_overrides or not all(a.get('company') for a in row_overrides.values())):
            raise ValueError('Specify company from the report title; the source company hint is only a filename.')
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
                raise ValueError(f'Row {index}:{number} has both skip_rows and row_overrides. Remove the skip for financial data; a mapped row must not be silently discarded.')
            if reason:skipped.append({'row':number,'reason':reason});continue
            if not attributes and not any(numeric(c) for c in row):continue
            label=str(row[label_column-1]).strip() if len(row)>=label_column else ''
            mapped=(metrics or {}).get(label)
            if isinstance(mapped,str):mapped={'metric':mapped}
            if mapped is None:
                name=re.sub('[^a-z0-9]+','_',label.lower()).strip('_')
                if not name or not name[0].isalpha():
                    if not attributes.get('metric'):raise ValueError(f'Row {index}:{number} needs an explicit metric: {label}')
                mapped={'metric':name}
            attrs={'label':label,'dimensions_json':json.dumps(dimensions or {},ensure_ascii=False),**mapped,**attributes}
            if isinstance(attrs.get('columns_json'),list):attrs['columns_json']=json.dumps(attrs['columns_json'],ensure_ascii=False)
            if isinstance(attrs.get('dimensions_json'),dict):attrs['dimensions_json']=json.dumps(attrs['dimensions_json'],ensure_ascii=False)
            rows.append({'row':number,'attributes':attrs})
        self.results[index]={'index':index,'schema':{'company':company or self.source['company'],'statement':statement,
            'scope':scope,'currency':currency,'unit':unit,'columns_json':json.dumps(columns,ensure_ascii=False),
            'skipped_rows_json':json.dumps(skipped,ensure_ascii=False),
            **({'data_kind':data_kind} if data_kind else {}),'entity_kind':entity_kind,
            **({'scenario':scenario} if scenario else {}),**({'attribution':attribution} if attribution else {})},'rows':rows}

    def exclude_table(self,index,reason):
        if not reason.strip():raise ValueError('exclusion requires a reason')
        self.results[index]={'index':index,'schema':{'statement':'nonfinancial'},'rows':[], 'exclusion_reason':reason}

    def save(self):
        Path('/output/cleaning_result.json').write_text(json.dumps({'tables':list(self.results.values())},ensure_ascii=False),encoding='utf-8')

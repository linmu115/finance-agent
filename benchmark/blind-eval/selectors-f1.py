"""Bind frozen gold keys to submitted CSV/JSON cells. No guessed numeric scanner."""
import argparse,csv,hashlib,json
from decimal import Decimal
from pathlib import Path
from blind import read,dump,output
UNITS={'CNY':('CNY',1),'CNY_million':('CNY',1000000),'CNY_100million':('CNY',100000000),'HKD':('HKD',1),'CNY/share':('CNY/share',1),'HKD/share':('HKD/share',1),'ratio':('ratio',1),'%':('ratio',Decimal('.01')),'pp':('pp',1)}
def at(obj,path):
    for key in path:obj=obj[key]
    return obj
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def grade(catalog_path,bindings_path,folder):
    catalog=read(catalog_path);binding=read(bindings_path);folder=Path(folder).resolve()
    if binding['catalog_sha256']!=sha(catalog_path):raise ValueError('Frozen selector catalog mismatch')
    specs={c['key']:c for c in catalog['checks']};results=[];observed=set();files={}
    for b in binding['bindings']:
        if 'expected' in b:raise ValueError('Binding cannot override gold')
        spec=specs[b['key']];p=(folder/b['file']).resolve()
        if not p.is_relative_to(folder):raise ValueError('Binding outside submitted folder')
        if not p.exists():results.append({'key':b['key'],'status':'missing_file','file':b['file']});continue
        if sha(p)!=b['sha256']:raise ValueError('Submitted file changed after binding')
        files[b['file']]=b['sha256'];observed.add(b['key']);row=None
        if b['format']=='csv':
            with p.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            found=[r for r in rows if all(r.get(k)==v for k,v in b['row'].items())]
            if len(found)!=1:raise ValueError('CSV selector must identify exactly one row')
            row=found[0];v=row[b['column']]
            unit_text=row[b['unit_column']] if b.get('unit_column') else b['unit_literal']
        elif b['format']=='json':
            obj=read(p);v=at(obj,b['path']);unit_text=at(obj,b['unit_path']) if b.get('unit_path') else b['unit_literal']
        else:raise ValueError('Use CSV/JSON cells; prose and figures require independent review')
        # Literal units need an exact quoted annotation in the submitted artifact.
        if 'unit_literal' in b and b['unit_literal'] not in p.read_text('utf-8-sig'):raise ValueError('Unit annotation absent from delivered file')
        unit=b['unit_map'].get(unit_text)
        result={'key':b['key'],'file':b['file'],'selector':b,'actual_raw':v,'unit_text':unit_text,'role':spec['role'],'source_pages_gold':spec['source_pages'],'semantic_status':'independent_review_required'}
        if unit not in UNITS:result['status']='unknown_unit'
        elif v is None or v=='':result['status']='missing_value'
        else:
            eu=UNITS[spec['expected']['unit']];au=UNITS[unit]
            if eu[0]!=au[0]:result['status']='unit_or_currency_mismatch'
            else:
                actual=Decimal(str(v).replace(',',''))*Decimal(au[1])/Decimal(eu[1]);expected=Decimal(spec['expected']['value']);tol=Decimal(spec['expected']['absolute_tolerance'])
                if not actual.is_finite():raise ValueError('Non-finite numeric claim')
                error=actual-expected;result.update(error_in_reference_unit=str(error),status='exact' if error==0 else 'rounding_consistent' if abs(error)<=tol else 'numeric_mismatch')
        results.append(result)
    tasks=binding['tasks']
    unbound=[{'key':c['key'],'role':c['role'],'status':'unbound_unknown'} for c in catalog['checks'] if c['task'] in tasks and c['key'] not in observed]
    return {'catalog_sha256':sha(catalog_path),'binding_sha256':sha(bindings_path),'files':files,'checks':results,'unbound':unbound,'limitations':'Bindings are evaluator-reviewed locations and unit annotations, not gold edits. Include every still-delivered version; missing selectors are not a numeric pass or automatic material error. Source identity, comparability, direction in prose and explanations use A5 plus independent review.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('catalog');p.add_argument('bindings');p.add_argument('folder');p.add_argument('destination');a=p.parse_args();dump(output(a.destination),grade(a.catalog,a.bindings,a.folder))

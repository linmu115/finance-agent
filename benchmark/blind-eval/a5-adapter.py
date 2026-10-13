"""Offline adapter for the existing mainline A5 CLI; no duplicate scanner."""
import argparse,json,subprocess,sys,os,hashlib
from pathlib import Path
from blind import ROOT,read,dump,output
SOURCE_TOOLS={'query_financial_data','get_financial_record','get_source_page','get_source_table','get_source_segment','search_document_sources','search_evidence','get_data_catalog','query_research_records','calculate_financial_metrics','get_document_overview','get_records','query_records','get_document_data','get_financial_records'}
def build_input(study,label):
    study=Path(study);events=[json.loads(line) for line in (study/(label+'-audit.jsonl')).read_text('utf-8-sig').splitlines() if line.strip()]
    tables={};sources=[];calls=[]
    for e in events:
        if e['type']!='tool_result':continue
        d=e['data'];result=d.get('result',{});data=result.get('data',{})
        if d.get('name') in SOURCE_TOOLS:
            sources.append(result);calls.append({'name':d['name'],'toolCallId':d.get('toolCallId')})
        for name in data.get('scenario_context',{}).get('unqualified_names',[]):tables.pop(name,None)
        found=data.get('numeric_tables') or data.get('report',{}).get('tables') or data.get('result',{}).get('report',{}).get('tables')
        if found:tables.update(found) # full A1 tables from host audit, last exposed revision per name
    attachments=[];unreviewed=[]
    for a in read(study/(label+'-deliverables.json'))['artifacts']:
        if not a.get('localFile'):
            unreviewed.append({'name':a['name'],'reason':'download failed','httpStatus':a.get('httpStatus')});continue
        p=study/(label+'-artifacts')/a['localFile']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=a['sha256']:raise ValueError('Delivered artifact changed '+a['name'])
        if p.suffix.lower() in ('.md','.csv'):
            attachments.append({'name':a['localFile'],'artifact':a['name'],'format':p.suffix[1:].lower(),'text':p.read_text('utf-8-sig')})
        else:unreviewed.append({'name':a['name'],'reason':'A5 CLI text scope excludes this format; independent review required'})
    payload={'answer':(study/(label+'-answer.md')).read_text('utf-8-sig'),'tables':tables,'source_records':sources,'attachments':attachments}
    return payload,{'source_calls':calls,'unreviewed':unreviewed,'scope':'Only this run queried sources, full A1 audit tables and manifest-delivered files; no gold or whole-library evidence.'}
def invoke(payload):
    r=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/scan-delivery-consistency.py')],input=json.dumps(payload,ensure_ascii=False),text=True,encoding='utf-8',capture_output=True,check=True,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'})
    return json.loads(r.stdout)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');g=p.add_mutually_exclusive_group(required=True);g.add_argument('--mainline-result');g.add_argument('--input');g.add_argument('--study');p.add_argument('--label');a=p.parse_args()
    destination=output(a.destination);metadata={}
    if a.mainline_result:result=read(a.mainline_result);method='imported_mainline_result'
    else:
        if a.study:
            if not a.label:p.error('--study requires --label')
            payload,metadata=build_input(a.study,a.label)
        else:payload=read(a.input)
        dump(destination.with_suffix('.input.json'),payload);result=invoke(payload);method='scripts/scan-delivery-consistency.py'
    dump(destination,{'status':'observation_only','scanner_run':method,'result':result,'metadata':metadata,'limitations':'A5 classifications and false positives retained unchanged; absence of a flag is not semantic correctness. No participant feedback or paid retry.'})

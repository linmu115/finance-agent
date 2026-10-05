"""Run the actual period-review pipeline against an isolated sample database.

No evaluator reference is imported or sent to the model. The full PDF supplies
source evidence; only already extracted sample batches populate the test facts.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.semantic import materialize,table_batches
from service.temporal_semantics import review_project
from scripts.benchmark_cleaning import CASES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepared',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=['low','compact-low','targeted-low'],required=True)
    args=parser.parse_args();runtime=json.loads(sys.stdin.readline())
    output=Path(args.output).resolve();root=output/'review-data'/args.mode
    if root==Path('data').resolve() or (root/'finance.sqlite').resolve()==Path('data/finance.sqlite').resolve():
        raise ValueError('isolated_database_required')
    source=json.loads(Path(args.prepared).read_text(encoding='utf-8'));parsed=source['parsed']
    samples=[]
    for index,first,name in CASES:
        file=output/(args.mode+'-'+name+'.json')
        if not file.exists():raise ValueError('sample_not_complete: '+name)
        samples.append(json.loads(file.read_text(encoding='utf-8')))
    svc=FinanceService(root)
    try:
        svc.create_project('p','隔离清洗样本期间复核')
        identity=root/'document-identity.json'
        if identity.exists():doc=json.loads(identity.read_text(encoding='utf-8'))
        else:
            original=Path('data/documents/b43ae45c-d96b-43b6-ab5b-04306c0eb142/1f94f25a3cb74d528f10ddac0be06a0d.pdf')
            upload=root/'uploads'/'伊利股份2024年年度报告.pdf';shutil.copyfile(original,upload)
            doc=svc.register_document('p',str(upload),upload.name)['data']
            identity.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
        did=doc['document_id'];svc._persist_prepared('p',did,parsed)
        for data in samples:
            batch=next(b for b in table_batches(parsed) if b[0]['table']['index']==data['table'] and b[0]['rows'][0]==1)
            for detail in data['details']:
                facts,issues=materialize(detail['extractions'],batch,did,runtime['model'])
                svc._commit_semantic_batch('p',did,'sample-'+args.mode,batch,facts,issues,detail)
        runtime.update(processing_id='review-'+args.mode)
        report=review_project(svc,'p',runtime,lambda message:print(message,flush=True))
        (output/('reviewed-'+args.mode+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with svc.store.connect() as db:records=[dict(r) for r in db.execute('SELECT * FROM facts WHERE project_id=?',('p',))]
        for data in samples:
            facts=[]
            for record in records:
                ref=json.loads(record['source_json'])
                if int(ref['table_id'].rsplit(':t',1)[1])!=data['table']:continue
                facts.append({**record,'source':ref})
            result={**data,'mode':'reviewed-'+args.mode,'facts':facts,'temporal_report_file':'reviewed-'+args.mode+'-report.json'}
            (output/('reviewed-'+args.mode+'-'+data['case']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('status','profiles_reviewed','sources_targeted','facts_updated','model_requests','cache_hits')},ensure_ascii=False),flush=True)
    finally:
        for pool in (svc.processing_pool,svc.pool,svc.analysis_pool,svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)


if __name__=='__main__':main()

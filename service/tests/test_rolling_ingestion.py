import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from service.core import FinanceService
from service.semantic import normalize_document, table_batches, SCHEMA_HASH, VERSION
from service.tests.test_semantic_sources import mappings, sdk_result


class RollingIngestionTests(unittest.TestCase):
    def test_partial_row_override_cannot_silently_drop_other_year_columns(self):
        from service.semantic import materialize
        import json
        batch=[{'table':{'index':0,'page':7,'rows':[['每股收益','1.33','1.64','-18.90']]},'rows':[1]}]
        cols=[{'column':c,'period':str(y)+'-FY','unit':'元/股','currency':'CNY'} for c,y in [(2,2024),(3,2023)]]
        cols.append({'column':4,'period':'2024-FY','unit':'%','currency':'percent'})
        ex=mappings(0,1,'eps',cols)
        ex[1]['attributes']['columns_json']=json.dumps([cols[-1]|{'metric':'eps_yoy'}])
        facts,issues=materialize(ex,batch,'d','fixture')
        self.assertEqual({i['column'] for i in issues if i['reason']=='incomplete_column_override'},{2,3})
        self.assertEqual(len(facts),1)
        ex[1]['attributes']['columns_json']=json.dumps(cols[:-1]+[cols[-1]|{'metric':'eps_yoy'}])
        facts,issues=materialize(ex,batch,'d','fixture');self.assertEqual(issues,[]);self.assertEqual(len(facts),3)

    def test_low_cleaning_high_local_repair_and_failed_slice_does_not_stop_later_work(self):
        parsed={"company":"fixture","report_year":2024,"pages":[{"page":i+1,"text":"2024年合并报表 单位：元"} for i in range(6)],"tables":[{"index":i,"page":i+1,"rows":[["Item","Year end"],["Assets",str(100+i)]]} for i in range(6)]}
        requests=[];committed=[];failed=[]
        def model(**kwargs):
            text=kwargs['text_or_documents'];indices=sorted(set(map(int,re.findall(r'\[\[T(\d+)\]\]',text))))
            effort=kwargs['config'].provider_kwargs['reasoning_effort'];requests.append((indices,effort))
            if 1 in indices:raise RuntimeError('fixture interrupted response')
            extracts=[]
            for i in indices:
                ex=mappings(i,2)
                if i==2 and effort=='low':ex=ex[:1]
                # The bounded repair contract fills the missing row while the
                # host retains its existing table schema and valid neighbours.
                if effort=='high' and '财务映射局部复核器' in kwargs['prompt_description']:ex=ex[1:]
                extracts.extend(ex)
            return sdk_result(extracts)
        runtime={"model":"fixture","base_url":"http://127.0.0.1:1/v1","api_key":"test","processing_id":"p"}
        with patch('langextract.extract',side_effect=model):
            facts,report=normalize_document(parsed,'d',runtime,lambda *_:None,lambda:False,lambda _:None,lambda *_:None,
                on_batch=lambda batch,*_:committed.append(batch[0]['table']['index']),on_failure=lambda batch,*_:failed.append(batch[0]['table']['index']))
        self.assertEqual(sorted(committed),[0,2,3,4,5]);self.assertEqual(failed,[1]);self.assertEqual(report['attempted'],6)
        self.assertEqual(report['completed'],5);self.assertEqual(len(facts),5)
        self.assertEqual([ids for ids,effort in requests if effort=='high'],[[2]])

    def test_checkpoint_comes_from_source_batches_and_survives_service_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);svc=FinanceService(root);svc.create_project('p','test')
            source=root/'uploads'/'report.csv';source.write_text('Item,Value\nAssets,100\n',encoding='utf-8')
            doc=svc.register_document('p',str(source),'report.csv')['data'];did=doc['document_id']
            parsed={"company":"fixture","report_year":2024,"warnings":[],"pages":[{"page":1,"text":"2024 合并 单位：元","printed_page":"1","width":0,"height":0}],"tables":[{"index":0,"page":1,"rows":[["Item","Value"],["Assets","100"]],"cells":{},"bbox":None}],"chunks":[]}
            svc._persist_prepared('p',did,parsed);batch=table_batches(parsed)[0]
            svc._commit_semantic_batch('p',did,'old-run',batch,[],[{"table":0,"reason":"model_request_failed"}],{"version":VERSION,"schema_hash":SCHEMA_HASH,"model":"fixture","extractions":[],"request_error":"temporary"})
            checkpoint=svc.get_processing_checkpoint('p',did)['data']['documents'][0]
            self.assertEqual(checkpoint['counts']['failed'],1);self.assertEqual(checkpoint['remaining'][0]['rows'],[1,2])
            from service.completed_document import completed_document
            self.assertIsNone(completed_document(svc,'p',svc.store.document('p',did),{'model':'fixture'}))
            from service.semantic import materialize
            facts,issues=materialize(mappings(0,2),batch,did,'fixture')
            svc._commit_semantic_batch('p',did,'new-run',batch,facts,issues,{"schema_hash":SCHEMA_HASH,"model":"fixture","extractions":mappings(0,2)})
            for pool in (svc.processing_pool,svc.pool,svc.analysis_pool,svc.embedding_pool):pool.shutdown(wait=True)
            restored=FinanceService(root)
            try:
                checkpoint=restored.get_processing_checkpoint('p',did)['data']['documents'][0]
                self.assertEqual(checkpoint['counts'],{"total":1,"completed":1,"needs_review":0,"failed":0,"pending":0})
                self.assertEqual(restored.query_financial_data('p')['data']['total'],1)
                page=restored.get_data_catalog('p',query='assets',limit=1)['data'];self.assertEqual(page['pagination']['total'],1)
                self.assertEqual(page['metrics'][0]['metric'],'assets')
            finally:
                for pool in (restored.processing_pool,restored.pool,restored.analysis_pool,restored.embedding_pool):pool.shutdown(wait=True)

    def test_catalog_batches_are_bounded_and_resume_saved_batches(self):
        from service.catalog_semantics import _ensure_tables, _bounded_review
        profiles=[{'metric':'metric_'+str(i),'labels':['概念'+str(i)],'statements':['notes'],'units':['CNY'],'dimension_keys':[],'examples':[],'signature':str(i)} for i in range(160)]
        runtime={'model':'fixture','processing_id':'p1','owner_run_id':'r1'}
        with tempfile.TemporaryDirectory() as directory:
            svc=FinanceService(Path(directory));svc.create_project('p','test');_ensure_tables(svc.store)
            calls=[]
            def failed_second(batch,*_):
                calls.append([p['metric'] for p in batch]);self.assertLessEqual(len(batch),72)
                if 'metric_48'==batch[0]['metric']:raise RuntimeError('transient')
                return {'keep':[p['metric'] for p in batch],'aliases':{}},[],1
            try:
                with patch('service.catalog_semantics._call_model',side_effect=failed_second):
                    with self.assertRaisesRegex(ValueError,'pending_retry'):_bounded_review(svc.store,'p',profiles,runtime,lambda _:None,lambda:False)
                self.assertEqual(len(calls),4)
                with patch('service.catalog_semantics._call_model',side_effect=lambda batch,*_:({'keep':[p['metric'] for p in batch],'aliases':{}},[],1)) as model:
                    review,_,count=_bounded_review(svc.store,'p',profiles,runtime,lambda _:None,lambda:False)
                self.assertEqual(model.call_count,1);self.assertEqual(count,1);self.assertEqual(len(review['keep']),160)
            finally:
                for pool in (svc.processing_pool,svc.pool,svc.analysis_pool,svc.embedding_pool):pool.shutdown(wait=True)

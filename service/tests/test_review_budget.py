import json
import tempfile
import unittest
from pathlib import Path
from service.store import Store
from service.review_budget import bounded_temporal_result
from service.temporal_semantics import digest,_ensure_tables


class LimitError(Exception):
    status_code=422
    body={'error':{'code':'model_output_limit','stop_reason':'length','request_id':'audited-request'}}


class ReviewBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name));_ensure_tables(self.store)
        self.owner={'processing_id':'p','owner_run_id':'r'}
        self.items=[{'group_id':str(i)} for i in range(4)]
    def tearDown(self):self.tmp.cleanup()
    def run_parts(self,infer,items=None,phase='profiles',owner=None):
        def validate(part,result):
            if phase=='profiles':self.assertEqual(result['reviewed_count'],len(part))
            else:self.assertEqual({i['source_key'] for i in part},{i['source_key'] for i in result['corrections']+result['unresolved']})
        return bounded_temporal_result(self.store,items or self.items,phase,digest,infer,validate,lambda:False,lambda _:None,owner or self.owner)
    def success(self,part):
        return {'reviewed_count':len(part),'reviewed_group_ids':[p['group_id'] for p in part],'candidates':[],
                'extractions':[],'_review_provenance':self.owner},1

    def test_split_only_failed_batch_and_complete_parent_becomes_zero_call_cache(self):
        seen=[]
        def infer(part):
            seen.append([p['group_id'] for p in part])
            if len(part)==4:raise LimitError()
            return self.success(part)
        result,cached,count=self.run_parts(infer)
        self.assertEqual(seen,[['0','1','2','3'],['0','1'],['2','3']]);self.assertEqual(count,3)
        self.assertEqual(result['reviewed_count'],4);self.assertFalse(cached)
        _,cached,count=self.run_parts(lambda _:self.fail('paid cache replay'))
        self.assertTrue(cached);self.assertEqual(count,0)

    def test_interruption_retains_split_plan_and_successful_child_owner(self):
        def infer(part):
            if len(part)==4:raise LimitError()
            if part[0]['group_id']=='2':raise ConnectionError('temporary transport')
            return self.success(part)
        with self.assertRaises(ConnectionError):self.run_parts(infer)
        owner={'processing_id':'new-p','owner_run_id':'new-r'};seen=[]
        def resume(part):
            seen.append([p['group_id'] for p in part]);value,count=self.success(part);value['_review_provenance']=owner;return value,count
        result,_,count=self.run_parts(resume,owner=owner)
        self.assertEqual(seen,[['2','3']]);self.assertEqual(count,1)
        self.assertEqual(result['split_children'][0]['source_provenance'],self.owner)
        self.assertEqual(result['split_children'][1]['source_provenance'],owner)

    def test_only_audited_limit_allows_subdivision(self):
        for error in (ConnectionError('timeout'),ValueError('invalid mapping')):
            seen=[]
            def infer(part):seen.append(part);raise error
            with self.assertRaises(type(error)):self.run_parts(infer)
            self.assertEqual(len(seen),1)
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from temporal_review_cache').fetchone()[0],0)

    def test_stubborn_limit_has_bounded_attempts_and_escalates_without_inventing_dates(self):
        seen=[]
        def infer(part):seen.append(part);raise LimitError()
        items=[{'group_id':str(i)} for i in range(16)]
        result,_,count=self.run_parts(infer,items)
        self.assertEqual(count,7);self.assertEqual(len(seen),7);self.assertEqual(len(result['deferred_group_ids']),16)
        self.assertEqual(len(result['candidates']),16)

    def test_source_limit_keeps_unresolved_and_success_retains_leaf_audit(self):
        items=[{'source_key':str(i)} for i in range(2)]
        def infer(part):
            if len(part)>1:raise LimitError()
            if part[0]['source_key']=='1':raise LimitError()
            return {'corrections':[{'source_key':'0','period':'2024-12-31'}],'unresolved':[],'extractions':[],
                    '_review_provenance':self.owner},1
        result,_,count=self.run_parts(infer,items,'sources')
        self.assertEqual(count,3);self.assertEqual(len(result['corrections']),1);self.assertEqual(len(result['unresolved']),1)
        self.assertEqual(result['source_audits']['0']['cache_key'],digest([items[0]]))
        self.assertEqual(result['source_audits']['0']['source_provenance'],self.owner)


if __name__=='__main__':unittest.main()

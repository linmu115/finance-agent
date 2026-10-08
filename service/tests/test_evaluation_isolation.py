import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from service.core import FinanceService
from service.evaluation_isolation import isolation_key
from service.model_delivery import select_models, deliver_saved
from service.report_package import prepare, finish
from service.financial_workpapers import publish
from service.research_models import evaluate_model
from service.tests.test_research_models import dcf_spec


@contextmanager
def scoped(key):
    token=isolation_key.set(key)
    try:yield
    finally:isolation_key.reset(token)


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.s=FinanceService(self.root);self.s.create_project('p','Shared prepared inputs')
        self.inputs={};owner=self
        class Runner:
            def availability(self):return {'available':True}
            def run(self,code,inputs,**kw):
                # No generated script executes on the host or in Docker.
                rid=kw['run_id'];owner.inputs[rid]={k:p.read_bytes() for k,p in inputs.items()}
                folder=owner.root/'analysis'/rid/'output';folder.mkdir(parents=True)
                (folder/'result.txt').write_text('chain '+str(isolation_key.get()),encoding='utf8')
                return {'run_id':rid,'status':'succeeded','artifacts':[{'name':'result.txt'}]}
            def artifact_path(self,rid,name,project_id):return owner.root/'analysis'/rid/'output'/name
        self.s.sandbox=Runner()

    def tearDown(self):
        for name in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(self.s,name).shutdown(wait=True)
        self.tmp.cleanup()

    def run_analysis(self,key,**kw):
        with scoped(key):
            rid=self.s.run_analysis('p',**kw)['data']['run_id']
        self.s.analysis_futures[rid].result(timeout=5)
        return rid

    def saved_model(self,key,revision):
        spec=dcf_spec();model={'id':'m_'+revision,'revision_id':revision,'kind':'dcf','spec':spec,'result':evaluate_model('dcf',spec)}
        if key is not None:model['isolation_key']=key
        folder=self.root/'research/p/artifacts';folder.mkdir(parents=True,exist_ok=True)
        (folder/(revision+'.json')).write_text(json.dumps(model),encoding='utf8')
        return {'artifact_id':model['id'],'revision_id':revision}

    def test_analysis_artifacts_status_and_rerun_hide_old_and_other_chains(self):
        old=self.run_analysis(None,code='pass');a=self.run_analysis('a',code='pass');b=self.run_analysis('b',code='pass')
        for key,own,foreign in [('a',a,b),('b',b,a)]:
            with scoped(key):
                self.assertEqual(self.s.get_analysis_status('p',own)['data']['status'],'succeeded')
                result=self.s.get_artifact('p',own,'result.txt')['data']
                self.assertIn(('chain '+key).encode(),(self.root/result['relative_path']).read_bytes())
                for rid in (old,foreign,'absent'):
                    for fn in (lambda:self.s.get_analysis_status('p',rid),lambda:self.s.get_artifact('p',rid,'result.txt'),
                               lambda:self.s.run_analysis('p',source_run_id=rid,edits=[{'before':'pass','after':'print(1)'}])):
                        with self.assertRaisesRegex(ValueError,'^analysis_not_found_in_project$'):fn()
            copied=self.run_analysis(key,source_run_id=own,edits=[{'before':'pass','after':'print(1)'}])
            self.assertEqual(self.inputs[copied]['analysis.py'],b'print(1)')
        # Ownership survives worker saves and a fresh service object.
        reopened=FinanceService(self.root)
        try:
            with scoped('a'):self.assertEqual(reopened._analysis_state('p',a)['isolation_key'],'a')
            for rid in (old,a,b):self.assertEqual(reopened.get_analysis_status('p',rid)['data']['status'],'succeeded')
        finally:
            for name in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(reopened,name).shutdown(wait=True)

    def test_model_refs_and_deliveries_have_the_same_scope(self):
        refs={k:self.saved_model(None if k=='old' else k,k) for k in ('old','a','b')}
        ordinary=deliver_saved(self.root,'p',{'x':refs['a']},{})
        for key in ('a','b'):
            with scoped(key):
                self.assertEqual(select_models(self.root,'p',{'x':refs[key]})['x']['isolation_key'],key)
                d=deliver_saved(self.root,'p',{'x':refs[key]},{});self.assertEqual(d['isolation_key'],key)
                self.assertNotEqual(d['delivery_id'],ordinary['delivery_id'])
                for other in ('old', 'b' if key=='a' else 'a','absent'):
                    ref=refs.get(other,{'artifact_id':'absent','revision_id':'absent'})
                    for fn in (lambda:select_models(self.root,'p',{'x':ref}),lambda:self.s.run_analysis('p',code='pass',model_refs={'x':ref})):
                        with self.assertRaisesRegex(ValueError,'^model_revision_not_found_in_project$'):fn()
            rid=self.run_analysis(key,code='pass',model_refs={'x':refs[key]})
            self.assertEqual(json.loads(self.inputs[rid]['models.json'])['x']['id'],refs[key]['artifact_id'])
        self.assertEqual(len(select_models(self.root,'p',refs)),3)

    def test_nonempty_prepared_research_records_remain_shared(self):
        from service.tests.test_research_ingestion import ResearchIngestionTests
        fixture=ResearchIngestionTests();fixture.setUp()
        try:
            fixture.commit();fixture.finish_text()
            visible_records=[]
            for key in (None,'a','b'):
                with scoped(key):visible_records.append(fixture.s.query_research_records('p')['data']['items'])
            self.assertTrue(visible_records[0])
            self.assertEqual(visible_records[0],visible_records[1]);self.assertEqual(visible_records[1],visible_records[2])
        finally:fixture.tearDown()

    def test_parameter_update_and_intermediate_runs_keep_the_chain_scope(self):
        base=self.run_analysis('a',code='x=1\ny=2\npass')
        updated=self.run_analysis('a',source_run_id=base,params={'x':3,'y':4},params_order=['x','y'])
        with scoped('a'):
            state=self.s._analysis_state('p',updated)
            self.assertEqual(state['status'],'succeeded',state.get('error'))
            self.assertEqual(state['isolation_key'],'a')
            child=state['parameter_steps'][0]['run_id']
            self.assertEqual(self.s._analysis_state('p',child)['isolation_key'],'a')
        with scoped('b'):
            for rid in (base,updated,child):
                with self.assertRaisesRegex(ValueError,'^analysis_not_found_in_project$'):
                    self.s.run_analysis('p',source_run_id=rid,params={'x':4})

    def test_prepared_documents_facts_and_records_are_shared_in_both_profiles(self):
        from service.semantic import materialize, table_batches, VERSION, SCHEMA_HASH
        from service.tests.test_semantic_sources import mappings
        p=self.root/'uploads/source.csv';p.write_text('项目,2024\n收入,100',encoding='utf8')
        did=self.s.register_document('p',str(p),'source.csv')['data']['document_id']
        parsed={'company':'Fixture','report_year':2024,'warnings':[],'pages':[{'page':1,'text':'收入100'}],
                'tables':[{'index':0,'page':1,'rows':[['项目','2024'],['收入','100']],'cells':{}}]}
        self.s._persist_prepared('p',did,parsed)
        batch=table_batches(parsed)[0];ext=mappings(0,2);facts,issues=materialize(ext,batch,did,'fixture')
        self.s._commit_semantic_batch('p',did,'owner',batch,facts,issues,{'version':VERSION,'schema_hash':SCHEMA_HASH,'model':'fixture','extractions':ext})
        # Existing research ingestion tests cover record semantics; this checks identical prepared input snapshots.
        a=self.run_analysis('a',code='pass');b=self.run_analysis('b',code='pass',financial_tools=False)
        for name in ('tables.json','pages.json','facts.json','research_records.json'):
            self.assertEqual(self.inputs[a][name],self.inputs[b][name])
        self.assertTrue(json.loads(self.inputs[a]['facts.json']))
        with scoped('b'):self.assertEqual(self.s.get_source_page('p',did,1)['data']['text'],'收入100')

    def test_workpaper_and_report_package_ownership_cannot_be_supplied_by_content(self):
        report={'title':'fixture','body':'','tables':{'observations':{'columns':{'key':{},'finding':{}},'rows':[{'key':'x','finding':'fixture'}]}}}
        snapshot={'project_id':'p','conversation_id':'c','isolation_key':'forged','title':'Report','turns':[{'id':'m','created_at':'today','body':'Result','sources':[],'tables':{}}]}
        with scoped('a'):
            wp=publish(self.s,'p','statement_analysis',report,[])
            path=self.root/'research/p/deliveries'/wp['delivery']['id']/'delivery.json'
            self.assertEqual(json.loads(path.read_text('utf8'))['isolation_key'],'a')
            pkg=prepare(self.s,'p',snapshot)
            path=self.root/'report_packages/p'/pkg['package_id']/'snapshot.json'
            self.assertEqual(json.loads(path.read_text('utf8'))['isolation_key'],'a')
        with scoped('b'):
            for package_id in (pkg['package_id'],'0'*32):
                with self.assertRaisesRegex(ValueError,'^报告包不存在$'):finish(self.s,'p',package_id,'<p>report</p>')
        with scoped('a'):self.assertTrue(finish(self.s,'p',pkg['package_id'],'<p>report</p>')['relative_path'])
        self.assertTrue(finish(self.s,'p',pkg['package_id'],'<p>report</p>')['relative_path'])


if __name__=='__main__':unittest.main()

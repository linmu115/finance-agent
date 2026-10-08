"""Offline mounts/source isolation. Synthetic inputs; no Docker or model calls."""
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from service.baseline import prepare_document_sources
from service.core import FinanceService
from service.evaluation_isolation import evaluation_profile, analysis_only, isolation_key
from service.financial_workpapers import publish
from service.plot_runtime import LAUNCH, ORIGINAL_PI_LAUNCH


@contextmanager
def scope(profile, key='chain', analysis=True):
    tokens=[(c,c.set(v)) for c,v in ((evaluation_profile,profile),(isolation_key,key),(analysis_only,analysis))]
    try:yield
    finally:
        for c,t in reversed(tokens):c.reset(t)


class OriginalPiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.s=FinanceService(self.root);self.s.create_project('p','Synthetic original Pi fixture')
        self.s.create_project('other','Other project')
        source=self.root/'uploads/source.csv';source.write_text('项目,本期\n收入,137\n',encoding='utf8')
        self.doc=self.s.register_document('p',str(source),source.name)['data']['document_id']
        self.parsed={'company':'合成公司','report_year':2024,'warnings':[],
                     'pages':[{'page':1,'text':'合成原文 收入137','words':[{'text':'137','bbox':[1,2,3,4]}]}],
                     'tables':[{'index':0,'page':1,'rows':[['项目','本期'],['收入','137']],'cells':{}}]}
        self.s._persist_prepared('p',self.doc,self.parsed)
        self.captures={};owner=self
        class Runner:
            def availability(self):return {'available':True}
            def run(self,code,inputs,**kw):
                rid=kw['run_id'];owner.captures[rid]={'launch':code,'inputs':{k:p.read_bytes() for k,p in inputs.items()},'options':kw}
                output=owner.root/'analysis'/rid/'output';output.mkdir(parents=True)
                (output/'result.csv').write_text('key,value\nrevenue,137\n',encoding='utf8')
                (output/'report.md').write_text('自写报告：137元。',encoding='utf8')
                return {'run_id':rid,'project_id':kw['project_id'],'status':'succeeded','stdout':'137',
                        'artifacts':[{'name':'result.csv'},{'name':'report.md'}]}
            def artifact_path(self,rid,name,project_id):return owner.root/'analysis'/rid/'output'/name
        self.s.sandbox=Runner()

    def tearDown(self):
        for name in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(self.s,name).shutdown(wait=True)
        self.tmp.cleanup()

    def run_analysis(self,profile,key='chain',**args):
        with scope(profile,key):
            result=self.s.run_analysis('p',code='print(137)',raw_only=profile=='generic',financial_tools=profile=='financial',**args)
            rid=result['data']['run_id'];self.s.analysis_futures[rid].result(timeout=5)
            state=self.s.get_analysis_status('p',rid)['data']
        return rid,state

    def test_three_arm_mount_capture_and_legacy_result_views(self):
        evidence={}
        with patch.object(self.s,'query_financial_data',return_value={'data':{'items':[{'value':'137','marker':'structured fact'}],'total':1}}) as facts, \
             patch.object(self.s,'query_research_records',return_value={'data':{'items':[{'marker':'structured research'}],'next_offset':None}}) as records:
            for profile in ('original_pi','prepared','financial','generic'):
                before=(facts.call_count,records.call_count);rid,state=self.run_analysis(profile)
                capture=self.captures[rid];inputs=capture['inputs']
                if profile in ('original_pi','generic'):
                    self.assertEqual((facts.call_count,records.call_count),before)
                    self.assertEqual(json.loads(inputs['facts.json']),[])
                    self.assertEqual(json.loads(inputs['research_records.json']),[])
                else:
                    self.assertEqual(json.loads(inputs['facts.json'])[0]['value'],'137')
                    self.assertTrue(json.loads(inputs['research_records.json']))
                self.assertIn(b'137',inputs['pages.json']);self.assertIn(b'137',inputs['tables.json'])
                if profile=='original_pi':
                    self.assertEqual(set(inputs),{'analysis.py','pages.json','tables.json','facts.json','research_records.json','plot_runtime.py'})
                    self.assertEqual(capture['launch'],ORIGINAL_PI_LAUNCH)
                    self.assertNotIn('numeric_tables',state);self.assertNotIn('available_params',state)
                    self.assertNotIn('analysis_report',capture['launch'])
                else:
                    self.assertIn('analysis_report.py',inputs);self.assertIn('delivery_text.py',inputs)
                    self.assertIn('numeric_tables',state)
                    self.assertIn('analysis_report',capture['launch'])
                self.assertEqual('finance_charts.py' in inputs,profile=='financial')
                self.assertEqual('models.json' in inputs,profile=='financial')
                with scope(profile):
                    artifact=self.s.get_artifact('p',rid,'report.md')['data']
                    self.assertTrue((self.root/artifact['relative_path']).is_file())
                    self.assertEqual('content' in artifact,profile!='original_pi')
                    self.assertEqual(state['stdout'],'137')
                evidence[profile]={'launch':capture['launch'],'mounts':{k:{'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for k,v in inputs.items()},
                                   'status_fields':sorted(state),'artifact_fields':sorted(artifact),'timeout_seconds':capture['options']['timeout_seconds']}
        for name in ('pages.json','tables.json','analysis.py','plot_runtime.py'):
            self.assertEqual(len({e['mounts'][name]['sha256'] for e in evidence.values()}),1,name)
        self.assertIn("runpy.run_path('/input/analysis.py'",ORIGINAL_PI_LAUNCH)
        self.assertIn('executed_script.py',ORIGINAL_PI_LAUNCH)
        if target:=os.environ.get('ORIGINAL_PI_EVIDENCE_DIR'):
            out=Path(target);out.mkdir(parents=True,exist_ok=True)
            (out/'sandbox-capture.json').write_text(json.dumps({'mode':'offline fake Runner; actual FinanceService export path','profiles':evidence},ensure_ascii=False,indent=2)+'\n',encoding='utf8')

    def test_original_cannot_use_report_params_models_or_other_delivery_ids(self):
        own,_=self.run_analysis('original_pi');foreign,_=self.run_analysis('prepared')
        with scope('financial'):
            report={'title':'Synthetic','tables':{'observations':{'columns':{'key':{},'finding':{}},'rows':[{'key':'x','finding':'synthetic observation'}]}}}
            wp=publish(self.s,'p','statement_analysis',report,[])['delivery']['id']
        with scope('original_pi'):
            for extra in ({'report':{}},{'model_refs':{}},{'comparisons':{}},{'source_run_id':own},{'edits':[]},{'params':{}},{'params_order':[]}):
                with self.subTest(extra=extra),self.assertRaisesRegex(ValueError,'original_pi_analysis_argument_not_available'):
                    self.s.run_analysis('p',code='pass',**extra)
            for rid in (foreign,wp,'absent'):
                for fn in (lambda:self.s.get_analysis_status('p',rid),lambda:self.s.get_artifact('p',rid,'report.md')):
                    with self.assertRaisesRegex(ValueError,'^analysis_not_found_in_project$'):fn()
            self.assertEqual(self.s.get_analysis_status('p',own)['data']['status'],'succeeded')
        with scope('original_pi','other-chain'):
            with self.assertRaisesRegex(ValueError,'^analysis_not_found_in_project$'):self.s.get_artifact('p',own,'report.md')
        with scope('original_pi'):
            with self.assertRaisesRegex(ValueError,'^analysis_not_found_in_project$'):self.s.get_artifact('other',own,'report.md')
        # Ordinary product access remains project-wide, including original Pi's files.
        for rid in (own,foreign,wp):self.assertGreater(self.s.get_artifact('p',rid,'report.md')['data']['size'],0)

    def test_source_pages_tables_and_search_exclude_structured_excerpts(self):
        with self.s.store.connect(write=True) as db:
            for marker in ('record_id','normalization','fact_id','research_record_id','data_kind'):
                self.s._insert_chunk(db,'p',self.doc,1,'合成原文 收入999 STRUCTURED',
                    {'source_id':marker,'document_id':self.doc,'table_id':'t0','row':1,marker:'structured'})
        views={}
        for profile in ('original_pi','prepared','financial'):
            with scope(profile):
                views[profile]={
                    'page':self.s.get_source_page('p',self.doc,1),
                    'table':self.s.get_source_table('p',self.doc),
                    'search':self.s.search_evidence('p','合成原文',limit=50)}
                text=json.dumps(views[profile],ensure_ascii=False)
                self.assertIn('137',text)
                self.assertEqual('STRUCTURED' in text,profile!='original_pi')
                if profile=='original_pi':
                    for marker in ('record_id','normalization','fact_id','research_record_id','data_kind'):
                        self.assertNotIn('"'+marker+'": "structured"',text)

    def test_analysis_only_preparation_is_read_only_for_all_three_arms(self):
        source=self.root/'uploads/new.csv';source.write_text('x,y\n1,2',encoding='utf8')
        new=self.s.register_document('p',str(source),source.name)['data']['document_id']
        for profile in ('original_pi','prepared','financial'):
            with scope(profile),patch.object(self.s,'_persist_prepared',side_effect=AssertionError('analysis must not write source views')):
                self.assertTrue(prepare_document_sources(self.s,'p',[self.doc])['data']['documents'][0]['reused_sources'])
                with self.assertRaisesRegex(ValueError,'^analysis_sources_not_prepared$'):prepare_document_sources(self.s,'p',[new])
                self.assertEqual(self.s.get_document('p',new)['data']['page_count'],0)
        self.assertFalse(prepare_document_sources(self.s,'p',[new])['data']['documents'][0]['reused_sources'])


if __name__=='__main__':unittest.main()

"""Historical truncation evidence and scheduling tests; fixtures only."""
import copy
import json
import unittest
from unittest.mock import patch

from service.definition_history import expected_messages,historical_output_limit
from service.definition_semantics import build_groups,family_catalog,digest,_ensure_tables,review_project
from service.definition_model import CACHE_HASH
from service.store import dumps


class HistoricalDefinitionLimitTests(unittest.TestCase):
    def setUp(self):
        from service.tests.test_definition_semantics import DefinitionTransactionTests
        DefinitionTransactionTests.setUp(self)
        self.fixture=DefinitionTransactionTests
        _ensure_tables(self.svc.store)
        with self.svc.store.connect() as db:self.groups,self.members,known,*_=build_groups(db,'p',['receivable_amount'])
        self.known=family_catalog(known,self.groups)
        self.key=digest({'config':CACHE_HASH,'model':self.runtime['model'],'groups':self.groups,'known_metrics':self.known})
        self.fingerprints={s['source_key']:s['source_fingerprint'] for values in self.members.values() for s in values}
        self.ids=[g['group_id'] for g in self.groups]
        self.prior={'review_id':'historical-review','model':self.runtime['model'],'owner_run_id':'old-owner','processing_id':'old-processing',
                    'completed_at':'2026-01-01','status':'failed','source_fingerprints':self.fingerprints,
                    'failures':[{'cache_key':self.key,'group_ids':self.ids,'error':'InferenceRuntimeError'}]}
        with self.svc.store.connect(write=True) as db:db.execute('INSERT INTO fact_definition_reviews VALUES(?,?,?,?)',('historical-review','p',dumps(self.prior),'2026-01-01'))
        _,messages=expected_messages(self.groups,self.known)
        def event(kind,data):return {'type':kind,'runId':'old-owner','projectId':'p','data':data}
        self.events=[event('processing_started',{'processingId':'old-processing','ownerRunId':'old-owner'}),
                     event('extraction_request',{'requestId':'prior-request','ownerRunId':'old-owner','model':self.runtime['model'],'reasoningEffort':'high','maxTokens':32768,'messages':messages}),
                     event('extraction_result',{'requestId':'prior-request','ownerRunId':'old-owner','model':self.runtime['model'],'stopReason':'length','usage':{'input':10,'output':20,'reasoning':20,'totalTokens':30}})]
        self.audit=self.root/'audit'/'old-owner.jsonl';self.audit.parent.mkdir()
        self.write_audit()

    def tearDown(self):self.fixture.tearDown(self)
    def write_audit(self):self.audit.write_text('\n'.join(json.dumps(e,ensure_ascii=False) for e in self.events)+'\n',encoding='utf-8')
    def lookup(self,**overrides):
        values={'groups':self.groups,'known':self.known,'runtime':self.runtime,'source_fingerprints':self.fingerprints}|overrides
        return historical_output_limit(self.svc.store,'p',self.key,**values)

    def test_full_original_prompt_owner_config_and_sources_prove_limit_read_only(self):
        raw=self.audit.read_bytes()
        result=self.lookup()
        self.assertEqual(result['original_request_id'],'prior-request')
        self.assertEqual(result['original_owner_run_id'],'old-owner')
        self.assertEqual(result['current_model_requests'],0)
        self.assertEqual(result['historical_usage']['output'],20)
        self.assertEqual(self.audit.read_bytes(),raw)
        with self.svc.store.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT report_json FROM fact_definition_reviews').fetchone()[0]),self.prior)
            self.assertEqual(db.execute('SELECT count(*) FROM fact_definition_cache').fetchone()[0],0)

    def test_input_prompt_owner_processing_config_or_result_change_prevents_reuse(self):
        original=copy.deepcopy(self.events)
        mutations=[lambda e:e[1]['data']['messages'][0].update(content='different system prompt'),
                   lambda e:e[1]['data']['messages'][1].update(content=e[1]['data']['messages'][1]['content']+' '),
                   lambda e:e[1]['data'].update(reasoningEffort='low'),lambda e:e[1]['data'].update(maxTokens=32767),
                   lambda e:e[1]['data'].update(ownerRunId='another-owner'),lambda e:e[0]['data'].update(processingId='different-processing'),
                   lambda e:e[2]['data'].update(stopReason='error'),lambda e:e[2]['data'].update(stopReason='aborted'),
                   lambda e:e[2]['data'].update(ownerRunId='another-owner'),lambda e:e[2]['data'].update(requestId='other-request'),
                   lambda e:e[2].update(projectId='other-project'),lambda e:e.append(copy.deepcopy(e[2])),
                   lambda e:e.append(copy.deepcopy(e[1])),
                   lambda e:e.insert(1,{**e[0],'data':{'processingId':'other-processing','ownerRunId':'old-owner'}})]
        for mutate in mutations:
            self.events=copy.deepcopy(original);mutate(self.events);self.write_audit()
            self.assertIsNone(self.lookup())

    def test_changed_groups_catalog_fingerprint_or_model_are_not_same_request(self):
        groups=copy.deepcopy(self.groups);groups[0]['evidence'][0]['text']+='new context'
        known=copy.deepcopy(self.known);known[0]['labels'].append('another label')
        fingerprints=dict(self.fingerprints);fingerprints[next(iter(fingerprints))]='different'
        for values in ({'groups':groups},{'known':known},{'source_fingerprints':fingerprints},
                       {'runtime':self.runtime|{'model':'other-model'}},{'runtime':self.runtime|{'max_tokens':16384}},
                       {'runtime':self.runtime|{'force':True}}):
            self.assertIsNone(self.lookup(**values))

    def test_missing_or_corrupt_audit_is_not_truncation_evidence(self):
        self.audit.write_text('not json',encoding='utf-8');self.assertIsNone(self.lookup())
        self.audit.unlink();self.assertIsNone(self.lookup())

    def test_already_accepted_cache_has_priority_over_historical_failure(self):
        accepted=self.fixture.model(self,self.groups)
        accepted['_review_provenance']={'processing_id':'success-processing','owner_run_id':'success-owner'}
        with self.svc.store.connect(write=True) as db:db.execute('INSERT INTO fact_definition_cache VALUES(?,?,?)',(self.key,dumps(accepted),'2026-01-02'))
        self.assertIsNone(self.lookup())
        with patch('service.definition_model.review_definitions',side_effect=AssertionError('successful cache wins')):
            report=review_project(self.svc,'p',['receivable_amount'],self.runtime)
        self.assertEqual(report['model_requests'],0);self.assertEqual(report['historical_output_limits'],[])
        self.assertEqual(report['cache_hits'],1)

    def test_verified_historical_parent_is_not_called_again_and_children_keep_new_owner(self):
        calls=[]
        before=self.audit.read_bytes()
        def model(groups,*args):
            calls.append([g['group_id'] for g in groups])
            self.assertEqual(len(groups),1,'the known truncated parent must not be sent again')
            return self.fixture.model(self,groups)
        with patch('service.definition_model.review_definitions',side_effect=model):
            report=review_project(self.svc,'p',['receivable_amount'],self.runtime)
        self.assertEqual(calls,[[self.ids[0]],[self.ids[1]]])
        self.assertEqual(report['status'],'reviewed');self.assertEqual(report['model_requests'],2)
        self.assertEqual(report['historical_output_limits'][0]['current_model_requests'],0)
        self.assertEqual(report['historical_output_limits'][0]['historical_usage']['output'],20)
        self.assertEqual(report['split_attempts'][0]['historical_index'],0)
        self.assertEqual(report['split_attempts'][0]['model_requests'],0)
        self.assertEqual(report['failed_attempts'],[],'historical scheduling is not a new model attempt')
        self.assertEqual(self.audit.read_bytes(),before)
        with self.svc.store.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT report_json FROM fact_definition_reviews WHERE review_id=?',('historical-review',)).fetchone()[0]),self.prior)
            self.assertEqual(db.execute('SELECT count(*) FROM fact_definition_cache').fetchone()[0],2)
        self.assertEqual({f['definition_review']['owner_run_id'] for f in self.fixture.facts(self)},{'pi-owner'})


if __name__=='__main__':unittest.main()

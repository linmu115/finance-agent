import copy
import json
import unittest
from unittest.mock import patch
from service.tests import test_script_cleaning as fixtures
from service.tests.test_cleaning_consistency import fact
from service.cleaning_consistency import document_conflicts, table_semantics
from service.cleaning_mapping import mapping_issues
from service.source_numbers import identifier_table_exclusion, numeric_cells
from service.source_dimensions import apply_source_dimensions
from service.accounting_basis import reapply_document_facts, identify
from service.store import dumps


class DeferralTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def extend(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed['tables'] += [dict(copy.deepcopy(parsed['tables'][0]),index=i) for i in (1,2)]
        self.s._persist_prepared('p',self.did,parsed)
        self.s.begin_script_cleaning('p',[self.did],'owner','fixture')
        state=self.s._clean_state('p',self.pid);d=state['documents'][0]
        d['batches']=[{'tables':[i],'group_id':str(i)} for i in range(3)]
        d['offered_tables']=[0];self.s._save_processing(state)

    def test_failure_defers_only_its_table_then_one_final_repair_sweep(self):
        self.extend()
        bad=copy.deepcopy(self.payload);bad['tables'][0]['rows'].pop()
        rid=self.job(bad)
        with self.assertRaisesRegex(ValueError,'validation_errors'):self.s.commit_cleaning_result('p',self.pid,rid)
        step=self.s.advance_cleaning_round('p',self.pid)['data']
        self.assertEqual(step['next_batch']['tables'],[1]);self.assertFalse(step['repair_phase'])
        self.assertEqual(set(step['deferred_tables'][self.did]),{'0'})
        self.assertTrue(step['deferred_tables'][self.did]['0']['issues'])
        self.assertEqual(step['pending_tables'][self.did],[0,1,2])
        good=copy.deepcopy(self.payload);good['tables'][0]['index']='T1'
        self.s.commit_cleaning_result('p',self.pid,self.job(good),table_indices=['t1'])
        step=self.s.advance_cleaning_round('p',self.pid)['data'];self.assertEqual(step['next_batch']['tables'],[2])
        step=self.s.advance_cleaning_round('p',self.pid)['data']
        self.assertTrue(step['repair_phase']);self.assertEqual(set(step['runnable_tables'][self.did]),{0,2})
        repair_first=step['next_batch']['tables'][0]
        step=self.s.advance_cleaning_round('p',self.pid)['data']
        self.assertEqual(step['runnable_tables'][self.did],[({0,2}-{repair_first}).pop()])
        step=self.s.advance_cleaning_round('p',self.pid)['data']
        self.assertIsNone(step['next_batch']);self.assertEqual(step['runnable_tables'][self.did],[])
        self.assertEqual(step['coverage']['tables_completed'],1)
        self.assertTrue(all(d['repair_attempted'] for d in step['deferred_tables'][self.did].values()))
        # Repeated process_documents in the same Pi run must not reset the sweep.
        again=self.s.begin_script_cleaning('p',[self.did],'owner','fixture')['data']
        self.assertIsNone(again['next_batch']);self.assertTrue(again['repair_phase'])

    def test_reference_error_keeps_evidence_and_next_batch_without_a_candidate(self):
        self.extend()
        step=self.s.advance_cleaning_round('p',self.pid,[{'tool':'get_source_table','document_id':self.did,'table_id':'T0','message':'invalid source reference'}])['data']
        error=step['deferred_tables'][self.did]['0']
        self.assertEqual(error['reason'],'tool_error_without_submission')
        self.assertEqual(error['tool_errors'][0]['message'],'invalid source reference')
        self.assertEqual(error['page'],1);self.assertEqual(step['next_batch']['tables'],[1])

    def test_successful_repair_removes_deferral_and_keeps_durable_completion(self):
        self.s.advance_cleaning_round('p',self.pid)
        self.s.commit_cleaning_result('p',self.pid,self.job())
        step=self.s.advance_cleaning_round('p',self.pid)['data']
        self.assertEqual(step['deferred_tables'][self.did],{})
        self.assertEqual(step['pending_tables'][self.did],[]);self.assertEqual(step['state'],'completed')

    def test_script_failure_retains_its_diagnostics_in_the_deferred_entry(self):
        rid=self.job();(self.root/'output'/rid/'stderr.log').write_text('MappingError: invalid source column 8','utf-8')
        with patch.object(self.s,'get_analysis_status',return_value={'data':{'state':'failed','error':'invalid source column'}}):
            self.s.get_cleaning_result('p',self.pid,rid)
        result=self.s.advance_cleaning_round('p',self.pid)['data']
        entry=result['deferred_tables'][self.did]['0']
        self.assertEqual(entry['reason'],'script_execution_failed')
        self.assertIn('column 8',entry['issues'][0]['diagnostics']['stderr.log']['text'])

    def test_real_conflict_defers_both_sides_but_not_the_next_unrelated_table(self):
        self.extend()
        _,parsed=self.s._clean_source('p',self.did);parsed['tables'][1]['rows'][1][1]='102'
        self.s._persist_prepared('p',self.did,parsed)
        self.s.commit_cleaning_result('p',self.pid,self.job())
        candidate=copy.deepcopy(self.payload);candidate['tables'][0]['index']=1
        rid=self.job(candidate)
        with self.assertRaisesRegex(ValueError,'document_value_conflict'):self.s.commit_cleaning_result('p',self.pid,rid)
        result=self.s.advance_cleaning_round('p',self.pid)['data']
        self.assertEqual(set(result['deferred_tables'][self.did]),{'0','1'})
        self.assertEqual(result['next_batch']['tables'],[2])
        self.assertTrue(all(x['reason']=='document_value_conflict' for x in result['deferred_tables'][self.did].values()))

    def test_aliases_are_local_and_unknown_id_lists_only_document_tables(self):
        for alias in ['0','t0','T0',f'{self.did}:T0']:
            self.assertEqual(self.s.get_source_table('p',self.did,alias)['data']['items'][0]['table_id'],self.did+':t0')
        for alias in ['99','foreign:t0']:
            with self.assertRaisesRegex(ValueError,'table_not_found') as ctx:self.s.get_source_table('p',self.did,alias)
            self.assertEqual(ctx.exception.details['available_table_ids'],[self.did+':t0'])

    def test_identifier_only_table_commits_its_specific_source_reason(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed['tables'][0]['rows']=[['公司股票简况','',''],['股票种类','股票简称','股票代码'],['A股','Test','600001']]
        self.s._persist_prepared('p',self.did,parsed)
        result=self.s.begin_script_cleaning('p',[self.did],'owner','fixture')['data']
        self.assertEqual(result['coverage']['tables_completed'],1);self.assertEqual(result['fact_count'],0)
        with self.s.store.connect() as db:
            saved=json.loads(db.execute('SELECT result_json FROM normalization_batches').fetchone()[0])
        reason=json.loads(saved['exclusion_reason'])
        self.assertEqual(reason['reason'],'identifier_only_table')
        self.assertEqual(reason['cells'][0],{'row':3,'column':3,'raw_value':'600001','reason':'股票代码'})

    def test_whole_table_replaces_legacy_alias_header_and_unresolved_records_with_history(self):
        self.s.commit_cleaning_result('p',self.pid,self.job())
        with self.s.store.connect(write=True) as db:
            original=dict(db.execute('SELECT * FROM facts LIMIT 1').fetchone())
            for n,alias in enumerate(['0','T0']):
                old=dict(original);old['fact_id']='legacy'+str(n);old['scope']='consolidated_IFRS'
                ref=json.loads(old['source_json']);ref['table_id']=alias;ref['row']=1;old['source_json']=dumps(ref)
                db.execute('INSERT INTO facts VALUES('+','.join('?' for _ in old)+')',list(old.values()))
        self.s.commit_cleaning_result('p',self.pid,self.job())
        with self.s.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],4)
            history=[json.loads(r[0]) for r in db.execute('SELECT fact_json FROM fact_history')]
            self.assertEqual(len(history),6)
            self.assertTrue({'legacy0','legacy1'}<={r['fact_id'] for r in history})

    def test_document_basis_reapplies_existing_facts_idempotently_with_history(self):
        self.s.commit_cleaning_result('p',self.pid,self.job())
        _,parsed=self.s._clean_source('p',self.did)
        parsed['pages'][0]['text']+='\n本财务报表按照企业会计准则编制。'
        with self.s.store.connect(write=True) as db:db.execute("UPDATE facts SET scope='consolidated_IFRS'")
        changed=reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'basis-replay')
        self.assertEqual(changed,{'updated':4,'history_preserved':4})
        self.assertEqual(reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'repeat')['updated'],0)
        with self.s.store.connect() as db:
            self.assertEqual({r[0] for r in db.execute('SELECT scope FROM facts')},{'consolidated_CAS'})
            history=[json.loads(r[0]) for r in db.execute('SELECT fact_json FROM fact_history')]
            self.assertTrue(all(r['scope']=='consolidated_IFRS' for r in history))


class SourceRulesTests(unittest.TestCase):
    def test_identifiers_in_parallel_pairs_and_column_headers_are_not_amounts(self):
        rows=[['股票种类','股票上市交易所','股票简称','股票代码','变更前股票简称'],['A股','上海','甲公司','600001','甲']]
        company={'index':0,'page':1,'rows':rows}
        self.assertEqual(numeric_cells(company),[]);self.assertTrue(identifier_table_exclusion(company))
        self.assertEqual(table_semantics(company,{},[]),[])
        self.assertEqual(mapping_issues(company,{'statement':'nonfinancial'},[],exclusion_reason='股票上市信息与证券代码'),[])
        company['rows']=[['证券代码','600001','统一社会信用代码','91310000123456789A'],['电话','021-12345678','邮编','200001'],['序号','1','登记日期','2024-12-31']]
        self.assertEqual(numeric_cells(company),[])
        company['rows'].append(['证券代码','600001','营业收入','100000'])
        self.assertEqual(len(numeric_cells(company)),1);self.assertIsNone(identifier_table_exclusion(company))
        company['rows']=[['高级无抵押定息债券','2024 年5 月17 日和2024 年11 月18 日各兑付利息4,062,500 美元。']]
        self.assertEqual(len(numeric_cells(company)),1);self.assertIsNone(identifier_table_exclusion(company))
        company['rows']=[['序号','污染物名称','排放浓度','排放总量'],['1','COD','40.72 mg/L','0.1788 吨']]
        self.assertEqual(len(numeric_cells(company)),2);self.assertIsNone(identifier_table_exclusion(company))
        company['rows']=[['项目','重要性标准'],['重要的在建工程项目','单项在建工程的预算金额≥总资产的5%']]
        self.assertEqual(table_semantics(company,{},[]),[])

    def test_hierarchy_counterparties_direction_and_genuine_conflict(self):
        a={'table':{'index':0,'page':1,'rows':[['项目','2024'],['其他应付款','100']]},'facts':[fact(metric='other_payables')]}
        b={'table':{'index':1,'page':2,'rows':[['项目','2024'],['其他应付款','90'],['合计','100']]},'facts':[fact(1,value='90',raw='90',metric='other_payables'),fact(1,row=3,metric='other_payables')]}
        apply_source_dimensions(b['table'],b['facts']);self.assertEqual(document_conflicts([a,b]),[])
        b['facts'][1]['value']='120';b['facts'][1]['raw_value']='120'
        self.assertEqual({i['table'] for i in document_conflicts([a,b])},{0,1})
        for item,side in [(a,'资产'),(b,'负债')]:
            for f in item['facts']:f['metric']='forward_contracts'
            apply_source_dimensions(item['table'],item['facts'],context={'text':'2、衍生金融'+side})
        self.assertEqual(document_conflicts([a,b]),[])


if __name__=='__main__':unittest.main()

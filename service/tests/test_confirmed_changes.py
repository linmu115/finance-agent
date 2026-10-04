import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from service.store import Store, dumps, utcnow
from service.database_admin import execute
from service.attachment_flows import record_processing, read, record_read
from service.three_statement import three_statement, EXAMPLE

class ConfirmedChanges(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        with self.store.connect(write=True) as db:
            for p in ['a','b']:db.execute('INSERT INTO projects VALUES(?,?,?)',(p,p,utcnow()))
            db.execute('INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,state,parser_version,created_at) VALUES(?,?,?,?,?,?,?,?,?)',('doc','a','示例.csv','sha','uploads/a.csv','text/csv','ready','test',utcnow()))
            db.execute('INSERT INTO facts(fact_id,document_id,project_id,metric,year,period,scope,currency,raw_value,raw_unit,value,source_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('f','doc','a','revenue',2024,'2024FY','consolidated','CNY','1','万元','10000',dumps({'page':1})))
    def tearDown(self):self.tmp.cleanup()

    def test_db_atomic_rollback_backup_consumption_and_protected_tables(self):
        result=execute(self.store,'a',{'operation':'update_fact','fact_id':'f','value':'12000'},'approve1')
        self.assertTrue((self.store.root/result['backup']).is_file())
        with closing(sqlite3.connect(self.store.root/result['backup'])) as old:self.assertEqual(old.execute('SELECT value FROM facts').fetchone()[0],'10000')
        with self.assertRaises(ValueError):execute(self.store,'a',{'operation':'sql','sql':'DELETE FROM facts'},'approve1')
        for i,sql in enumerate(["ATTACH DATABASE ':memory:' AS other",'PRAGMA writable_schema=ON',"UPDATE app_state SET value_json='{}'",'DROP TABLE database_audit','ALTER TABLE app_state RENAME TO tmp_state']):
            with self.assertRaises(sqlite3.DatabaseError):execute(self.store,'a',{'operation':'sql','sql':sql},f'denied{i}')
        with self.assertRaises(sqlite3.DatabaseError):execute(self.store,'a',{'operation':'analysis_changes','commands':[{'sql':'UPDATE facts SET value=?','parameters':['999']},{'sql':'INSERT INTO missing VALUES(1)'}]},'atomic')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT value FROM facts').fetchone()[0],'12000')
        with self.assertRaises(ValueError):execute(self.store,'a',{'operation':'sql','sql':'SELECT 1'},'atomic')
        execute(self.store,'a',{'operation':'sql','sql':'CREATE TABLE scenario_assumptions(name TEXT,value TEXT)'},'ddl1')
        execute(self.store,'a',{'operation':'sql','sql':'ALTER TABLE scenario_assumptions ADD COLUMN source TEXT'},'ddl2')
        execute(self.store,'a',{'operation':'sql','sql':'DROP TABLE scenario_assumptions'},'ddl3')
        self.assertEqual(execute(self.store,'a',{'operation':'read_other_project','target_project_id':'b'},'cross')['results'][0]['rows'],[])

    def test_attempt_snapshots_survive_other_conversation_reprocessing_and_deletion(self):
        state={'processing_id':'p1','project_id':'a','owner_run_id':'r1','state':'queued','created_at':utcnow(),'updated_at':utcnow(),'documents':[{'document_id':'doc','name':'示例.csv','state':'queued','fact_count':0}]}
        with self.store.connect(write=True) as db:record_processing(db,state)
        with self.store.connect(write=True) as db:
            db.execute("UPDATE facts SET value='12000'");state['state']='completed';state['documents'][0].update(state='ready',fact_count=1);record_processing(db,state)
        first=read(self.store,'a',['r1'],'p1:doc');self.assertEqual(first['changes']['changed'],1)
        record_read(self.store,'a','r2','doc')
        execute(self.store,'a',{'operation':'update_fact','fact_id':'f','value':'19000'},'edit')
        old=read(self.store,'a',['r1'],'p1:doc');self.assertEqual(old['facts'][0]['value'],'12000');self.assertFalse(old['facts'][0]['current_match'])
        with self.assertRaises(ValueError):read(self.store,'a',['r2'],'p1:doc')
        self.assertEqual(read(self.store,'b',['r1'])['flows'],[])
        execute(self.store,'a',{'operation':'delete_document','document_id':'doc'},'delete')
        self.assertEqual(read(self.store,'a',['r1'],'p1:doc')['facts'][0]['value'],'12000')

    def test_three_statements_independently_calculated_and_shortfall_visible(self):
        r=three_statement(EXAMPLE);income=r['tables']['income_statement'][0];cf=r['tables']['cash_flow_statement'][0];bs=r['tables']['balance_sheet'][0]
        # 1100-660-165-40=235 EBIT; 10 interest; 56.25 tax; NI=168.75.
        self.assertEqual(Decimal(income['net_income']),Decimal('168.75'))
        # AR +10, inventory +12, AP -14 -> WC uses 36. CFO=168.75+40-36=172.75.
        self.assertEqual(float(cf['operating_cash_flow']),172.75);self.assertEqual(float(bs['cash']),172.75)
        self.assertEqual(float(bs['assets']),864.75);self.assertEqual(float(bs['liabilities_and_equity']),864.75)
        bad=copy.deepcopy(EXAMPLE);bad['opening']['equity']='401'
        with self.assertRaises(ValueError):three_statement(bad)
        stress=copy.deepcopy(EXAMPLE);stress['forecast'][0]['capex']='1000';self.assertTrue(any('shortfall' in w for w in three_statement(stress)['warnings']))
        invalid=copy.deepcopy(EXAMPLE);invalid['forecast'][0]['debt_repayment']='300'
        with self.assertRaises(ValueError):three_statement(invalid)

    def test_restart_does_not_display_interrupted_work_as_still_running_or_invent_snapshot(self):
        now=utcnow();state={'processing_id':'restart','project_id':'a','owner_run_id':'interrupted','state':'normalizing','created_at':now,'updated_at':now,'documents':[{'document_id':'doc','state':'normalizing','progress':0.5,'fact_count':0}]}
        with self.store.connect(write=True) as db:
            db.execute('INSERT INTO processing_runs VALUES(?,?,?,?,?,?)',('restart','a','interrupted',dumps(state),now,now));record_processing(db,state)
        reopened=Store(self.tmp.name);result=read(reopened,'a',['interrupted'],'restart:doc')
        self.assertEqual(result['attempt_state'],'failed');self.assertTrue(result['snapshot_missing']);self.assertEqual(result['facts'],[])

if __name__=='__main__':unittest.main()

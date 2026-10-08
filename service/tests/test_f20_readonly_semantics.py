import copy
import json
import unittest

from service.accounting_basis import identify, reapply_document_facts
from service.dimension_semantics import classify_dimensions
from service.financial_workpapers import load_facts
from service.metric_normalization import apply_metric_normalization
from service.source_dimensions import apply_source_dimensions
from service.standard_metrics import canonical_rows
from service.tests.test_ingestion_semantics_v3 import fact
from service.tests import test_script_cleaning as fixtures


class ReadOnlySemanticsTests(unittest.TestCase):
    def test_real_allowance_period_cells_keep_metric_and_stored_roles(self):
        table={'rows':[['类别','期初余额','本期变动金额','','','','期末余额'],
                       ['','','计提','收回或转回','转销或核销','其他变动',''],
                       ['其他应收款','29834174.36','-508936.63','323190.29','619083.72','18767.52','28401731.24']]}
        for column,value in [(2,'29834174.36'),(7,'28401731.24')]:
            f=fact('receivables_allowance_rollforward','其他应收款',value,row=3,column=column,
                   dimensions={'financial_item':'other_receivables'})
            before=copy.deepcopy(f);ctx={'text':'（4）坏账准备的情况','statement':'notes'}
            apply_metric_normalization(table,[f],ctx);apply_source_dimensions(table,[f],context=ctx)
            self.assertEqual(f,before)
            classify_dimensions(table,[f],ctx)
            self.assertEqual(f,before, 'read interpretation cannot excuse a different original metric')

    def test_submission_canonical_rows_keep_custom_id(self):
        table={'rows':[['项目','2024'],['营业收入','12']]}
        rows=[{'row':2,'attributes':{'metric':'reported_revenue'}}]
        self.assertEqual(canonical_rows(table,rows,statement='income'),rows)


class StoredSemanticsTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def test_commit_reapply_and_workpaper_read_do_not_rewrite_facts(self):
        self.payload['tables'][0]['rows'][0]['attributes']['metric']='bespoke_turnover'
        self.s.commit_cleaning_result('p',self.pid,self.job())
        with self.s.store.connect() as db:
            before=[dict(r) for r in db.execute('SELECT * FROM facts ORDER BY fact_id')]
            parsed=json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?',(self.did,)).fetchone()[0])
        self.assertEqual(sum(r['metric']=='bespoke_turnover' for r in before),2)
        load_facts(self.s,'p',self.did)
        result=reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'readonly-test')
        self.assertEqual(result,{'updated':0,'history_preserved':0})
        with self.s.store.connect() as db:
            self.assertEqual(before,[dict(r) for r in db.execute('SELECT * FROM facts ORDER BY fact_id')])

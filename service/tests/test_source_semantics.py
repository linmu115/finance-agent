import copy
import json
import unittest

from service.accounting_basis import identify, reapply_document_facts
from service.cleaning_rules import context
from service.source_semantics import apply_source_semantics
from service.tests import test_script_cleaning as fixtures


def document(rows, heading='报告分部的财务信息', report='2024年年度报告'):
    table={'index':0,'page':1,'rows':rows,'cells':{}}
    return {'company':'Test','report_year':2024,'pages':[{'page':1,'text':report+'\n'+heading+'\n单位：元\n币种：人民币'}],
            'tables':[table],'warnings':[]},table


def fact(row, column=2, period='2024-FY', scope='consolidated_CAS', currency='CNY'):
    return {'company':'Test','metric':'test_metric','year':int(period[:4]) if period!='unknown' else None,
            'period':period,'scope':scope,'currency':currency,'raw_value':'100','value':'100',
            'source':{'table_id':'doc:t0','row':row,'column':column,'normalization':
                      {'statement':'notes','period_start':'2024-01-01','period_end':'2024-12-31','dimensions':{}}}}


class SourceSemanticsTests(unittest.TestCase):
    def apply(self, parsed, table, facts):
        apply_source_semantics(parsed,table,facts,context(parsed,table))

    def test_segment_stocks_become_instants_but_flows_and_growth_do_not(self):
        parsed,table=document([['项目','食品分部'],['主营业务收入','100'],['资产总额','100'],['负债总额','100'],
                               ['资产总额增加','100'],['资产总额','100']])
        facts=[fact(i) for i in range(2,7)];facts[-1]['currency']='percent'
        unchanged=copy.deepcopy([facts[0],facts[3],facts[4]])
        self.apply(parsed,table,facts)
        self.assertEqual([f['period'] for f in facts],['2024-FY','2024-12-31','2024-12-31','2024-FY','2024-FY'])
        self.assertEqual([facts[0],facts[3],facts[4]],unchanged)
        self.assertEqual(facts[1]['source']['normalization']['period_start'],'2024-12-31')
        once=copy.deepcopy(facts);self.apply(parsed,table,facts);self.assertEqual(facts,once)

    def test_source_dates_and_comparative_years_override_report_end(self):
        parsed,table=document([['项目','2024年6月30日','2023年12月31日'],['资产总额','100','100']])
        facts=[fact(2),fact(2,3,period='2023-FY')];self.apply(parsed,table,facts)
        self.assertEqual([f['period'] for f in facts],['2024-06-30','2023-12-31'])

    def test_interim_and_quarterly_balance_dates_do_not_assume_december(self):
        for title,end in [('半年度','06-30'),('第三季度','09-30')]:
            parsed,table=document([['项目','分部'],['负债总额','100']],report='2024年'+title+'报告')
            facts=[fact(2)];self.apply(parsed,table,facts)
            self.assertEqual(facts[0]['period'],'2024-'+end)

    def test_unknown_report_date_and_unknown_period_are_not_guessed(self):
        for report,period in [('内部资料','2024-FY'),('2024年年度报告','unknown')]:
            parsed,table=document([['项目','分部'],['资产总额','100']],report=report)
            facts=[fact(2,period=period)];before=copy.deepcopy(facts);self.apply(parsed,table,facts)
            self.assertEqual(facts,before)

    def test_quarter_headers_and_attributable_row_resolve_entire_table(self):
        parsed,table=document([['项目','第一季度','第二季度'],['营业收入','100','100'],
                               ['归属于上市公司股东的净利润','100','100']],heading='九、2024年分季度主要财务数据')
        facts=[fact(2,period='2024-Q1',scope='unspecified_CAS'),fact(3,3,period='2024-Q2',scope='unspecified_CAS')]
        self.apply(parsed,table,facts)
        self.assertEqual([f['scope'] for f in facts],['consolidated_CAS']*2)
        self.assertEqual([f['period'] for f in facts],['2024-Q1','2024-Q2'])
        self.assertEqual(context(parsed,table)['scope'],'consolidated')

    def test_explicit_parent_heading_wins_and_missing_scope_evidence_stays_unknown(self):
        for heading,expected in [('母公司分季度主要财务数据','parent_CAS'),('合并分季度主要财务数据','consolidated_CAS'),
                                 ('分季度主要财务数据','unspecified_CAS'),('季度预测','unspecified_CAS')]:
            parsed,table=document([['项目','第一季度'],['营业收入','100']],heading=heading)
            facts=[fact(2,period='2024-Q1',scope='unspecified_CAS')];self.apply(parsed,table,facts)
            self.assertEqual(facts[0]['scope'],expected)

    def test_balance_statement_columns_are_instants_without_changing_movement_columns(self):
        parsed,table=document([['项目','2024年','本期变动金额'],['应收账款','100','100']],heading='合并资产负债表')
        facts=[fact(2),fact(2,3)];self.apply(parsed,table,facts)
        self.assertEqual([f['period'] for f in facts],['2024-12-31','2024-FY'])

    def test_note_balance_column_and_opening_row_use_source_endpoints(self):
        parsed,table=document([['项目','期末余额','期初余额'],['应收款项','100','100']])
        facts=[fact(2),fact(2,3)];self.apply(parsed,table,facts)
        self.assertEqual([f['period'] for f in facts],['2024-12-31','2023-12-31'])
        parsed,table=document([['项目','2024年'],['年初余额','100'],['本期增加','100']])
        facts=[fact(2),fact(3)];self.apply(parsed,table,facts)
        self.assertEqual([f['period'] for f in facts],['2023-12-31','2024-FY'])


class ReapplicationTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def test_commit_and_document_reapply_share_scope_rules_with_history(self):
        parsed,table=document([['项目','第一季度','第二季度'],['营业收入','100','80'],
                               ['归属于上市公司股东的净利润','40','30']],heading='分季度主要财务数据')
        parsed['pages'][0]['text']+='\n企业会计准则'
        self.s._persist_prepared('p',self.did,parsed)
        # New mappings follow the same deterministic source interpretation.
        self.schema['scope']='unspecified_CAS'
        self.schema['columns_json']=json.dumps([{'column':2,'period':'2024-Q1'},{'column':3,'period':'2024-Q2'}])
        self.payload['tables'][0]['rows'][1]['attributes']={'metric':'net_profit_parent','label':'归属于上市公司股东的净利润'}
        self.s.commit_cleaning_result('p',self.pid,self.job())
        with self.s.store.connect(write=True) as db:
            self.assertEqual({r[0] for r in db.execute('SELECT scope FROM facts')},{'consolidated_CAS'})
            db.execute("UPDATE facts SET scope='unspecified_CAS'")
        result=reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'source-reapply')
        self.assertEqual(result,{'updated':4,'history_preserved':4})
        self.assertEqual(reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'repeat')['updated'],0)
        with self.s.store.connect() as db:
            history=[json.loads(r[0]) for r in db.execute("SELECT fact_json FROM fact_history WHERE processing_id='source-reapply'")]
            self.assertEqual(len(history),4);self.assertTrue(all(r['scope']=='unspecified_CAS' for r in history))

    def test_stock_period_reapplication_updates_query_fields_and_archives_old_period(self):
        parsed,table=document([['项目','2024年','2023年'],['主营业务收入','100','80'],['资产总额','40','30']])
        parsed['pages'][0]['text']+='\n企业会计准则'
        self.s._persist_prepared('p',self.did,parsed)
        self.schema['columns_json']=json.dumps([{'column':2,'period':'2024-FY'},{'column':3,'period':'2023-FY'}])
        self.payload['tables'][0]['rows'][1]['attributes']={'metric':'segment_assets','label':'资产总额'}
        self.s.commit_cleaning_result('p',self.pid,self.job())
        with self.s.store.connect(write=True) as db:
            stock=[dict(r) for r in db.execute("SELECT * FROM facts WHERE metric='segment_assets'")]
            self.assertEqual({r['period'] for r in stock},{'2024-12-31','2023-12-31'})
            for old in stock:
                source=json.loads(old['source_json']);source['normalization'].pop('source_semantics')
                source['normalization'].update(period_start='',period_end='')
                db.execute('UPDATE facts SET period=?,source_json=? WHERE fact_id=?',(f"{old['year']}-FY",json.dumps(source),old['fact_id']))
        result=reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'stock-reapply')
        self.assertEqual(result,{'updated':2,'history_preserved':2})
        self.assertEqual(reapply_document_facts(self.s,'p',self.did,parsed,identify(parsed),'repeat')['updated'],0)
        with self.s.store.connect() as db:
            self.assertEqual({r[0] for r in db.execute("SELECT period FROM facts WHERE metric='segment_assets'")},{'2024-12-31','2023-12-31'})
            history=[json.loads(r[0]) for r in db.execute("SELECT fact_json FROM fact_history WHERE processing_id='stock-reapply'")]
            self.assertEqual({r['period'] for r in history},{'2024-FY','2023-FY'})


if __name__=='__main__':unittest.main()

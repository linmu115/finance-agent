import copy
import json
import unittest
from service.cleaning_consistency import table_semantics, document_conflicts
from service.tests import test_script_cleaning as fixtures


def fact(table=0,row=2,column=2,value='100',raw='100',metric='net_profit',**meta):
    return {'company':'Company','metric':metric,'period':'2024-FY','scope':'consolidated_CAS','currency':'CNY',
            'raw_value':raw,'raw_unit':'元','value':value,'source':{'table_id':f'd:t{table}','row':row,'column':column,'page':table+1,
            'normalization':{'dimensions':{},**meta}}}


class ConsistencyTests(unittest.TestCase):
    def test_conflicts_report_both_coordinates_but_respect_precision_and_economic_dimensions(self):
        a={'table':{'index':0,'rows':[['项目','2024'],['净利润','100']]},'facts':[fact()]}
        b={'table':{'index':1,'rows':[['项目','2024'],['净利润','90']]},'facts':[fact(1,value='90',raw='90')]}
        issues=document_conflicts([a,b]);self.assertEqual({i['table'] for i in issues},{0,1})
        self.assertEqual(issues[0]['left']['value'],'100');self.assertEqual(issues[0]['right']['row'],2)
        b['facts'][0].update(value='100.4',raw_value='100.4');self.assertEqual(document_conflicts([a,b]),[])
        b['facts'][0].update(value='90',raw_value='90');b['facts'][0]['source']['normalization']['dimensions']={'segment':'other'}
        self.assertEqual(document_conflicts([a,b]),[])
        b['facts'][0]['source']['normalization']={'data_kind':'analyst_forecast'}
        self.assertEqual(document_conflicts([a,b]),[])

    def test_zero_records_cannot_be_completed_by_a_gap_note(self):
        table={'index':0,'page':2,'rows':[['现金流量表（百万元）','2024','2025E']]}
        self.assertEqual(table_semantics(table,{},[])[0]['reason'],'numeric_table_without_records')
        table['rows']=[['项目','2024'],['净利润','100']]
        self.assertTrue(table_semantics(table,{},[]))
        self.assertFalse(table_semantics(table,{},[fact()]))
        table['rows']=[[''],['']];self.assertFalse(table_semantics(table,{},[]))
        table['rows']=[['公司邮政编码','564501']];self.assertFalse(table_semantics(table,{},[]))
        table['rows']=[['Corporate information','2'],['Financial statements','28']]
        self.assertFalse(table_semantics(table,{},[],'CONTENTS'))
        table['rows']=[['公司继续调整渠道，业绩改善。','10%'],['明年有望复苏。','2%']]
        self.assertFalse(table_semantics(table,{},[],'行业与沪深300指数对比图'))

    def test_peer_aggregate_and_parallel_panel_do_not_become_issuer_dimensions(self):
        peer={'index':0,'page':1,'rows':[['公司简称 公司代码','2024 EPS'],['平均值','1.2'],['Other 600001 CH','1.3']]}
        self.assertEqual(table_semantics(peer,{},[fact()])[0]['reason'],'peer_aggregate_assigned_to_company')
        aggregate=fact(entity_kind='other');aggregate['company']='可比公司平均值'
        self.assertEqual(table_semantics(peer,{},[aggregate]),[])
        self.assertEqual(table_semantics(peer,{},[fact(row=3)])[0]['reason'],'peer_row_company_mismatch')
        table={'index':0,'page':1,'rows':[['年度','2024','2025 年度','2024','2025'],['现金','100','90 净利润','70','80']]}
        f=fact(column=4,value='70',raw='70',row_metric='cash',dimensions={'financial_item':'cash'})
        self.assertEqual(table_semantics(table,{},[f])[0]['reason'],'parallel_panel_dimension_inheritance')
        f['source']['normalization']['dimensions']={};self.assertEqual(table_semantics(table,{},[f]),[])

    def test_opposite_signs_require_source_presentation_evidence(self):
        a={'table':{'index':0,'rows':[['Gain on disposal','16']]},'facts':[fact(row=1,value='16',metric='gain_disposal_ppe')]}
        b={'table':{'index':1,'rows':[['Gain on disposal','(16)']]},'facts':[fact(1,row=1,value='-16',raw='(16)',metric='gain_disposal_ppe')]}
        self.assertTrue(document_conflicts([a,b]))
        b['page_text']='Profit before tax arrived at after charging/(crediting)'
        self.assertEqual(document_conflicts([a,b]),[])
        b['facts'][0]['value']='-18';self.assertTrue(document_conflicts([a,b]))


class ContinuationConsistencyTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def test_conflict_reopens_committed_peer_and_good_table_can_still_commit(self):
        _,parsed=self.s._clean_source('p',self.did);parsed=copy.deepcopy(parsed)
        for index in (1,2):
            table=copy.deepcopy(parsed['tables'][0]);table['index']=index
            if index==1:table['rows'][1][1]='102'
            parsed['tables'].append(table)
        self.s._persist_prepared('p',self.did,parsed)
        self.pid=self.s.begin_script_cleaning('p',[self.did],'cross','fixture')['data']['processing_id']
        self.s.commit_cleaning_result('p',self.pid,self.job())
        bad=copy.deepcopy(self.payload['tables'][0]);bad['index']=1
        good=copy.deepcopy(self.payload['tables'][0]);good['index']=2;good['schema']['scope']='parent_unknown'
        rid=self.job({'tables':[bad,good]})
        result=self.s.commit_cleaning_result('p',self.pid,rid)['data']
        self.assertEqual(result['committed_tables'],[2]);self.assertEqual(result['pending_tables'][self.did],[0,1])
        self.assertEqual(result['failed_tables'][0]['issues'][0]['reason'],'document_value_conflict')
        checkpoint=self.s.get_processing_checkpoint('p',self.did)['data']['documents'][0]
        self.assertGreater(checkpoint['counts']['failed'],0)

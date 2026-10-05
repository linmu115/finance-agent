import copy
import json
import unittest
from unittest.mock import patch
from service.semantic import materialize, normalize_document
from service.semantic_compact import expand_mappings
from service.semantic_repair import merge_repairs, safe_revision, repair_input
from service.tests.test_semantic_sources import mappings, sdk_result

class SemanticCostTests(unittest.TestCase):
    def fixture(self):
        columns=[{'column':2,'period':'2024-FY','start':'2024-01-01','end':'2024-12-31','unit':'元','currency':'CNY'},
                 {'column':3,'period':'2023-FY','start':'2023-01-01','end':'2023-12-31','unit':'元','currency':'CNY'},
                 {'column':4,'period':'2024-FY','unit':'%','currency':'percent','metric':'revenue_yoy'}]
        item={'table':{'index':0,'page':7,'rows':[['营业收入','100','90','11.11'],['总资产','200','180','11.11']]},'rows':[1,2],
              'text':'context\n目标区\n[[T0]]\n[[T0:R1]] C1=营业收入 | C2=100 | C3=90 | C4=11.11\n[[T0:R2]] C1=总资产 | C2=200 | C3=180 | C4=11.11'}
        ex=mappings(0,1,'revenue',columns)
        ex.append(mappings(0,2,'assets',columns)[1])
        return item,ex

    def test_explicit_defaults_and_row_patches_expand_without_losing_any_column(self):
        item,ex=self.fixture();wire=copy.deepcopy(ex)
        schema=wire[0]['attributes'];columns=json.loads(schema['columns_json'])
        schema['column_defaults_json']=json.dumps({'unit':'元','currency':'CNY'})
        schema['columns_json']=json.dumps([{k:v for k,v in c.items() if k not in {'unit','currency'}} if c['column']!=4 else c for c in columns])
        wire[2]['attributes']['column_overrides_json']=json.dumps({'columns':[{'column':c,'period':str(y)+'-12-31','start':''} for c,y in [(2,2024),(3,2023)]]})
        expected=copy.deepcopy(ex)
        expected[2]['attributes']['columns_json']=json.dumps([{**c,'period':c['period'][:4]+'-12-31','start':''} if c['column']!=4 else c for c in columns])
        expanded=expand_mappings(wire)
        self.assertEqual(materialize(expanded,[item],'d','m'),materialize(expected,[item],'d','m'))
        self.assertIn('column_defaults_json',wire[0]['attributes'])
        self.assertNotIn('column_defaults_json',expanded[0]['attributes'])
        self.assertEqual(len(json.loads(expanded[2]['attributes']['columns_json'])),3)

    def test_legacy_partial_array_remains_an_error_and_invalid_patch_cannot_drop_year(self):
        item,ex=self.fixture();cols=json.loads(ex[0]['attributes']['columns_json'])
        ex[1]['attributes']['columns_json']=json.dumps([cols[-1]])
        facts,issues=materialize(expand_mappings(ex),[item],'d','m')
        self.assertEqual({i['column'] for i in issues if i['reason']=='incomplete_column_override'},{2,3})
        ex[1]['attributes'].pop('columns_json')
        ex[1]['attributes']['column_overrides_json']='{"columns":[{"column":99,"unit":"元"}]}'
        with self.assertRaisesRegex(ValueError,'unknown_or_duplicate'):expand_mappings(ex)

    def test_cell_repair_preserves_valid_neighbours_and_rejects_unauthorized_target(self):
        item,ex=self.fixture();cols=json.loads(ex[0]['attributes']['columns_json']);cols[0]['period']='unknown'
        ex[1]['attributes']['columns_json']=json.dumps(cols)
        _,issues=materialize(ex,[item],'d','m')
        proposal={'class':'cell_patch','text':'[[T0:R1]]','span':[1,10],'attributes':{'column':2,'column_json':'{"period":"2024-FY"}'}}
        revised=merge_repairs(ex,[proposal],item,issues)
        self.assertTrue(safe_revision(ex,revised,[item],'d','m',materialize))
        self.assertEqual(len(materialize(revised,[item],'d','m')[0]),6)
        self.assertEqual(ex[2],revised[2])
        self.assertNotIn('[[T0:R2]]',repair_input(item,ex,issues))
        proposal['attributes']['column']=3
        with self.assertRaisesRegex(ValueError,'out_of_scope'):merge_repairs(ex,[proposal],item,issues)

    def test_fewer_issues_is_not_enough_if_a_good_cell_changes_or_disappears(self):
        item,ex=self.fixture();broken=copy.deepcopy(ex)
        broken[1]['attributes']['unit']='unknown'
        repaired=copy.deepcopy(ex);repaired[2]['attributes']['metric']='wrong_assets'
        self.assertFalse(safe_revision(broken,repaired,[item],'d','m',materialize))
        repaired=ex[:2]
        self.assertFalse(safe_revision(ex,repaired,[item],'d','m',materialize))

    def test_legacy_off_is_floored_to_low_and_only_defective_row_escalates_to_high(self):
        parsed={'company':'fixture','report_year':2024,'pages':[{'page':1,'text':'2024合并报表，单位元'}],
                'tables':[{'index':0,'page':1,'rows':[['资产','100'],['现金','80']]}]}
        calls=[]
        def model(**kwargs):
            effort=kwargs['config'].provider_kwargs['reasoning_effort'];calls.append((effort,kwargs['text_or_documents']))
            if effort=='low':return sdk_result(mappings(0,1))
            return sdk_result([mappings(0,2,'cash')[1]])
        runtime={'model':'fixture','api_key':'test','base_url':'http://127.0.0.1:1/v1','cleaning_effort':'none','compact_mappings':True,'targeted_repairs':True}
        with patch('langextract.extract',side_effect=model):
            facts,report=normalize_document(parsed,'d',runtime,lambda *_:None,lambda:False,lambda _:None,lambda *_:None)
        self.assertEqual([c[0] for c in calls],['low','high']);self.assertEqual(len(facts),2)
        self.assertNotIn('[[T0:R1]]',calls[1][1]);self.assertEqual(report['low_requests'],1);self.assertEqual(report['high_requests'],1)
        self.assertEqual(report['issues'],[])

    def test_optimization_does_not_invalidate_saved_source_batches_or_mix_request_caches(self):
        from service.semantic import SCHEMA_HASH, VERSION
        parsed={'company':'fixture','report_year':2024,'pages':[{'page':1,'text':'2024合并单位元'}],
                'tables':[{'index':0,'page':1,'rows':[['资产','100']]}]}
        base={'model':'fixture','api_key':'test','base_url':'http://127.0.0.1:1/v1','processing_id':'test'}
        keys=[]
        with patch('langextract.extract',return_value=sdk_result(mappings(0,1))):
            for effort,compact,targeted in [('low',False,False),('low',True,False),('low',True,True)]:
                normalize_document(parsed,'d',{**base,'cleaning_effort':effort,'compact_mappings':compact,'targeted_repairs':targeted},
                    lambda *_:None,lambda:False,lambda _:None,lambda key,_:keys.append(key))
        self.assertEqual(len(set(keys)),3)
        saved={'version':VERSION,'schema_hash':SCHEMA_HASH,'model':'fixture','extractions':mappings(0,1),'inference_policy':{'cleaning':'low'}}
        with patch('langextract.extract',side_effect=AssertionError('paid request for saved work')):
            facts,report=normalize_document(parsed,'d',{**base,'cleaning_effort':'none','compact_mappings':True,'targeted_repairs':True},
                lambda *_:None,lambda:False,lambda _:None,lambda *_:None,resume_get=lambda _:saved)
        self.assertEqual(len(facts),1);self.assertEqual(report['resumed_batches'],1);self.assertEqual(report['requests'],0)
        # A previously saved no-thinking interpretation is not a valid shortcut.
        with patch('langextract.extract',return_value=sdk_result(mappings(0,1))) as call:
            _,report=normalize_document(parsed,'d',base,lambda *_:None,lambda:False,lambda _:None,lambda *_:None,
                resume_get=lambda _:{**saved,'inference_policy':{'cleaning':'none'}})
        self.assertEqual(call.call_count,1);self.assertEqual(report['resumed_batches'],0)

    def test_nonfinancial_classification_requires_independent_high_review_even_when_resumed(self):
        parsed={'company':'fixture','report_year':2024,'pages':[{'page':1,'text':'2024注册资本单位元'}],
                'tables':[{'index':0,'page':1,'rows':[['子公司A','100']]}]}
        excluded=mappings(0,1)[:1];excluded[0]['attributes'].update(statement='nonfinancial',columns_json='[]')
        calls=[];details=[]
        def model(**kwargs):
            effort=kwargs['config'].provider_kwargs['reasoning_effort'];calls.append(effort)
            return sdk_result(excluded if effort=='low' else mappings(0,1,'registered_capital'))
        runtime={'model':'fixture','api_key':'test','base_url':'http://127.0.0.1:1/v1','cleaning_effort':'low','compact_mappings':True,'targeted_repairs':True}
        with patch('langextract.extract',side_effect=model):
            facts,report=normalize_document(parsed,'d',runtime,lambda *_:None,lambda:False,lambda _:None,lambda *_:None,
                resume_get=lambda _:{'extractions':excluded},on_batch=lambda *args:details.append(args[-1]))
        self.assertEqual(calls,['low','high']);self.assertEqual(len(facts),1);self.assertEqual(report['resumed_batches'],0)
        self.assertTrue(details[0]['nonfinancial_reviewed'])

    def test_long_continuation_gets_verbatim_header_and_section_without_changing_coordinates(self):
        from service.semantic_context import source_structure_context,with_structure_context
        header={'index':0,'page':2,'rows':[['主体','期初账面价值','期末账面价值'],['甲','100','200']]}
        tail={'index':3,'page':5,'rows':[['乙','300','400']]}
        parsed={'pages':[{'page':1,'text':'十九、母公司财务报表注释'},{'page':2,'text':'3、长期股权投资\n单位：元'},{'page':5,'text':'续表'}],'tables':[header,tail]}
        context=source_structure_context(parsed,tail)
        self.assertIn('母公司财务报表注释',context);self.assertIn('物理页2',context);self.assertIn('期初账面价值',context);self.assertIn('单位：元',context)
        item={'table':tail,'rows':[1],'text':'page context\n本表起始行（仅上下文，不表示都是表头）：乙 | 300 | 400\n目标区\n[[T3:R1]] C1=乙 | C2=300 | C3=400'}
        enriched=with_structure_context([item],parsed)[0]
        self.assertEqual(enriched['rows'],item['rows']);self.assertIs(enriched['table'],tail)
        self.assertTrue(enriched['text'].startswith('page context\n'))
        self.assertNotIn('母公司财务报表注释',item['text'])

    def test_selected_sample_keeps_full_document_header_evidence(self):
        from service.semantic import table_batches
        parsed={'company':'fixture','report_year':2024,
                'pages':[{'page':2,'text':'母公司投资，单位元'},{'page':5,'text':'续表'}],
                'tables':[{'index':0,'page':2,'rows':[['主体','期初账面价值','期末账面价值'],['甲','100','200']]},
                          {'index':3,'page':5,'rows':[['乙','300','400']]}]}
        selected=next(b for b in table_batches(parsed) if b[0]['table']['index']==3)
        ex=mappings(3,1,columns=[{'column':2,'period':'2023-12-31','unit':'元','currency':'CNY'},
                                {'column':3,'period':'2024-12-31','unit':'元','currency':'CNY'}])
        runtime={'model':'fixture','api_key':'test','base_url':'http://127.0.0.1:1/v1','compact_mappings':True}
        with patch('langextract.extract',return_value=sdk_result(ex)) as call:
            facts,report=normalize_document(parsed,'d',runtime,lambda *_:None,lambda:False,lambda _:None,lambda *_:None,selected_batches=[selected])
        self.assertEqual(call.call_count,1);self.assertEqual(report['batches'],1);self.assertEqual(len(facts),2)
        self.assertIn('期初账面价值',call.call_args.kwargs['text_or_documents'])
        self.assertNotIn('[[T0:R2]]',call.call_args.kwargs['text_or_documents'])

if __name__=='__main__':unittest.main()

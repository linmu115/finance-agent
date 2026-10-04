import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from service.core import FinanceService
from service.baseline import prepare_document_sources


class BaselineSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.service=FinanceService(self.temp.name)
        self.service.create_project('p','baseline');self.service.create_project('other','other')
        source=Path(self.temp.name)/'uploads'/'source.csv'
        source.write_text('项目,2025年,2024年\n营业收入,123.45,100.00\n',encoding='utf8')
        self.doc=self.service.register_document('p',str(source),'未映射原文.csv')['data']['document_id']

    def tearDown(self):
        for name in ['pool','processing_pool','analysis_pool','embedding_pool']:getattr(self.service,name).shutdown(wait=True)
        self.temp.cleanup()

    def test_raw_index_is_available_without_any_fact_cleaning(self):
        with patch('service.semantic.normalize_document',side_effect=AssertionError('model must not run')),patch('service.core.extract_facts',side_effect=AssertionError('rules must not map facts')):
            result=prepare_document_sources(self.service,'p',[self.doc])
        self.assertEqual(result['data']['facts_written'],0)
        self.assertEqual(self.service.get_document('p',self.doc)['data']['fact_count'],0)
        self.assertIn('营业收入',self.service.get_source_page('p',self.doc,1)['data']['text'])
        self.assertTrue(self.service.get_source_table('p',self.doc)['data']['items'])
        self.assertIn('tables:',self.service.get_document_index('p',self.doc)['data']['index_yaml'])
        self.assertTrue(prepare_document_sources(self.service,'p',[self.doc])['data']['documents'][0]['reused_sources'])

    def test_other_project_and_live_writer_are_rejected_without_side_effect(self):
        with self.assertRaisesRegex(ValueError,'document_not_found_in_project'):prepare_document_sources(self.service,'other',[self.doc])
        self.service.processing_documents[('p',self.doc)]='another-owner'
        with self.assertRaisesRegex(ValueError,'document_processing_active'):prepare_document_sources(self.service,'p',[self.doc])
        self.assertEqual(self.service.processing_documents[('p',self.doc)],'another-owner')

    def test_cancel_releases_only_its_claim_and_does_not_publish_sources(self):
        with self.assertRaises(InterruptedError):prepare_document_sources(self.service,'p',[self.doc],cancelled=lambda:True)
        self.assertNotIn(('p',self.doc),self.service.processing_documents)
        self.assertEqual(self.service.get_document('p',self.doc)['data']['page_count'],0)

    def test_previously_normalized_data_cannot_be_used_as_generic_input(self):
        with self.service.store.connect(write=True) as db:db.execute('INSERT INTO normalization_batches VALUES(?,?,?,?,?)',(self.doc,'batch','processing','{}','now'))
        with self.assertRaisesRegex(ValueError,'baseline_requires_raw_only_documents'):prepare_document_sources(self.service,'p',[self.doc])
        with self.service.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM normalization_batches').fetchone()[0],1)

    def navigation_fixture(self, page_count=123):
        pages=[];tables=[]
        for page in range(1,page_count+1):
            heading=f'第 {page} 页 / '+('RISK 风险披露' if page==23 else '财务附注')
            pages.append({'page':page,'text':heading+'\n原文第二行\n原文第三行\n仅在正文中出现的限定词 BODYONLY',
                          'width':595,'height':842,'printed_page':str(page-1)})
            for ordinal in range(2):
                index=len(tables)
                rows=[['附注明细','本期','上期'],['精确金额','9007199254740993.123456789','-0.000000001'],
                      ['后续原文','123,456.7800','=SUM(B1:B2)']]
                tables.append({'index':index,'page':page,'sheet':f'Sheet{page} {ordinal}',
                               'rows':rows,'bbox':[10,20,500,600],
                               'cells':{'B2':{'text':rows[1][1],'bbox':[30,40,50,60]},
                                        'C3':{'text':rows[2][2],'formula':'=SUM(B1:B2)'}}})
        parsed={'company':'合成索引测试','report_year':2025,'pages':pages,'tables':tables,'warnings':[]}
        self.service._persist_prepared('p',self.doc,parsed)
        self.index_path=Path(self.temp.name)/'indexes'/'p'/'catalog.yaml'
        return parsed

    def test_index_overview_is_bounded_without_rewriting_full_catalog(self):
        self.navigation_fixture()
        before=self.index_path.read_bytes()
        result=self.service.get_document_index('p',self.doc)['data']
        navigation=yaml.safe_load(result['index_yaml'])
        self.assertEqual(result['totals'],{'pages':123,'tables':246})
        self.assertEqual(set(result['pagination']),{'pages','tables'})
        for kind,total in [('pages',123),('tables',246)]:
            self.assertEqual(len(navigation[kind]),40)
            self.assertEqual(result['pagination'][kind],{'total':total,'returned':40,'offset':0,'limit':40,'has_more':True,'next_offset':40})
        self.assertTrue(all(set(item)=={'table_id','page','sheet'} for item in navigation['tables']))
        self.assertTrue(all(set(item)=={'page','heading'} for item in navigation['pages']))
        self.assertEqual(Path(result['index_path']),self.index_path)
        self.assertTrue(Path(result['original_path']).is_file())
        self.assertEqual(before,self.index_path.read_bytes())
        full=yaml.safe_load(before)['documents'][0]
        self.assertEqual(len(full['pages']),123);self.assertEqual(len(full['tables']),246)
        self.assertIn('preview',full['tables'][0])
        self.assertLess(len(result['index_yaml'].encode()),len(yaml.safe_dump(full,allow_unicode=True).encode())//3)

    def test_every_navigation_item_can_be_retrieved_once_in_stable_pages(self):
        self.navigation_fixture()
        full=yaml.safe_load(self.index_path.read_text(encoding='utf8'))['documents'][0]
        for section,key in [('pages','page'),('tables','table_id')]:
            offset=0;seen=[]
            while True:
                result=self.service.get_document_index('p',self.doc,section=section,offset=offset,limit=37)['data']
                items=yaml.safe_load(result['index_yaml'])[section];meta=result['pagination'][section]
                self.assertEqual(set(result['pagination']),{section})
                self.assertNotIn('tables' if section=='pages' else 'pages',yaml.safe_load(result['index_yaml']))
                self.assertEqual(meta['total'],len(full[section]))
                self.assertEqual(meta['returned'],len(items));self.assertLessEqual(len(items),37)
                seen.extend(item[key] for item in items)
                if not meta['has_more']:
                    self.assertIsNone(meta['next_offset']);break
                self.assertEqual(meta['next_offset'],offset+len(items));offset=meta['next_offset']
            self.assertEqual(seen,[item[key] for item in full[section]])
            self.assertEqual(len(set(seen)),len(seen))

    def test_index_filters_compose_and_overview_has_independent_totals(self):
        self.navigation_fixture()
        result=self.service.get_document_index('p',self.doc,query='rIsK',page_start=20,page_end=30,limit=1)['data']
        navigation=yaml.safe_load(result['index_yaml'])
        self.assertEqual([p['page'] for p in navigation['pages']],[23])
        self.assertEqual(result['pagination']['pages']['total'],1)
        self.assertFalse(result['pagination']['pages']['has_more'])
        self.assertEqual(result['pagination']['tables']['total'],2)
        self.assertTrue(result['pagination']['tables']['has_more'])
        self.assertEqual(result['pagination']['tables']['next_offset'],1)
        second=self.service.get_document_index('p',self.doc,section='tables',query='rIsK',page_start=20,page_end=30,limit=1,offset=1)['data']
        self.assertFalse(second['pagination']['tables']['has_more'])
        self.assertNotEqual(navigation['tables'][0]['table_id'],yaml.safe_load(second['index_yaml'])['tables'][0]['table_id'])
        headers=self.service.get_document_index('p',self.doc,section='tables',query='附注明细',page_start=17,page_end=24)['data']
        self.assertEqual(headers['pagination']['tables']['total'],16)
        self.assertTrue(all(17<=t['page']<=24 and 'preview' not in t for t in yaml.safe_load(headers['index_yaml'])['tables']))
        sheet=self.service.get_document_index('p',self.doc,section='tables',query='sHeEt23 风险')['data']
        self.assertEqual([x['page'] for x in yaml.safe_load(sheet['index_yaml'])['tables']],[23,23])
        body=self.service.get_document_index('p',self.doc,query='BODYONLY')['data']
        self.assertEqual(body['pagination']['pages']['total'],0)
        self.assertEqual(body['pagination']['tables']['total'],0)
        self.assertIn('BODYONLY',self.service.get_source_page('p',self.doc,23)['data']['text'])

    def test_preview_is_opt_in_and_source_rows_cells_and_values_remain_exact(self):
        parsed=self.navigation_fixture()
        before=self.index_path.read_bytes()
        result=self.service.get_document_index('p',self.doc,section='tables',page_start=23,page_end=23,include_preview=True)['data']
        items=yaml.safe_load(result['index_yaml'])['tables']
        self.assertEqual(len(items),2)
        for item,table in zip(items,[t for t in parsed['tables'] if t['page']==23]):
            self.assertEqual(item['preview'],table['rows'][:2])
            actual=self.service.get_source_table('p',self.doc,item['table_id'])['data']['items'][0]
            for field in ['rows','cells','bbox','page','sheet']:self.assertEqual(actual[field],table[field])
            self.assertEqual([r['row'] for r in actual['row_source_refs']],[1,2,3])
        self.assertEqual(self.service.get_source_page('p',self.doc,23)['data']['text'],parsed['pages'][22]['text'])
        self.assertEqual(before,self.index_path.read_bytes())
        self.assertEqual(self.service.get_document('p',self.doc)['data']['fact_count'],0)

    def test_navigation_bounds_empty_pages_and_project_ownership(self):
        self.navigation_fixture()
        bounded=self.service.get_document_index('p',self.doc,section='tables',limit=10000,offset=-5)['data']
        self.assertEqual(bounded['pagination']['tables']['limit'],100)
        self.assertEqual(bounded['pagination']['tables']['returned'],100)
        self.assertEqual(bounded['pagination']['tables']['offset'],0)
        empty=self.service.get_document_index('p',self.doc,section='pages',offset=1000)['data']
        self.assertEqual(yaml.safe_load(empty['index_yaml'])['pages'],[])
        self.assertEqual(empty['pagination']['pages']['total'],123)
        self.assertFalse(empty['pagination']['pages']['has_more'])
        self.assertIsNone(empty['pagination']['pages']['next_offset'])
        before=self.index_path.read_bytes()
        for kwargs in [{'section':'all'},{'page_start':0},{'page_end':-1},{'page_start':3,'page_end':2}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.service.get_document_index('p',self.doc,**kwargs)
        with self.assertRaisesRegex(ValueError,'document_not_found_in_project'):
            self.service.get_document_index('other',self.doc,section='tables',query='9007199254740993',include_preview=True)
        with self.assertRaisesRegex(ValueError,'document_not_found_in_project'):
            self.service.get_document_index('p','../../other',section='pages')
        self.assertEqual(before,self.index_path.read_bytes())
        self.assertFalse((Path(self.temp.name)/'indexes'/'other').exists())


class NavigationMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_tool_schema_and_filtered_navigation_roundtrip(self):
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as root:
            params=StdioServerParameters(command=sys.executable,args=['-m','service.server'],
                                        cwd=str(Path(__file__).resolve().parents[2]),env={**os.environ,'FINANCE_DATA_DIR':root})
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    await session.initialize()
                    tool=next(t for t in (await session.list_tools()).tools if t.name=='get_document_index')
                    schema=tool.inputSchema['properties']
                    self.assertEqual(schema['section']['enum'],['overview','pages','tables'])
                    self.assertEqual(schema['limit']['default'],40)
                    self.assertFalse(schema['include_preview']['default'])
                    saved=next(t for t in json.loads((Path(__file__).resolve().parents[1]/'tool-schema.json').read_text(encoding='utf8')) if t['name']=='get_document_index')
                    self.assertEqual(saved['inputSchema'],tool.inputSchema)
                    self.assertEqual(saved['description'],tool.description)
                    await session.call_tool('create_project',{'project_id':'nav','name':'navigation'})
                    source=Path(root)/'uploads'/'source.csv'
                    source.write_text('项目,2025年\n精确金额,9007199254740993.123456789\n',encoding='utf8')
                    registered=await session.call_tool('register_document',{'project_id':'nav','path':str(source),'original_name':'source.csv'})
                    doc=registered.structuredContent['data']['document_id']
                    prepared=await session.call_tool('prepare_document_sources',{'project_id':'nav','document_ids':[doc]})
                    self.assertEqual(prepared.structuredContent['data']['facts_written'],0)
                    args={'project_id':'nav','document_id':doc,'section':'tables','query':'精确金额','page_start':1,'page_end':1,'offset':0,'limit':1}
                    result=(await session.call_tool('get_document_index',args)).structuredContent['data']
                    nav=yaml.safe_load(result['index_yaml'])
                    self.assertEqual(result['pagination']['tables']['total'],1)
                    self.assertNotIn('preview',nav['tables'][0])
                    full=(await session.call_tool('get_document_index',{**args,'include_preview':True})).structuredContent['data']
                    self.assertEqual(yaml.safe_load(full['index_yaml'])['tables'][0]['preview'][1][1],'9007199254740993.123456789')
                    denied=(await session.call_tool('get_document_index',{**args,'project_id':'foreign'})).structuredContent
                    self.assertEqual(denied['status'],'error')

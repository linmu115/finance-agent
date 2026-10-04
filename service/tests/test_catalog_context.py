import unittest
from service.semantic import related_catalog

class CatalogContextTests(unittest.TestCase):
    def test_relevance_keeps_names_without_rewriting_or_limiting_source(self):
        entries=[{'metric':f'unrelated_{i}','label':f'其他项目{i}'} for i in range(500)]+[{'metric':'trade_receivables','label':'应收账款'},{'metric':'service_sales','label':'技术服务收入'}]
        text='某公司 本表 应收账款 123.456 技术服务收入 789.01'
        selected=related_catalog(entries,text)
        self.assertLessEqual(len(selected),32)
        self.assertIn(entries[-1],selected);self.assertIn(entries[-2],selected)
        self.assertEqual(text,'某公司 本表 应收账款 123.456 技术服务收入 789.01')
        self.assertEqual(len(entries),502)
    def test_small_catalog_unchanged_and_large_selection_deterministic(self):
        values=[{'metric':'a','label':'收入'},{'metric':'b','label':'成本'}]
        self.assertEqual(related_catalog(values,'其他'),values)
        many=[{'metric':f'm{i:03}','label':'成本项目'} for i in range(50)]
        self.assertEqual(related_catalog(many,'成本项目'),related_catalog(list(reversed(many)),'成本项目'))

if __name__=='__main__':unittest.main()

"""Period-boundary regressions use source tables, never benchmark labels/predictions."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import unittest

from service.parser import extract_facts


def parsed_tables(tables):
    return {'kind':'.pdf','pages':[{'page':n,'text':'主要会计数据 单位：元 币种：人民币'}
                                  for n in sorted({t['page'] for t in tables})],
            'tables':[{'index':i,'cells':{},**t} for i,t in enumerate(tables)]}


class PeriodBoundaryTests(unittest.TestCase):
    def test_explicit_subannual_headers_cannot_inherit_prior_years(self):
        for headers in [
            ['第一季度\n（1-3月份）','第二季度（4-6月份）'],
            ['2024年第一季度','2023年第一季度'],
            ['2024年1-6月','2023年1-6月'],
            ['2024年上半年','2023年上半年'],
            ['2024年半年','2023年半年'],
            ['2024年6月','2023年6月'],
            ['2024 Q1','2023 Q1'],
            ['2024 H1','2023 H1'],
            ['Six months ended 2024','Six months ended 2023'],
            ['2024/06/30','2023/06/30'],
        ]:
            with self.subTest(headers=headers):
                data=parsed_tables([
                    {'page':1,'rows':[['指标','2024年','2023年'],['营业收入','100','90']]},
                    {'page':2,'rows':[['指标',*headers],['营业收入','31','29']]},
                    {'page':2,'rows':[['营业收入','17','16']]},
                    {'page':3,'rows':[['指标','2024年','2023年'],['营业收入','100','90']]},
                ])
                before=deepcopy(data)
                facts=extract_facts(data,'sample')
                self.assertEqual({f['source']['page'] for f in facts},{1,3})
                self.assertEqual(len(facts),4)
                self.assertEqual(data,before,'Raw source tables must remain available unchanged')

    def test_second_header_row_cannot_reuse_year_only_top_row(self):
        data=parsed_tables([{'page':1,'rows':[['指标','2024','2023'],['','上半年','上半年'],['营业收入','30','25']]}])
        self.assertEqual(extract_facts(data,'sample'),[])

    def test_genuine_continuation_uses_geometry_not_inserted_empty_columns(self):
        data=parsed_tables([
            {'page':1,'rows':[['指标','','2024年','2023年'],['营业收入','','100','90']],
             'column_centers':{0:40,1:100,2:180,3:280}},
            {'page':2,'rows':[['总资产','250','230']],
             'column_centers':{0:40,1:180,2:280}},
        ])
        facts=[f for f in extract_facts(data,'sample') if f['source']['page']==2]
        self.assertEqual([(f['year'],f['value'],f['period']) for f in facts],
                         [(2024,'250','2024-12-31'),(2023,'230','2023-12-31')])

    def test_annual_end_dates_and_full_year_month_span_are_not_blocked(self):
        for headers in [('2024年12月31日','2023年12月31日'),('2024-12-31','2023-12-31'),
                        ('2024年1-12月','2023年1-12月')]:
            with self.subTest(headers=headers):
                data=parsed_tables([{'page':1,'rows':[['指标',*headers],['总资产','250','230']]}])
                self.assertEqual(len(extract_facts(data,'sample')),2)


class RealYiliSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fitz
        path=Path(__file__).resolve().parents[2]/'benchmark/sources/reports/yili_2024.pdf'
        if not path.exists():raise unittest.SkipTest('Original Yili PDF unavailable')
        pages=[];tables=[]
        with fitz.open(path) as pdf:
            for number in [7,8,87,88]:
                page=pdf[number-1]
                pages.append({'page':number,'text':page.get_text('text',sort=True)})
                for table in page.find_tables().tables:
                    centers={}
                    for row in table.rows:
                        for col,rect in enumerate(row.cells):
                            if rect is not None:centers.setdefault(col,(rect[0]+rect[2])/2)
                    tables.append({'page':number,'index':len(tables),'rows':[
                        ['' if cell is None else str(cell) for cell in row] for row in table.extract()],
                        'cells':{},'column_centers':centers})
        cls.parsed={'kind':'.pdf','pages':pages,'tables':tables}

    def test_quarterly_table_is_preserved_but_has_no_annual_facts(self):
        before=deepcopy(self.parsed)
        facts=extract_facts(self.parsed,'yili-source-test')
        quarter=next(t for t in self.parsed['tables'] if t['page']==8 and '第一季度' in ''.join(t['rows'][0]))
        self.assertIn('27,232,860,611.05',quarter['rows'][1])
        self.assertFalse(any(f['source']['table_id']==f"yili-source-test:t{quarter['index']}" for f in facts))
        self.assertEqual(self.parsed,before)
        annual=next(t for t in self.parsed['tables'] if t['page']==7 and t['rows'][0][0]=='主要会计数据')
        expected={('revenue',2024):annual['rows'][1][1],('revenue',2023):annual['rows'][1][2],
                  ('net_profit_parent',2024):annual['rows'][2][1],('net_profit_parent',2023):annual['rows'][2][2],
                  ('operating_cash_flow',2024):annual['rows'][4][1],('operating_cash_flow',2023):annual['rows'][4][2],
                  ('equity_parent',2024):annual['rows'][6][1],('equity_parent',2023):annual['rows'][6][2],
                  ('assets',2024):annual['rows'][7][1],('assets',2023):annual['rows'][7][2]}
        actual={(f['metric'],f['year']):f['value'] for f in facts if f['source']['page']==7}
        for key,value in expected.items():self.assertEqual(Decimal(actual[key]),Decimal(value.replace(',','')))

    def test_real_annual_year_map_survives_into_next_page(self):
        # Exercise actual p87/p88 geometry/rows. The continuation omits its unit;
        # supply the source table's explicitly printed p87 unit in test context
        # to isolate year inheritance from the pre-existing unit propagation rule.
        data=deepcopy(self.parsed)
        data['tables']=[t for t in data['tables'] if t['page'] in {87,88}]
        continuation=next(p for p in data['pages'] if p['page']==88)
        continuation['text']='单位：元\n'+continuation['text']
        facts=[f for f in extract_facts(data,'yili-continuation') if f['source']['page']==88]
        self.assertEqual({(f['metric'],f['year']) for f in facts},
                         {('liabilities',2024),('liabilities',2023),('equity_parent',2024),('equity_parent',2023)})
        self.assertTrue(all(f['period']==f"{f['year']}-12-31" for f in facts))


if __name__=='__main__':unittest.main()

"""Constructed mechanism cases, independent of evaluation subjects/answers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from service.core import FinanceService
from service.financial_workpapers import Statement, statement_analysis, financial_workpaper, WorkpaperInputError
from service.workpaper_period_selection import canonical_period


class WorkpaperInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.s = FinanceService(self.tmp.name); self.s.create_project('p', 'constructed development')
        self.facts = json.loads((Path(__file__).parent / 'fixtures/workpapers/carote.json').read_text('utf-8'))
        for r in self.facts: r.update(company='样例集团', project_id='p', document_id='d')

    def document(self, did='d', company='样例集团'):
        with self.s.store.connect(write=True) as db:
            db.execute('INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,company,report_year,state,parser_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (did, 'p', '样例2024年度报告.pdf', did, 'unused.pdf', 'application/pdf', company, 2024, 'parsed', 'test', 'now'))

    def original_tables(self, unit='单位：元 币种：人民币', restated=False):
        self.document()
        rows = [['项目', '2024年度', '2023年度'], ['营业收入', '120', '100'], ['营业成本', '80', '70'],
                ['营业利润', '25', '20'], ['利润总额', '24', '19'], ['所得税费用', '4', '3'],
                ['净利润', '20', '16'], ['归属于母公司股东的净利润', '19', '15'], ['少数股东损益', '1', '1']]
        if restated:
            rows[0] = ['项目', '2024年度', '2023年度（调整前）', '2023年度（调整后）']
            for r in rows[1:]: r.append(r[-1])
            rows[1][-1] = '105'
        with self.s.store.connect(write=True) as db:
            page = '样例集团2024年年度报告\n企业会计准则\n合并利润表\n2024年1月1日至12月31日\n' + unit + '\n' + '\n'.join(' | '.join(r) for r in rows)
            db.execute('INSERT INTO pages(document_id,page,text) VALUES(?,?,?)', ('d', 1, page))
            db.execute('INSERT INTO source_tables VALUES(?,?,?,?,?,?,?)', ('d:t0', 'd', 1, None, '[]', json.dumps(rows, ensure_ascii=False), '{}'))

    def test_profile_selects_issuer_not_counterparty_in_same_report(self):
        self.document()
        other = copy.deepcopy(self.facts)
        for r in other: r['company'] = '联营主体'
        st = Statement(self.s, 'p', self.facts + other, document_id='d')
        self.assertEqual(st.company, '样例集团')
        self.assertEqual({r['company'] for r in st.facts}, {'样例集团'})
        self.assertIn('document_report_subject', [b['rule'] for b in st.selection['basis']])

    def test_group_scope_precedes_parent_and_never_sums_them(self):
        parent = copy.deepcopy(self.facts)
        for r in parent: r.update(scope='parent_IFRS', company='母公司报表主体')
        st = Statement(self.s, 'p', self.facts + parent)
        self.assertEqual(st.company, '样例集团')
        self.assertEqual(st.pick('revenue', '2025-H1', 'income')['value'], '836925000')

    def test_ah_dual_framework_returns_executable_candidates(self):
        other = copy.deepcopy(self.facts)
        for r in other: r['scope'] = 'consolidated_CAS'
        with self.assertRaises(WorkpaperInputError) as cm: Statement(self.s, 'p', self.facts + other)
        choices = cm.exception.selection['candidates']
        self.assertEqual({c['scope'] for c in choices}, {'consolidated_IFRS', 'consolidated_CAS'})
        for c in choices:
            args = c['retry']['arguments']; self.assertTrue(args['periods']); self.assertTrue(c['retry']['call'])
            st = Statement(self.s, 'p', self.facts + other, args['scope'], args['periods'])
            self.assertEqual({r['scope'] for r in st.facts}, {c['scope']})

    def test_ambiguous_companies_preserve_counts_and_periods(self):
        other = copy.deepcopy(self.facts)
        for r in other: r.update(company='第二主体', document_id='e')
        with self.assertRaises(WorkpaperInputError) as cm: Statement(self.s, 'p', self.facts + other)
        self.assertEqual(len(cm.exception.selection['candidates']), 2)
        self.assertTrue(all(c['fact_count'] == len(self.facts) for c in cm.exception.selection['candidates']))

    def test_zero_fact_partial_report_is_directly_usable(self):
        self.original_tables()
        report, records = statement_analysis(self.s, 'p', document_id='d')
        st = Statement(self.s, 'p', [], document_id='d')
        revenue = st.pick('revenue', '2024-FY', 'income')
        self.assertEqual(revenue['value'], '120')
        self.assertEqual(revenue['source_ref']['source_method'], '原表直读')
        self.assertEqual((revenue['source_ref']['page'], revenue['source_ref']['row'], revenue['source_ref']['column']), (1, 2, 2))
        self.assertTrue(any(r['reason'] for r in report['tables']['missing']['rows']))
        with self.s.store.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0], 0)

    def test_missing_unit_is_local_gap_not_guess_or_zero(self):
        self.original_tables(unit='金额单位未说明')
        with self.assertRaises(WorkpaperInputError) as cm: Statement(self.s, 'p', [], document_id='d')
        self.assertTrue(any('单位' in g['reason'] for g in cm.exception.selection['source_gaps']))

    def test_restated_comparative_selected_and_both_columns_retained(self):
        self.original_tables(restated=True)
        st = Statement(self.s, 'p', [], document_id='d')
        r = st.pick('revenue', '2023-FY', 'income')
        self.assertEqual(r['value'], '105')
        self.assertEqual(r['source_ref']['normalization']['restatement'], 'restated')
        self.assertEqual({r['value'] for r in st.facts if r['metric']=='revenue' and r['period']=='2023-FY'}, {'100', '105'})

    def test_nonstandard_window_and_unknown_row_do_not_block_other_rows(self):
        for r in self.facts:
            if r['period']=='2025-H1': r['period']='截至本报告期止六个月'
        unknown = copy.deepcopy(self.facts[0]); unknown['metric'] = 'unrecognized_item'; unknown['period'] = '待定位'
        unknown['source_ref']['normalization'].update(period_start='', period_end='')
        st = Statement(self.s, 'p', self.facts + [unknown])
        self.assertEqual(st.periods[0], '2025-H1')
        self.assertTrue(any(r['source_ref']['normalization'].get('period_error') for r in st.facts))
        self.assertEqual(canonical_period('2024年1月1日至2024年6月30日'), '2024-H1')
        self.assertEqual(canonical_period('2023年度（调整后）'), '2023-FY')
        self.assertEqual(canonical_period('2024年1至6月'), '2024-H1')

    def test_paired_restatement_header_inherits_shared_year_only(self):
        self.original_tables(restated=True)
        with self.s.store.connect(write=True) as db:
            rows=json.loads(db.execute('SELECT rows_json FROM source_tables').fetchone()[0])
            rows[0][-1]='调整后'
            db.execute('UPDATE source_tables SET rows_json=?',(json.dumps(rows,ensure_ascii=False),))
        st=Statement(self.s,'p',[],document_id='d')
        self.assertEqual(st.pick('revenue','2023-FY','income')['value'],'105')

    def test_bad_structured_flow_date_is_recovered_from_original_header(self):
        self.original_tables()
        st=Statement(self.s,'p',[],document_id='d')
        bad=copy.deepcopy(st.pick('revenue','2024-FY','income'))
        bad.update(period='2024-12-31',quality='structured')
        bad['source_ref']['normalization'].update(period_start='',period_end='2024-12-31')
        recovered=Statement(self.s,'p',[bad],document_id='d')
        self.assertEqual(recovered.pick('revenue','2024-FY','income')['value'],'120')
        self.assertTrue(any('期间起点' in gap['reason'] for gap in recovered.source_gaps))

    def test_pipeline_ambiguity_context_keeps_actionable_retry(self):
        other=copy.deepcopy(self.facts)
        for r in other:r.update(company='第二主体',document_id='e')
        with patch('service.financial_workpapers.load_facts',return_value=self.facts+other):
            result=self.s.financial_workpaper('p','analysis_pipeline')
        context=result['data']['context']
        self.assertEqual(context['status'],'selection_required')
        self.assertEqual(context['selection']['retry_calls'][0]['arguments']['kind'],'analysis_pipeline')

    def test_unavailable_period_retry_is_callable(self):
        with patch('service.financial_workpapers.load_facts', return_value=self.facts):
            result = self.s.financial_workpaper('p', periods='2030年')
        self.assertEqual(result['status'], 'insufficient_evidence')
        args = result['data']['selection']['retry_calls'][0]['arguments']
        with patch('service.financial_workpapers.load_facts', return_value=self.facts):
            retried = self.s.financial_workpaper(**args)
        self.assertEqual(retried['status'], 'ok')

    def test_pipeline_a1_handle_pagination_and_project_isolation(self):
        with patch('service.financial_workpapers.load_facts', return_value=self.facts):
            data = financial_workpaper(self.s, 'p', 'analysis_pipeline')
        context = data['context']; self.assertTrue(context['key_metrics']); self.assertTrue(context['missing'])
        self.assertEqual(context['extensions']['management_evidence'], 'pending')
        response = financial_workpaper(self.s, 'p', 'read_table', read={'handle': data['handle'], 'table': 'variance_profit_bridge', 'limit': 2})
        self.assertEqual(len(response['table_data']['rows']), 2); self.assertEqual(response['next_offset'], 2)
        self.assertEqual(response['table_data']['rows'], data['numeric_tables']['variance_profit_bridge']['rows'][:2])
        self.s.create_project('other', 'other')
        with self.assertRaises(WorkpaperInputError): financial_workpaper(self.s, 'other', 'read_table', read={'handle': data['handle'], 'table': 'variance_profit_bridge'})
        with self.assertRaises(WorkpaperInputError): financial_workpaper(self.s, 'p', 'read_table', read={'handle': '../outside', 'table': 'variance_profit_bridge'})

    def test_same_document_framework_evidence_corrects_view_without_mutation(self):
        self.original_tables()
        original=Statement(self.s,'p',[],document_id='d').facts
        existing=[r for r in original if r['metric']!='revenue']
        for r in existing:r['scope']='consolidated_IFRS'
        before=copy.deepcopy(existing)
        st=Statement(self.s,'p',existing,document_id='d')
        self.assertEqual({r['scope'] for r in st.facts},{'consolidated_CAS'})
        self.assertEqual(existing,before)
        self.assertTrue(any(b['rule']=='report_framework_over_record_annotation' for b in st.selection['basis']))
        with self.assertRaises(WorkpaperInputError):Statement(self.s,'p',existing,'consolidated_IFRS',document_id='d')

    def test_handle_respects_evaluation_isolation_and_hides_ownership(self):
        from service.evaluation_isolation import isolation_key
        token=isolation_key.set('a')
        try:
            with patch('service.financial_workpapers.load_facts',return_value=self.facts):
                data=financial_workpaper(self.s,'p','analysis_pipeline')
            args={'handle':data['handle'],'table':'statement_income'}
            self.assertTrue(financial_workpaper(self.s,'p','read_table',read=args)['table_data']['rows'])
        finally:isolation_key.reset(token)
        token=isolation_key.set('b')
        try:
            errors=[]
            for handle in (data['handle'],'0'*32):
                with self.assertRaises(WorkpaperInputError) as cm:financial_workpaper(self.s,'p','read_table',read=args|{'handle':handle})
                errors.append(str(cm.exception))
            self.assertEqual(errors[0],errors[1])
        finally:isolation_key.reset(token)

    def test_merged_cell_geometry_reads_original_spans_not_row_order(self):
        from service.workpaper_table_geometry import geometry_rows
        words=[{'text':text,'bbox':box} for text,box in [('Revenue',[0,0,40,10]),('Cost',[0,20,14,30]),
            ('of',[16,20,24,30]),('sales',[26,20,48,30]),('100',[60,0,90,10]),('70',[60,20,90,30])]]
        t={'index':0,'page':1,'rows':[['Revenue\nCost of sales','100\n70']],
           'cells':{'A1':{'bbox':[0,0,50,35]},'B1':{'bbox':[50,0,100,35]}}}
        parsed={'pages':[{'page':1,'words':words}]};schema={'columns_json':json.dumps([{'column':2,'period':'2024-FY'}])}
        rows=geometry_rows(parsed,t,schema);cs=json.loads(rows[0]['attributes']['columns_json'])
        self.assertEqual([(c['metric'],c['numeric_span']['text']) for c in cs],[('revenue','100'),('cost_of_revenue','70')])
        # Move the second amount outside the label line: it must not be guessed.
        words[-1]['bbox']=[60,32,90,42]
        cs=json.loads(geometry_rows(parsed,t,schema)[0]['attributes']['columns_json'])
        self.assertEqual([c['numeric_span']['text'] for c in cs],['100'])


if __name__ == '__main__': unittest.main()

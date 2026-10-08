"""F2.1 language rules: actual gate source pages and non-company templates."""
import json
from pathlib import Path
import unittest

from service.workpaper_basis import scan_basis_markers


class BasisMarkerTests(unittest.TestCase):
    def scan(self,text):
        return scan_basis_markers({1:text},'constructed')

    def test_gate_original_pages(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/f21_basis_marker_pages.json').read_text('utf-8'))
        rows=scan_basis_markers({int(k):v for k,v in fixture['pages'].items()},fixture['document_id'])
        merger=[r for r in rows if r['source']['page']==12 and '公司完成对于物流业务的并表' in r['quote']]
        self.assertEqual({(r['kind'],r['status']) for r in merger},
                         {('common_control','change_disclosed'),('restatement','restatement_disclosed')})
        self.assertTrue(all('报告期内' in r['quote'] and '进行了重述' in r['quote'] for r in merger))
        for page in (94,163):
            with self.subTest(page=page):
                policy=[r for r in rows if r['source']['page']==page and '保证类质保费用计入' in r['quote']]
                self.assertTrue(policy)
                self.assertEqual({(r['kind'],r['status']) for r in policy},{('accounting_policy','change_disclosed')})
                restatement=[r for r in rows if r['source']['page']==page and r['kind']=='restatement']
                self.assertTrue(restatement)
                self.assertTrue(all(r['status']=='restatement_disclosed' for r in restatement))
                self.assertTrue(all(r['source']['document_id']==fixture['document_id'] for r in policy))
        estimates=[r for r in rows if r['kind']=='accounting_estimate']
        self.assertTrue(estimates)
        self.assertTrue(all(r['status']=='unclassified' and '保证类' not in r['quote'] for r in estimates))

    def test_completion_applies_to_every_kind_and_keeps_quote(self):
        examples={
            'accounting_policy':'报告期内，本公司已执行新的会计政策变更。',
            'accounting_estimate':'本期已完成会计估计变更。',
            'prior_error':'报告期内，本公司完成前期差错更正。',
            'common_control':'报告期内，公司通过同一控制下企业合并将子公司纳入合并范围。',
            'restatement':'本公司已对前期财务报表进行追溯重述。',
        }
        for kind,quote in examples.items():
            with self.subTest(kind=kind):
                rows=self.scan(quote)
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['kind'],kind)
                self.assertEqual(rows[0]['status'],'restatement_disclosed' if kind=='restatement' else 'change_disclosed')
                self.assertEqual(rows[0]['quote'],quote)
                self.assertIn('原文明确执行/完成',rows[0]['reason'])

    def test_policy_cues_do_not_invent_estimate_changes(self):
        for quote in ('本期公司完成重分类。','本公司已执行《企业会计准则第99号》。',
                      '本公司已按《企业会计准则解释第十八号》调整相关报表。'):
            with self.subTest(quote=quote):
                rows=self.scan(quote)
                self.assertTrue(rows)
                self.assertEqual({r['kind'] for r in rows},{'accounting_policy'})
                self.assertTrue(all(r['status']=='change_disclosed' for r in rows))
        rows=self.scan('报告期内，本公司已完成会计估计变更，调整折旧年限。')
        self.assertEqual(rows[0]['kind'],'accounting_estimate')

    def test_templates_conditional_and_future_remain_unclassified(self):
        examples=(
            '会计政策变更 □适用 □不适用。',
            '公司对会计政策、会计估计变更原因及影响的分析说明 √适用 □不适用。',
            '本期发生同一控制下企业合并的，被合并方合并前净利润为：0元。',
            '在报告期内，若因同一控制下企业合并增加子公司，则将其收入纳入合并利润表。',
            '对于本公司同一控制下企业合并取得的子公司，视同该合并已经发生。',
            '本公司对会计估计的变更仅影响变更当期的，其影响数在变更当期予以确认。',
            '本公司对于已计提减值的资产重分类，按照相应政策处理。',
            '本公司拟完成会计估计变更。',
            '公司本期将于下年度完成同一控制下企业合并。',
            'The Group will adopt a new standard and the comparison will be restated.',
        )
        for quote in examples:
            with self.subTest(quote=quote):
                rows=self.scan(quote)
                self.assertTrue(rows)
                self.assertTrue(all(r['status']=='unclassified' for r in rows),rows)
                self.assertTrue(all(r['reason']=='未自动判定是否本期发生，需对照原文核对' for r in rows))

    def test_not_applicable_is_local_to_heading(self):
        quote='（一）会计估计变更 □适用 √不适用\n（二）会计政策变更 √适用 □不适用\n本期已完成重分类。'
        rows=self.scan(quote)
        self.assertEqual(next(r for r in rows if r['kind']=='accounting_estimate')['status'],'not_applicable')
        self.assertTrue(all(r['status']=='change_disclosed' for r in rows if r['kind']=='accounting_policy'))

    def test_explicit_no_change_does_not_promote_completion(self):
        for quote in ('本期未完成会计估计变更。','本期尚未将同一控制下企业合并对象纳入合并范围。',
                      'The Group has not completed changes in accounting estimates.'):
            with self.subTest(quote=quote):
                rows=self.scan(quote)
                self.assertFalse(any('disclosed' in r['status'] for r in rows))

    def test_zero_impact_does_not_erase_explicit_implementation(self):
        for impact in ('对利润无重大影响','未发生重大影响'):
            rows=self.scan('本期已完成会计政策变更，'+impact+'。')
            self.assertEqual(rows[0]['status'],'change_disclosed')
            self.assertIn(impact,rows[0]['quote'])

    def test_policy_execution_does_not_override_negated_restatement(self):
        rows=self.scan('本期已完成会计政策变更，无需追溯重述。')
        self.assertEqual(rows[0]['status'],'change_disclosed')
        self.assertEqual(rows[1]['status'],'no_impact_or_no_change')
        rows=self.scan('本期已发生会计估计变更。')
        self.assertEqual(rows[0]['status'],'change_disclosed')


if __name__=='__main__':unittest.main()

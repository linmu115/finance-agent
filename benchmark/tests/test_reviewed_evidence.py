import sys,unittest,hashlib,importlib.util,json,tempfile,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluate import score_case
spec=importlib.util.spec_from_file_location('review_builder',Path(__file__).resolve().parents[1]/'scripts/build_reviewed_benchmark.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class ReviewedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.gold={'id':'fixture','track':'finqa_multi','status':'ok','answer':'10','unit':'percentage_points','abs_tolerance':'0.000006','citations':['row1','row2'],'evidence_sets':[['row1','row2'],['direct_change']],'valid_context_citations':['unit_header']}
    def prediction(self,refs):
        return {'id':'fixture','status':'ok','answer':'10','unit':'percentage_points','citations':refs}
    def test_independently_sufficient_sources_and_context(self):
        for refs in [['row1','row2'],['direct_change'],['row1','row2','direct_change','unit_header']]:
            self.assertTrue(score_case(self.prediction(refs),self.gold)['grounded_ok'])
    def test_header_or_one_operand_is_not_sufficient(self):
        for refs in [['unit_header'],['row1'],['invented'],['row1','row2','noise']]:
            self.assertFalse(score_case(self.prediction(refs),self.gold)['grounded_ok'])
    def test_ambiguity_requires_refusal_and_evidence(self):
        self.gold.update(status='insufficient_evidence',answer=None,reason_code='ambiguous_question_or_source')
        correct={'status':'insufficient_evidence','answer':None,'reason_code':'ambiguous_question_or_source','citations':['row1','row2']}
        self.assertTrue(score_case(correct,self.gold)['grounded_ok'])
        self.assertFalse(score_case({**correct,'citations':[]},self.gold)['grounded_ok'])
        self.assertFalse(score_case(self.prediction(['row1','row2']),self.gold)['answer_ok'])

    def test_partial_different_alternatives_do_not_combine(self):
        self.gold['evidence_sets']=[['a1','a2'],['b1','b2']]
        self.assertFalse(score_case(self.prediction(['a1','b2']),self.gold)['grounded_ok'])

    def test_duplicate_and_malformed_citations_fail(self):
        for refs in [['row1','row1','row2'],['row1',None],list(map(str,range(9))),None]:
            with self.subTest(refs=refs):
                self.assertIn('invalid_citation_schema',score_case(self.prediction(refs),self.gold)['errors'])

    def test_invalid_gold_groups_fail_closed(self):
        for groups in [[],[[]],[['row1','row1']],[['row1',None]],['row1']]:
            with self.subTest(groups=groups),self.assertRaises(ValueError):
                score_case(self.prediction(['row1']),{**self.gold,'evidence_sets':groups})

    def test_evidence_sets_do_not_need_legacy_citations_alias(self):
        del self.gold['citations']
        self.assertTrue(score_case(self.prediction(['direct_change']),self.gold)['grounded_ok'])

    def test_v02_explicit_ratio_percent_and_money_conversion(self):
        for target,unit,value,returned_unit in [('10','percent','0.1','ratio'),
                ('0.1','ratio','10','percent'),('2','million_USD','2000000','USD'),
                ('2000','USD','2','thousand_USD')]:
            with self.subTest(unit=unit,returned_unit=returned_unit):
                g={**self.gold,'benchmark_revision':'0.2','answer':target,'unit':unit}
                p={**self.prediction(['direct_change']),'answer':value,'unit':returned_unit}
                self.assertTrue(score_case(p,g)['grounded_ok'])

    def test_units_never_guessed_and_percentage_points_distinct(self):
        self.gold['benchmark_revision']='0.2'
        for value,unit in [('10','percent'),('0.1','ratio'),('10','CNY'),('10',None),('10',[])]:
            p={**self.prediction(['direct_change']),'answer':value,'unit':unit}
            self.assertIn('unit',score_case(p,self.gold)['errors'])
        g={**self.gold,'unit':'percent'}
        self.assertFalse(score_case({**self.prediction(['direct_change']),'answer':'0.1','unit':'percent'},g)['answer_ok'])

    def test_legacy_keeps_exact_unit_and_empty_abstention_rules(self):
        g={**self.gold,'unit':'percent','citations':['row1','row2']}
        g.pop('evidence_sets');g.pop('valid_context_citations')
        p={**self.prediction(['row1','row2']),'answer':'0.1','unit':'ratio'}
        self.assertFalse(score_case(p,g)['answer_ok'])
        g.update(status='insufficient_evidence',answer=None,reason_code='period_not_in_source')
        p={'status':'insufficient_evidence','answer':None,'reason_code':'period_not_in_source','citations':[]}
        self.assertTrue(score_case(p,g)['grounded_ok'])
        self.assertFalse(score_case({**p,'citations':['row1']},g)['grounded_ok'])

    def test_ambiguity_rejects_fabricated_scalar_or_reason(self):
        g={**self.gold,'benchmark_revision':'0.2','status':'insufficient_evidence','answer':None,'reason_code':'ambiguous_question_or_source'}
        p={'status':'insufficient_evidence','answer':None,'reason_code':'ambiguous_question_or_source','citations':['direct_change']}
        for patch in [{'answer':'10'},{'reason_code':'period_not_in_source'},{'status':'ok'}]:
            self.assertFalse(score_case({**p,**patch},g)['answer_ok'])

    def test_rounding_variants_require_their_own_complete_evidence(self):
        g={**self.gold,'benchmark_revision':'0.2','answer':'0.833','unit':'ratio',
           'supported_rounding_variants':[{'canonical_answer':'0.8333333333','answer_unit':'ratio',
               'abs_tolerance':'0.000006','evidence_sets':[['rounded_a','rounded_b']],
               'valid_context_citations':['rounded_header']}]}
        p={**self.prediction(['rounded_a','rounded_b','rounded_header']),'answer':'83.33333333','unit':'percent'}
        result=score_case(p,g)
        self.assertTrue(result['grounded_ok']);self.assertEqual(result['matched_answer_variant'],'rounded_source_1')
        for refs in [['row1','row2'],['rounded_a'],['rounded_header'],[]]:
            with self.subTest(refs=refs):self.assertFalse(score_case({**p,'citations':refs},g)['answer_ok'])
        self.assertFalse(score_case({**p,'answer':'83.5'},g)['answer_ok'])
        self.assertTrue(score_case({**self.prediction(['row1','row2']),'answer':'0.833','unit':'ratio'},g)['grounded_ok'])

    def test_nonfinite_boolean_and_extreme_converted_answers_fail(self):
        g={**self.gold,'benchmark_revision':'0.2','unit':'percent'}
        for value in [True,None,'NaN','Infinity','1e999999999']:
            self.assertFalse(score_case({**self.prediction(['direct_change']),'answer':value,'unit':'ratio'},g)['answer_ok'])

class BuilderValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source.json'
        self.source.write_text(json.dumps({'table':[{'id':'row','cells':['10']}],'text':[{'id':'context','text':'year and unit'}]}),encoding='utf8')
        self.case={'id':'fixture','split':'dev'};self.legacy={'answer':'10'}
        self.review={'id':'fixture','split':'dev','material_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'legacy_answer':'10','label_status':'verified','canonical_answer':'10','answer_unit':'million_USD',
            'abs_tolerance':'0.000006','evidence_sets':[['row']],'valid_context_citations':['context'],
            'rationale':'Source row explicitly states the amount.'}

    def validate(self,review=None):return builder.validate_review(self.case,review or self.review,self.source,self.legacy)

    def test_source_hash_and_legacy_provenance_required(self):
        self.validate()
        for patch in [{'material_sha256':'0'*64},{'legacy_answer':'11'},{'split':'acceptance'},{'rationale':''}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.validate({**self.review,**patch})

    def test_ambiguous_cannot_be_given_scalar_or_variant(self):
        r={**self.review,'label_status':'ambiguous','canonical_answer':None};self.validate(r)
        for patch in [{'canonical_answer':'10'},{'supported_rounding_variants':[{}]}]:
            with self.assertRaises(ValueError):self.validate({**r,**patch})

    def test_invalid_tolerance_and_evidence_rejected(self):
        for patch in [{'abs_tolerance':'NaN'},{'abs_tolerance':'-0.1'},{'rel_tolerance':'0.1'},
                      {'evidence_sets':[['invented']]},{'evidence_sets':[['row','row']]},
                      {'valid_context_citations':['invented']},{'canonical_answer':True}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.validate({**self.review,**patch})

    def test_variants_must_have_explicit_tolerance_and_real_source(self):
        v={'canonical_answer':'10.1','answer_unit':'million_USD','abs_tolerance':'0.000006',
           'evidence_sets':[['row']],'rationale':'Synthetic alternate source figure for validation.'}
        self.validate({**self.review,'supported_rounding_variants':[v]})
        bad=dict(v);bad.pop('abs_tolerance')
        for variant in [bad,{**v,'evidence_sets':[['invented']]},{**v,'abs_tolerance':'-1'}]:
            with self.assertRaises(ValueError):self.validate({**self.review,'supported_rounding_variants':[variant]})

    def test_public_contract_is_global_not_label_dependent(self):
        text=builder.public_contract('percent')
        self.assertIn('percent=10 means 10%',text)
        self.assertIn('absolute difference between 12% and 10%',text)
        self.assertNotIn(self.review['rationale'],text)
        self.assertNotIn('canonical_answer',text)

    def test_builder_preserves_inventory_legacy_and_public_input_boundary(self):
        root=Path(self.temp.name)/'benchmark'
        for folder in ['agent_input','evaluator','review']:(root/folder).mkdir(parents=True)
        material=root/'agent_input/source.json';material.write_bytes(self.source.read_bytes())
        originals=[{'id':identifier,'split':split,'track':track,'question':'Synthetic public question',
                    'allowed_assets':['source.json']} for identifier,split,track in
                   [('fixture','dev','finqa_single'),('uncertain','acceptance','finqa_multi'),('cn','dev','cn_extract')]]
        legacy=[{'id':c['id'],'split':c['split'],'track':c['track'],'status':'ok','answer':'10',
                 'unit':'finqa_execution','citations':['row'],'abs_tolerance':'0.000006'} for c in originals]
        for path,values in [(root/'agent_input/cases.jsonl',originals),(root/'evaluator/gold.jsonl',legacy)]:
            path.write_text(''.join(json.dumps(x)+'\n' for x in values),encoding='utf8')
        legacy_hash=hashlib.sha256((root/'evaluator/gold.jsonl').read_bytes()).hexdigest()
        uncertain={**self.review,'id':'uncertain','split':'acceptance','label_status':'ambiguous',
                   'canonical_answer':None,'rationale':'Source cannot uniquely determine the requested quantity.'}
        reviews=[{'cases':[self.review]},{'items':[uncertain]},[]]
        for name,data in zip(['curation-dev.json','curation-acceptance-a.json','curation-acceptance-b.json'],reviews):
            (root/'review'/name).write_text(json.dumps(data),encoding='utf8')
        oldroot=builder.ROOT
        try:
            builder.ROOT=root
            with contextlib.redirect_stdout(io.StringIO()):builder.main()
        finally:builder.ROOT=oldroot
        public=builder.rows(root/'versions/v0.2/cases.jsonl')
        private=builder.rows(root/'versions/v0.2/gold.jsonl')
        self.assertEqual([x['id'] for x in public],[x['id'] for x in originals])
        self.assertEqual(hashlib.sha256((root/'evaluator/gold.jsonl').read_bytes()).hexdigest(),legacy_hash)
        forbidden={'canonical_answer','label_status','evidence_sets','legacy_answer','reason_code','conditioned_answers'}
        self.assertTrue(all(not forbidden.intersection(case) for case in public))
        self.assertIsNone(private[1]['answer'])
        self.assertEqual(private[1]['reason_code'],'ambiguous_question_or_source')

if __name__=='__main__':unittest.main()

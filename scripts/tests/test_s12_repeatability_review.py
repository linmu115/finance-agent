"""Source-only S12 review probes: synthetic fixtures, no model outputs or labels.

Run after the active benchmark finishes. Failures expose repeatability contract
gaps; this file deliberately does not patch the frozen scorer or runner.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"score_repeatability.py"
spec=importlib.util.spec_from_file_location("s12_review_target",SOURCE)
repeatability=importlib.util.module_from_spec(spec)
spec.loader.exec_module(repeatability)


class ValueValidityTests(unittest.TestCase):
    def setUp(self):
        self.gold={"id":"synthetic","track":"finqa_single","split":"dev",
                   "benchmark_revision":"0.2","status":"ok","answer":"100",
                   "unit":"percent","abs_tolerance":"0.000006","citations":["source:row"]}
        self.valid={"id":"synthetic","status":"ok","answer":"10","unit":"percent",
                    "citations":["source:row"]}

    def test_valid_identical_wrong_value_is_still_consistent(self):
        self.assertTrue(repeatability.same_value(self.valid,self.valid,self.gold))

    def test_explicit_equivalent_units_are_consistent(self):
        self.assertTrue(repeatability.same_value(self.valid,{**self.valid,"answer":"0.1","unit":"ratio"},self.gold))

    def test_failed_and_nonfinite_never_consistent(self):
        for patch in [{"status":"failed"},{"status":"running"},{"answer":"NaN"},{"answer":True}]:
            with self.subTest(patch=patch):
                invalid={**self.valid,**patch}
                self.assertFalse(repeatability.same_value(invalid,invalid,self.gold))

    def test_missing_answer_on_abstention_is_invalid(self):
        invalid={"status":"insufficient_evidence","reason_code":"ambiguous_question_or_source","citations":["source:row"]}
        self.assertFalse(repeatability.same_value(invalid,invalid,self.gold))

    def test_missing_or_unknown_abstention_reason_is_invalid(self):
        for reason in [None,"made_up_reason",4,""]:
            invalid={"status":"insufficient_evidence","answer":None,"citations":["source:row"]}
            if reason is not None:invalid["reason_code"]=reason
            with self.subTest(reason=reason):self.assertFalse(repeatability.same_value(invalid,invalid,self.gold))

    def test_valid_wrong_abstention_is_not_conflated_with_accuracy(self):
        valid={"status":"insufficient_evidence","answer":None,"reason_code":"period_not_in_source","citations":[]}
        self.assertTrue(repeatability.same_value(valid,valid,self.gold))

    def test_required_period_and_scope_must_be_present(self):
        gold={**self.gold,"period":"2024-FY","scope":"consolidated_CAS"}
        for patch in [{},{"period":"2024-FY"},{"scope":"consolidated_CAS"}]:
            invalid={**self.valid,**patch}
            with self.subTest(patch=patch):self.assertFalse(repeatability.same_value(invalid,invalid,gold))

    def test_present_wrong_period_can_still_be_consistent(self):
        gold={**self.gold,"period":"2024-FY","scope":"consolidated_CAS"}
        valid={**self.valid,"period":"2023-FY","scope":"consolidated_CAS"}
        self.assertTrue(repeatability.same_value(valid,valid,gold))

    def test_boolean_audit_requires_its_unit(self):
        gold={**self.gold,"answer":True,"corrected_value":"10","unit":"CNY"}
        invalid={"status":"ok","answer":False,"corrected_value":"9","citations":["source:row"]}
        self.assertFalse(repeatability.same_value(invalid,invalid,gold))

    def test_same_valid_numeric_answer_on_abstention_gold_is_consistent(self):
        ambiguous={key:value for key,value in self.gold.items() if key not in {"abs_tolerance","unit"}}
        ambiguous.update(status="insufficient_evidence",answer=None,reason_code="ambiguous_question_or_source")
        self.assertTrue(repeatability.same_value(self.valid,self.valid,ambiguous))
        self.assertFalse(repeatability.same_value(self.valid,{**self.valid,"answer":"10.000001"},ambiguous))
        invalid={k:v for k,v in self.valid.items() if k!="unit"}
        self.assertFalse(repeatability.same_value(invalid,invalid,ambiguous))


class RoundFileValidityTests(unittest.TestCase):
    def evaluate_fixture(self,rounds):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);run=root/"run";run.mkdir()
            gold_dir=root/"benchmark/versions/v0.2";gold_dir.mkdir(parents=True)
            gold={"id":"synthetic","track":"finqa_single","split":"dev","benchmark_revision":"0.2",
                  "status":"ok","answer":"100","unit":"percent","abs_tolerance":"0.000006","citations":["source:row"]}
            (gold_dir/"gold.jsonl").write_text(json.dumps(gold)+"\n",encoding="utf8")
            (run/"manifest.json").write_text(json.dumps({"repeat":len(rounds),"benchmarkVersion":"0.2","caseIds":["synthetic"]}),encoding="utf8")
            for index,rows in enumerate(rounds,1):
                folder=run/("round-"+str(index));folder.mkdir()
                (folder/"predictions.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows),encoding="utf8")
            old=repeatability.ROOT
            try:
                repeatability.ROOT=root
                return repeatability.evaluate(run)
            finally:repeatability.ROOT=old

    def prediction(self,answer="10",**extra):
        return {"id":"synthetic","status":"ok","answer":answer,"unit":"percent","citations":["source:row"],**extra}

    def test_all_rounds_fit_pairwise_tolerance(self):
        result=self.evaluate_fixture([[self.prediction("10")],[self.prediction("10.000006")],[self.prediction("9.999994")]])
        self.assertEqual(result["numericConclusionConsistency"],0)

    def test_failed_empty_citations_are_not_evidence_consistency(self):
        failed=self.prediction(None,status="failed",citations=[])
        result=self.evaluate_fixture([[failed],[failed],[failed]])
        self.assertEqual(result["numericConclusionConsistency"],0)
        self.assertEqual(result["citationSetConsistency"],0)

    def test_duplicate_ids_cannot_be_silently_overwritten(self):
        duplicate=[self.prediction("5"),self.prediction("10")]
        try:result=self.evaluate_fixture([duplicate,duplicate,duplicate])
        except ValueError:return
        self.assertTrue(result.get("protocol_errors") or result["numericConclusionConsistency"]==0)

    def test_unknown_ids_are_protocol_errors(self):
        entries=[self.prediction(),self.prediction(id="unexpected")]
        try:result=self.evaluate_fixture([entries,entries,entries])
        except ValueError:return
        self.assertTrue(result.get("protocol_errors") or result["numericConclusionConsistency"]==0)

    def test_malformed_citations_fail_without_type_error(self):
        for citations in [None,["source:row",3],["source:row","source:row"]]:
            with self.subTest(citations=citations):
                invalid=self.prediction(citations=citations)
                try:result=self.evaluate_fixture([[invalid],[invalid],[invalid]])
                except ValueError:continue
                self.assertEqual(result["numericConclusionConsistency"],0)
                self.assertEqual(result["citationSetConsistency"],0)


if __name__=="__main__":unittest.main()

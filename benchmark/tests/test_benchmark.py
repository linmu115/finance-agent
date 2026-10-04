import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluate import evaluate,numeric_equal,read_jsonl,score_case
from prepare_case import prepare
sys.path.insert(0,str(ROOT/"scripts"))
from build_benchmark import execute_finqa

class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold=read_jsonl(ROOT/"evaluator/gold.jsonl");cls.cases=read_jsonl(ROOT/"agent_input/cases.jsonl")
    def oracle(self):
        return [{k:v for k,v in g.items() if k in ["id","status","answer","corrected_value","unit","period","scope","citations","reason_code"]} for g in self.gold]
    def test_oracle_is_only_an_evaluator_selftest(self):
        report=evaluate(self.oracle(),self.gold,"all")
        self.assertTrue(report["dataset_gate_pass"]);self.assertFalse(report["full_system_acceptance"])
    def test_empty_submission_fails(self):
        result=evaluate([],self.gold,"acceptance");self.assertFalse(result["dataset_gate_pass"]);self.assertEqual(result["evaluated_cases"],124)
    def test_duplicate_and_unknown_ids_fail(self):
        good=self.oracle();self.assertFalse(evaluate(good+[good[0]],self.gold,"all")["dataset_gate_pass"])
        self.assertFalse(evaluate(good+[{"id":"unknown"}],self.gold,"all")["dataset_gate_pass"])
    def test_unit_factor_error_and_wrong_period_fail(self):
        g=next(g for g in self.gold if g["id"]=="midea_2024_extract_revenue_2024");p=copy.deepcopy(g)
        p["answer"]=str(Decimal(g["answer"])/1000);self.assertFalse(score_case(p,g)["answer_ok"])
        p=copy.deepcopy(g);p["period"]="2023-FY";self.assertFalse(score_case(p,g)["answer_ok"])
        p=copy.deepcopy(g);p["scope"]="IFRS";self.assertFalse(score_case(p,g)["answer_ok"])
    def test_correct_number_without_evidence_fails_grounding(self):
        g=self.gold[0];p=copy.deepcopy(g);p["citations"]=["invented:p999"]
        result=score_case(p,g);self.assertTrue(result["answer_ok"]);self.assertFalse(result["grounded_ok"])
    def test_audit_requires_boolean_and_correction(self):
        g=next(g for g in self.gold if g["track"]=="cn_audit");p=copy.deepcopy(g);p.pop("corrected_value")
        self.assertFalse(score_case(p,g)["answer_ok"])
    def test_missing_evidence_must_not_invent_value(self):
        g=next(g for g in self.gold if g["track"]=="cn_abstain");p=copy.deepcopy(g);p["answer"]="123"
        self.assertFalse(score_case(p,g)["answer_ok"])
    def test_reject_nan_infinity_bool_and_percent_guessing(self):
        for val in ["NaN","Infinity",True,"9.44%",None]: self.assertFalse(numeric_equal(val,"9.44","0.005"))
        self.assertFalse(numeric_equal("0.0944","9.44","0.005"));self.assertTrue(numeric_equal("9.4401","9.44","0.005"))
    def test_inputs_have_no_label_fields(self):
        forbidden={"qa","qa_0","qa_1","gold_inds","exe_ans","program","model_input","table_retrieved","text_retrieved","answer","gold"}
        def walk(x):
            if isinstance(x,dict):
                self.assertFalse(set(x)&forbidden)
                for y in x.values():walk(y)
            elif isinstance(x,list):
                for y in x:walk(y)
        for p in (ROOT/"agent_input/finqa").glob("*.json"):walk(json.loads(p.read_text(encoding="utf-8")))
    def test_companies_disjoint_and_ids_unique(self):
        groups={s:{r["group_id"] for r in self.cases if r["split"]==s} for s in ["dev","acceptance"]}
        self.assertFalse(groups["dev"]&groups["acceptance"])
        self.assertEqual(len(self.cases),len({r["id"] for r in self.cases}))
        self.assertEqual({r["id"] for r in self.cases},{r["id"] for r in self.gold})
    def test_source_hashes_and_reference_database(self):
        for row in json.loads((ROOT/"sources/manifest.json").read_text(encoding="utf-8")):
            self.assertEqual(hashlib.sha256((ROOT/row["path"]).read_bytes()).hexdigest(),row["sha256"])
        for relative,digest in json.loads((ROOT/"dataset_lock.json").read_text(encoding="utf-8")).items():
            self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),digest)
        con=sqlite3.connect(ROOT/"evaluator/reference.sqlite")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM facts").fetchone()[0],30)
        self.assertEqual(con.execute("SELECT value_cny FROM facts WHERE fact_id=?",("midea_2024:revenue:2024",)).fetchone()[0],"407149600000")
        con.close()
    def test_each_selected_finqa_program_recomputes_gold(self):
        for g in self.gold:
            if g["track"].startswith("finqa"):
                value,_=execute_finqa(g["program"]);self.assertTrue(numeric_equal(str(value),g["answer"],g["abs_tolerance"]))
    def test_ocr_package_cannot_see_pdf_or_gold(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"one";prepare("midea_2024_ocr_revenue",dest)
            files=[p.suffix for p in dest.rglob("*") if p.is_file()]
            self.assertCountEqual(files,[".json",".png"])
            with self.assertRaises(ValueError):prepare("midea_2024_ocr_revenue",dest)

if __name__=="__main__":unittest.main()

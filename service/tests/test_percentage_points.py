import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from service.catalog_model import _unit_kinds
from service.core import FinanceService
from service.normalization import numeric_candidate, unit_info, unit_kind
from service.semantic import SCHEMA_HASH, VERSION, _source_number, materialize, table_batches
from service.tests.test_semantic_sources import mappings


class PercentagePointTests(unittest.TestCase):
    def column(self, raw, number, polarity="negative", unit="个百分点"):
        start=raw.index(number)
        return {"column":2,"period":"2024-FY","start":"2024-01-01","end":"2024-12-31","unit":unit,
                "currency":"percentage_points","numeric_span":{"text":number,"start":start,"end":start+len(number),"polarity":polarity}}

    def materialize(self,raw,column):
        table={"index":0,"page":1,"rows":[["变动",raw]],"cells":{"B1":{"bbox":[1,2,3,4]}}}
        batch=[{"table":table,"rows":[1]}]
        facts,issues=materialize(mappings(0,1,"ratio_change",[column]),batch,"doc","fixture")
        return facts,issues

    def test_percent_and_percentage_points_remain_distinct_dimensions(self):
        for label in ("个百分点","百分点","percentage points","percentage_points","pp","p.p."):
            with self.subTest(label=label):
                self.assertEqual(unit_info(label)[1:],(Decimal(1),"percentage_points"))
                self.assertEqual(unit_info(label,"roe")[2],"percentage_points")
        self.assertEqual(unit_info("百分比")[2],"percent")
        self.assertEqual(unit_kind("percent"),"ratio_percent")
        self.assertEqual(unit_kind("percentage_points"),"percentage_points")
        self.assertNotEqual(_unit_kinds({"units":["percent"]}),_unit_kinds({"units":["percentage_points"]}))

    def test_model_selected_decrease_preserves_literal_source_and_codepoint_span(self):
        raw="📉减少2.5个百分点"
        facts,issues=self.materialize(raw,self.column(raw,"2.5"))
        self.assertEqual(issues,[])
        fact=facts[0]
        self.assertEqual(fact["value"],"-2.5");self.assertEqual(fact["raw_value"],raw)
        self.assertEqual(fact["currency"],"percentage_points");self.assertEqual(fact["unit_kind"],"percentage_points")
        span=fact["source"]["normalization"]["numeric_span"]
        self.assertEqual(span["start"],3);self.assertEqual(span["end"],6)
        self.assertEqual(span["offset_unit"],"unicode_codepoint");self.assertEqual(fact["source"]["bbox"],[1,2,3,4])

    def test_unmapped_point_text_is_not_silently_omitted_from_llm_batches(self):
        raw="上升3个百分点"
        self.assertTrue(numeric_candidate(raw))
        parsed={"company":"test","report_year":2024,"pages":[{"page":1,"text":"原文"}],"tables":[{"index":0,"page":1,"rows":[["比例变动",raw]]}]}
        batch=table_batches(parsed)[0]
        extracts=mappings(0,1,"ratio_change",[self.column(raw,"3","positive")])
        _,issues=materialize(extracts[:1],batch,"doc","fixture")
        self.assertTrue(any(issue["reason"]=="unmapped_numeric_row" for issue in issues))
        _,issues=materialize(mappings(0,1,"ratio_change",[{"column":2,"period":"2024-FY","unit":"个百分点"}]),batch,"doc","fixture")
        self.assertTrue(any(issue["reason"]=="missing_numeric_span" for issue in issues))

    def test_substring_mismatch_utf16_offsets_and_invalid_polarity_are_rejected(self):
        raw="📉减少2.5个百分点"
        for mutation in ("text","utf16","bounds","boolean","polarity"):
            col=self.column(raw,"2.5")
            if mutation=="text":col["numeric_span"]["text"]="3.5"
            elif mutation=="utf16":col["numeric_span"].update(start=4,end=7)
            elif mutation=="bounds":col["numeric_span"]["end"]=999
            elif mutation=="boolean":col["numeric_span"]["start"]=True
            else:col["numeric_span"]["polarity"]="invented"
            with self.subTest(mutation=mutation):
                facts,issues=self.materialize(raw,col)
                self.assertEqual(facts,[])
                self.assertTrue(any(issue["reason"]=="invalid_numeric_span" for issue in issues))

    def test_negative_sign_and_parenthesis_cannot_be_stripped_or_flipped(self):
        for raw,token in [("变动-2.5个百分点","-2.5"),("变动（2.5）个百分点","（2.5）"),("变动( 2.5 )个百分点","( 2.5 )")]:
            with self.subTest(raw=raw):
                _,_,error=_source_number(raw,self.column(raw,token,"positive"))
                self.assertEqual(error,"numeric_span_polarity_conflict")
                value,_,error=_source_number(raw,self.column(raw,token,"as_written"))
                self.assertEqual(error,None);self.assertEqual(value,Decimal("-2.5"))
                _,_,error=_source_number(raw,self.column(raw,"2.5","positive"))
                self.assertEqual(error,"numeric_span_splits_token")

    def test_clipped_digits_decimal_and_comma_group_are_rejected(self):
        for raw,token in [("上升12.5个百分点","2.5"),("上升2.51个百分点","2.5"),("上升1,234.5个百分点","234.5")]:
            with self.subTest(raw=raw):
                _,_,error=_source_number(raw,self.column(raw,token,"positive"))
                self.assertEqual(error,"numeric_span_splits_token")

    def test_numeric_unit_adjacent_to_span_must_match_mapped_dimension(self):
        raw="下降2.5个百分点"
        wrong=self.column(raw,"2.5",unit="%")
        facts,issues=self.materialize(raw,wrong)
        self.assertEqual(facts,[]);self.assertTrue(any(issue["reason"]=="source_cell_unit_mismatch" for issue in issues))
        raw="其他文字3个百分点，本项上升8.1%"
        correct=self.column(raw,"8.1","positive",unit="%")
        facts,issues=self.materialize(raw,correct)
        self.assertEqual(issues,[]);self.assertEqual(facts[0]["unit_kind"],"ratio_percent")
        self.assertEqual(facts[0]["value"],"8.1")

    def test_query_and_saved_fact_export_include_kind_and_original_span(self):
        with tempfile.TemporaryDirectory() as temporary:
            svc=FinanceService(Path(temporary))
            try:
                svc.create_project("p","Unit fixture")
                raw="减少2.5个百分点"
                path=svc.store.root/"uploads"/"2024.csv";path.write_text("变动,"+raw,encoding="utf-8")
                doc=svc.register_document("p",str(path),path.name)["data"]
                parsed={"company":"公司","report_year":2024,"warnings":[],"pages":[{"page":1,"text":raw}],
                        "tables":[{"index":0,"page":1,"rows":[["变动",raw]],"cells":{}}]}
                svc._persist_prepared("p",doc["document_id"],parsed)
                batch=table_batches(parsed)[0];ex=mappings(0,1,"ratio_change",[self.column(raw,"2.5")])
                facts,issues=materialize(ex,batch,doc["document_id"],"fixture")
                svc._commit_semantic_batch("p",doc["document_id"],"owner",batch,facts,issues,
                    {"version":VERSION,"schema_hash":SCHEMA_HASH,"model":"fixture","extractions":ex})
                query=svc.query_financial_data("p",{"currency":"percentage_points"})["data"]["items"]
                exported=json.loads(json.dumps(query,ensure_ascii=False))
                self.assertEqual(exported[0]["unit_kind"],"percentage_points")
                self.assertEqual(exported[0]["normalized_unit"],"个百分点")
                self.assertEqual(exported[0]["raw_value"],raw)
                self.assertEqual(exported[0]["numeric_span"]["polarity"],"negative")
            finally:
                for pool in (svc.processing_pool,svc.pool,svc.analysis_pool,svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)


if __name__=="__main__":unittest.main()

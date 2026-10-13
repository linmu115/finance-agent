"""Focused offline checks of actual known failure classes; no model or server calls."""
import importlib.util,io,json,tempfile,unittest,zipfile
from pathlib import Path
from blind import ROOT,Redactor,IDENTITY,read,expand_archive,build,dump
from metrics import compare_claim,summarize,aggregate_scores,stability,DIMS,RUBRIC_VERSION

class BlindPipelineTests(unittest.TestCase):
    def test_redacts_paths_tools_ids_without_changing_economic_units(self):
        redact=Redactor({'run_analysis':'component_1','statement_analysis':'component_2'})
        sample='financial run_analysis statement_analysis 12.07 HKD/share, 240.2亿元, 2024E; /api/projects/03b52dde-19da-49c1-949a-ee6d93bf036b/artifacts/x.png'
        got=redact(sample)
        self.assertIsNone(IDENTITY.search(got));self.assertIn('12.07 HKD/share, 240.2亿元, 2024E',got)
    def test_scale_currency_direction_and_rounding(self):
        ref={'value':24.02,'unit':'CNY_100million','absolute_tolerance':.005}
        self.assertEqual(compare_claim(ref,{'value':24.02,'unit':'CNY_billion'})['status'],'scale_mismatch')
        self.assertEqual(compare_claim(ref,{'value':24.02,'unit':'HKD'})['status'],'unit_or_currency_mismatch')
        self.assertEqual(compare_claim({'value':11.23042858,'unit':'HKD/share','absolute_tolerance':.005},{'value':12.07,'unit':'HKD/share'})['status'],'numeric_mismatch')
        self.assertEqual(compare_claim({'value':11.23042858,'unit':'HKD/share','absolute_tolerance':.005},{'value':11.23,'unit':'HKD/share'})['status'],'rounding_consistent')
        self.assertEqual(compare_claim({'value':5.723,'unit':'CNY_million','direction':'add'},{'value':5.723,'unit':'CNY_million','direction':'subtract'})['status'],'direction_mismatch')
        self.assertEqual(compare_claim(ref,None)['status'],'missing')
    def test_decimal_precision_survives_and_id_touching_chinese_is_redacted(self):
        redact=Redactor({})
        value='1808.67847193837461514903478831019450'
        self.assertEqual(redact(value),value)
        self.assertNotIn('3d9d0befd8374eed9a7488dbd8dd00d2',redact('文档3d9d0befd8374eed9a7488dbd8dd00d2原文'))
    def test_historical_failures_and_unknown_usage_remain_counted(self):
        result=summarize(ROOT/'data/evaluation/pi-cowork-acceptance-20261006')
        rows=[x for x in result['rows'] if x['profile']=='prepared']
        self.assertEqual(len(rows),7);self.assertEqual(sum(x['usage']['unknownCalls'] for x in rows),5)
        self.assertEqual(sum(x['usage']['input'] for x in rows),4086897)
        self.assertTrue(all(x['provider_billed_cost'] is None for x in rows));self.assertFalse(result['advantage_claim'])
    def test_no_advantage_claim_with_missing_heldout_or_unknown_cost(self):
        base={'split':'development','task_type':'valuation','task_id':'1','repeat':1,'scores':dict(reading=4,substantive=4,explanation=3,adjustments=None,anomalies=None,common=4),'material_defects':[],'status':'completed','verified_cost':None}
        rows=[dict(base,profile='prepared'),dict(base,profile='financial')]
        result=aggregate_scores(rows)
        self.assertFalse(result['may_claim_advantage'])
        self.assertIsNone(result['groups'][0]['mean_scores']['adjustments'])
        self.assertEqual(result['groups'][0]['scored_counts']['adjustments'],0)
    def test_v2_stability_excludes_untested_and_enforces_cap(self):
        parent=ROOT/'data/evaluation/blind-eval-offline-rubric-test';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as td:
            base=Path(td)
            req={k:{'coverage':'not_tested' if k=='R4' else 'direct'} for k in ['R1','R2','R3','R4','R5','C']}
            dump(base/'reference/reference.json',{'rubric_version':RUBRIC_VERSION,'task_requirements':{'1':req}})
            dump(base/'private-map.json',{'cases':[{'case_id':'S1','label':'A1','profile':'prepared','task':'1'}]})
            scores={k:None if k=='adjustments' else 3 for k in DIMS}
            for rd in ['round1','round2']:
                dump(base/f'private-{rd}-map.json',{'Q01':'S1'})
                dump(base/rd/'review.json',{'metadata':{'model':'gpt-6-astra','reasoning_effort':'high','rubric_version':RUBRIC_VERSION},'reviews':[{'case_id':'Q01','scores':dict(scores),'material_defects':[]}]})
            self.assertEqual(stability(base)['scored_dimension_pairs'],5)
            second=read(base/'round2/review.json');second['reviews'][0]['scores']['adjustments']=4
            dump(base/'round2/review.json',second)
            with self.assertRaisesRegex(ValueError,'Untested'):stability(base)
            second['reviews'][0]['scores']['adjustments']=None
            second['reviews'][0]['material_defects']=[{'evidence':'wrong currency'}]
            dump(base/'round2/review.json',second)
            with self.assertRaisesRegex(ValueError,'cap'):stability(base)
    def test_all_historical_attachments_preserved_and_image_bytes_unchanged(self):
        dest=ROOT/'data/evaluation/blind-eval-rehearsal-v2-20261007';mapping=read(dest/'private-map.json')
        self.assertEqual(len(mapping['cases']),12);self.assertEqual(sum(len(c['files']) for c in mapping['cases']),124)
        source=Path(mapping['source'])
        for c in mapping['cases']:
            for f in c['files']:
                p=dest/'packet'/c['case_id']/f['anonymous'];self.assertTrue(p.exists() or p.with_suffix(p.suffix+'.expanded').exists())
                if p.suffix=='.png':self.assertEqual(p.read_bytes(),(source/(c['label']+'-artifacts')/f['original']['localFile']).read_bytes())
    def test_native_nested_calculator_archive_is_anonymized_without_execution(self):
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w') as z:z.writestr('service/research_models.py','value=11.23042858274428535833348855366149\n# run_financial_model')
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w') as z:z.writestr('finance_model_code.zip',inner.getvalue())
        parent=ROOT/'data/evaluation/blind-eval-offline-archive-test';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as td:
            target=Path(td)/'expanded';expand_archive(outer.getvalue(),target,{})
            files=list(target.rglob('*.py'));self.assertEqual(len(files),1)
            text=files[0].read_text();self.assertIn('11.23042858274428535833348855366149',text);self.assertNotIn('run_financial_model',text)
    def test_replay_selects_all_exposed_versions_including_superseded(self):
        from replay import targets
        _,analyses,_=targets(ROOT/'data/evaluation/pi-cowork-acceptance-20261006')
        self.assertEqual(len(analyses),18)
    def test_failed_download_is_kept_distinct_from_evaluator_copy_and_missing_file(self):
        parent=ROOT/'data/evaluation/blind-eval-offline-delivery-test';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as td:
            base=Path(td);source=base/'source';source.mkdir();reference=base/'reference';reference.mkdir()
            dump(reference/'gold.json',{});(reference/'reference-notes.md').write_text('Reference')
            dump(source/'experiment.json',{'tasks':[{'id':'1','prompt':'Analyze the report'}],'runs':[{'label':'P1','status':'completed','profile':'prepared'}]})
            (source/'P1-answer.md').write_text('12.07 HKD/share')
            artifacts=source/'P1-artifacts';artifacts.mkdir();(artifacts/'copy.csv').write_text('value,unit\n12.07,HKD/share')
            dump(source/'P1-deliverables.json',{'artifacts':[{'name':'values.csv','url':'/api/projects/project/artifacts/values.csv','httpStatus':404,'evaluatorLocalFile':'copy.csv'},{'name':'missing.md','url':'/api/projects/project/artifacts/missing.md','httpStatus':404,'error':'unavailable'}]})
            dest=base/'result';build(source,dest,1,reference)
            files=read(dest/'round1/Q01/files.json')
            self.assertEqual(files[0]['role'],'evaluator_copy_download_failed');self.assertEqual(files[0]['download_status'],404)
            self.assertEqual(files[1]['role'],'unavailable_attachment');self.assertIsNone(files[1]['file'])

if __name__=='__main__':unittest.main()

"""Offline acceptance, explicitly scoped copied SQLite databases only.

No Store migration, source database writes, LLM calls, service or Docker access.
Independent source numbers below are acceptance references, never product input.
"""
import argparse
import importlib.util
import json
from decimal import Decimal as D, localcontext
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('ashare_replay',Path(__file__).with_name('replay-ashare-workpapers.py'))
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
from service.workpaper_signals import anomaly_signals
from service.analysis_report import compile_report,render_report,bind_text

CASES=[('yili','old','b43ae45c-d96b-43b6-ab5b-04306c0eb142','1f94f25a3cb74d528f10ddac0be06a0d'),
       ('ruihe','current','374beac2-a970-4972-b210-e91018bbd6e6','ab25c52089fd4db89fba046c9c811c46'),
       ('carote','current','03b52dde-19da-49c1-949a-ee6d93bf036b','3d9d0befd8374eed9a7488dbd8dd00d2')]


def manual_references():
    # Transcribed independent source references; arithmetic does not read tool
    # inputs/outputs. Each tuple includes physical PDF pages, not printed pages.
    revenue=D('115393310976.69');prior_revenue=D('125758168916.51')
    assets=D('153718003927.97');prior_assets=D('151620252657.98')
    np=D('8463710355.65');cfo=D('21739740393.38')
    yield 'yili','2024-FY_cash_conversion',cfo/np,[92,18]
    yield 'yili','2024-FY_accrual',(np-cfo)/((assets+prior_assets)/2)*100,[92,18,87]
    yield 'yili','receivables_growth_gap',((D('2878402047.44')/D('3084668398.14')-1)-(revenue/prior_revenue-1))*100,[87,7]
    yield 'yili','inventory_growth_gap',((D('10744674420.37')/D('12511775911.77')-1)-(D('76298833033.93')/D('84788592077.34')-1))*100,[87,18]
    yield 'yili','receivables_aging_change',((D('45742612.15')+D('7258718.02')+D('13283342.38'))/D('2993348236.25')-(D('28890564.44')+D('8307208.18')+D('12947187.60'))/D('3184937408.42'))*100,[153]
    yield 'yili','inventory_provision_change',(D('842927397.83')/D('11587601818.20')-D('1105099296.45')/D('13616875208.22'))*100,[164]
    yield 'yili','other_receivables_asset_share',D('125650067.32')/assets*100,[87]
    yield 'yili','other_receivables_growth',(D('125650067.32')/D('194691604.87')-1)*100,[87]
    yield 'yili','prepayments_asset_share',D('1176127164.72')/assets*100,[87]
    yield 'yili','prepayments_growth',(D('1176127164.72')/D('1480054252.66')-1)*100,[87]
    yield 'yili','other_noncurrent_asset_share',D('29259348529.10')/assets*100,[87]
    yield 'yili','other_noncurrent_growth',(D('29259348529.10')/D('19713153876.26')-1)*100,[87]
    yield 'yili','q4_revenue_share',D('26660376531.26')/revenue*100,[8,7]
    yield 'yili','q4_parent_profit_share',D('-2415620352.16')/D('8452859993.18')*100,[8,92]
    yield 'ruihe','receivables_overdue_change',(D('65202')/D('142099')-D('65400')/D('154318'))*100,[47]
    yield 'ruihe','2025-H1_cash_conversion',D('-30650')/D('41098'),[28,32]


def main():
    p=argparse.ArgumentParser();p.add_argument('--old-copy',type=Path,required=True);p.add_argument('--current-copy',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();reports={};summaries=[];inventory_rates={}
    for name,which,project,doc in CASES:
        s=legacy.FinanceService.__new__(legacy.FinanceService);s.store=legacy.ReadOnlyCopy(args.old_copy if which=='old' else args.current_copy)
        with localcontext() as ctx:
            ctx.prec=40;raw,records=anomaly_signals(s,project,doc);report=compile_report(raw,records)
        destination=args.output/name;destination.mkdir(parents=True,exist_ok=True);render_report(report,destination)
        (destination/'workpaper.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        (destination/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        rows=report['tables']['signals']['rows'];reports[name]={r['key']:r for r in rows}
        inventory_rates[name]=report['tables']['inventory_charge_rates']['rows']
        assert len({r['family'] for r in rows})==9
        assert all(r['missing'] for r in rows if r['value'] is None)
        assert all(r['evidence']!='[]' for r in rows if r['value'] is not None)
        assert {r['key'] for r in report['tables']['observations']['rows']}=={r['key'] for r in rows if r['triggered']=='是'}
        assert '{{' not in bind_text('{{signals.'+rows[0]['key']+'.value}}',report['tables'])
        summaries.append({'company':name,'signals':len(rows),'families':9,'known':sum(r['value'] is not None for r in rows),'triggered':[r['key'] for r in rows if r['triggered']=='是'],
                          'missing':[{'key':r['key'],'reason':r['missing']} for r in rows if r['value'] is None]})
    checks=[]
    with localcontext() as ctx:
        ctx.prec=40
        for name,key,expected,pages in manual_references():
            r=reports[name][key];actual=D(r['value']);assert abs(actual-expected)<D('1e-25'),(name,key,actual,expected)
            checks.append({'company':name,'key':key,'expected':str(expected),'actual':str(actual),'pdf_pages':pages,'match':True,'source_positions':json.loads(r['evidence'])})
        rate=next(r for r in inventory_rates['yili'] if r['period']=='2024-FY')
        expected=D('1260269311.15')/((D('13616875208.22')+D('11587601818.20'))/2)*100
        assert abs(D(rate['value'])-expected)<D('1e-25')
        assert next(r for r in inventory_rates['yili'] if r['period']=='2023-FY')['value'] is None
        checks.append({'company':'yili','key':'2024-FY_inventory_charge_rate','expected':str(expected),'actual':rate['value'],'pdf_pages':[164,165],'match':True})
    result={'llm_calls':0,'database_mode':'copied sqlite mode=ro; legacy TEMP view only','checked_computations':len(checks),'checks':checks,'cases':summaries,'inventory_charge_rates':inventory_rates,
            'visual_review':{'yili_pdf_pages':[8,87,92,153,164,165,62],'ruihe_pdf_pages':[47]},'not_proven':'专业优势与正式对照由N1验收；本脚本无付费分析或入库'}
    args.output.mkdir(parents=True,exist_ok=True);(args.output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'checked_computations':len(checks),'cases':[{k:v for k,v in r.items() if k!='missing'} for r in summaries]},ensure_ascii=False))


if __name__=='__main__':main()

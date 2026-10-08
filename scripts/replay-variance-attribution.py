"""Offline, read-only acceptance on the three expressly authorized copies."""
import argparse
import importlib.util
import json
from decimal import Decimal as D,localcontext
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('signals_replay',Path(__file__).with_name('replay-analyst-signals.py'))
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
from service.workpaper_variance import variance_attribution
from service.workpaper_annual import compact
from service.analysis_report import compile_report,render_report,bind_text

# Source transcriptions used only by acceptance, never by product matching.
MANUAL=[('yili','gross_change','-1875.09889641',18),
        ('yili','selling','589.20394521',18),('yili','administrative','689.10829385',18),
        ('yili','finance_costs','438.80125294',18),('yili','research','-19.83038463',18),
        ('yili','investment_income','2448.41963494',210),('yili','credit_impairment','-394.54239445',211),
        ('yili','parent_profit_change','-1975.68046476',92),
        ('ruihe','revenue_change','-60.619',28),('ruihe','fair_value_gains','63.015',28),
        ('ruihe','parent_profit_change','79.226',28)]
REVIEWED=[('yili','revenue_effect',18),('yili','margin_effect',18),('yili','selling',18),
          ('yili','administrative',18),('yili','finance_costs',18),('yili','research',19),
          ('yili','investment_income',210),('yili','credit_impairment',211),
          ('ruihe','research',13),('ruihe','selling',13),('ruihe','administrative',13),
          ('ruihe','tax',13),('ruihe','fair_value_gains',14)]


def main():
    p=argparse.ArgumentParser();p.add_argument('--old-copy',type=Path,required=True);p.add_argument('--current-copy',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();reports={};cases=[]
    for name,which,project,doc in shared.CASES:
        s=shared.legacy.FinanceService.__new__(shared.legacy.FinanceService)
        s.store=shared.legacy.ReadOnlyCopy(args.old_copy if which=='old' else args.current_copy)
        with localcontext() as ctx:
            ctx.prec=40;raw,records=variance_attribution(s,project,doc);report=compile_report(raw,records)
        dest=args.output/name;dest.mkdir(parents=True,exist_ok=True);render_report(report,dest)
        (dest/'workpaper.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        (dest/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        tabs=report['tables'];reports[name]=tabs
        residuals={r['key']:r['contribution'] for r in tabs['bridge']['rows'] if r['role']=='residual'}
        assert len(residuals)==4 and all(D(v)==0 for v in residuals.values())
        with s.store.connect() as db:pages={r['page']:r['text'] for r in db.execute('SELECT page,text FROM pages WHERE document_id=?',(doc,))}
        for r in tabs['drivers_evidence']['rows']:
            refs=json.loads(r['source'])
            if not refs:assert r['status']=='原文未说明'
            for ref in refs:
                assert ref['document_id']==doc and compact(ref['quote']) in compact(pages[ref['page']]),r['key']
        structure=[]
        for total in (r for r in tabs['contributions']['rows'] if r['role']=='total'):
            group=[r for r in tabs['contributions']['rows'] if r['view']==total['view'] and r['role'] in ('component','residual')]
            for key in ('revenue_change','gross_change'):
                if total[key] is not None:assert sum(D(r[key]) for r in group if r[key] is not None)==D(total[key])
            residual=next(r for r in group if r['role']=='residual')
            structure.append({'view':total['view'],'revenue_change':total['revenue_change'],'unallocated_revenue':residual['revenue_change'],
                              'gross_change':total['gross_change'],'unallocated_gross':residual['gross_change'],
                              'missing_components':[r['item'] for r in group if r['role']=='component' and r['revenue_change'] is None]})
        assert '{{' not in bind_text('{{bridge.parent_profit_change.contribution}}',tabs)
        cases.append({'company':name,'bridge_residuals':residuals,'structure':structure,
                      'explanations_found':sum(r['status']!='原文未说明' for r in tabs['drivers_evidence']['rows']),
                      'explanations_missing':[r['key'] for r in tabs['drivers_evidence']['rows'] if r['status']=='原文未说明']})
    checks=[]
    for name,key,expected,page in MANUAL:
        actual=next(r['contribution'] for r in reports[name]['bridge']['rows'] if r['key']==key)
        assert D(actual)==D(expected),(name,key,actual)
        checks.append({'company':name,'key':key,'actual_million':actual,'expected_million':expected,'pdf_page':page})
    for label,expected in [('液体乳',[-6046,-3521,-970]),('奶粉及奶制品',[2258,-915,734]),('冷饮产品',[-1952,303,-318])]:
        r=next(r for r in reports['yili']['contributions']['rows'] if r['axis']=='product' and r['item']==label)
        assert [D(r[k+'_effect']) for k in ('volume','price','mix')]==expected
        assert D(r['decomposition_residual'])==0
        checks.append({'company':'yili','product':label,'volume_price_mix_million':expected,'pdf_page':19})
    reviewed=[]
    for name,key,page in REVIEWED:
        r=next(r for r in reports[name]['drivers_evidence']['rows'] if r['key']==key)
        assert str(page)==r['pages']
        reviewed.append({'company':name,'key':key,'pdf_page':page,'quote':r['quote'],'review':'已对照渲染 PDF 人工核对该项原因；不据此断言解释全部金额'})
    result={'llm_calls':0,'database_mode':'copied SQLite mode=ro; no source migration or writes',
            'manual_amount_checks':len(MANUAL),'product_volume_price_mix_checks':9,'source_alignment_reviews':reviewed,'checks':checks,'cases':cases,
            'limitations':['伊利产品比较期收入缺精确原值：使用原文直接披露的亿元变动额并保留精度，其他产品未知；未分配收入86.69893521百万元、毛利53.33153448百万元。',
                           '瑞和产品成本未披露，分产品毛利贡献未知；总毛利变化在未分配行。',
                           '卡罗特经营/地域视图分别保留，披露金额舍入，未匹配唯一同口径总额时残差未知。',
                           '原因检索是候选原文证据，不由程序判定经济因果或将关联说明扩大为全额归因。',
                           '未读取held-out；专业优势由N1正式对照验收。']}
    (args.output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'manual_amount_checks':len(MANUAL),'pvm_checks':9,'reviewed_causes':len(reviewed),'cases':cases},ensure_ascii=False))


if __name__=='__main__':main()

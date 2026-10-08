"""Offline N4 acceptance on the previously isolated, allowlisted development seed.

Run from this worktree after copying the old three-document seed DB to tmp/depth.
No model requests, ingestion, HTTP listener or main-database access.
"""
import json
from pathlib import Path
import sys
import subprocess
from decimal import localcontext
from types import ModuleType
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.financial_workpapers import financial_workpaper
from service.workpaper_depth import enrich_workpaper_context
from service.analysis_report import bind_text, compile_report
from service.tests.test_workpaper_expectations import actual
from service.tests.test_expectations_data import record
from service.tests.test_workpaper_comparison import subject
from service.workpaper_expectations import expectations_report
from service.workpaper_expectations_data import context_tables, reference_tables, candidate_issue
from service.workpaper_constraints import attach_constraints
from service.workpaper_comparison import comparison_report


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/evidence/n4-usable-depth-20261008'
CASES = [
    ('carote','03b52dde-19da-49c1-949a-ee6d93bf036b','3d9d0befd8374eed9a7488dbd8dd00d2'),
    ('yili','374beac2-a970-4972-b210-e91018bbd6e6','d84573bf6b584e7e874faa4c6adf454a'),
]


def save(name, obj):
    (OUT/name).write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf8'))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    s = FinanceService(ROOT/'tmp/depth')
    stats = []
    baselines = {}
    for alias, filename, function in [('variance','workpaper_variance','variance_attribution'),('signals','workpaper_signals','anomaly_signals')]:
        code=subprocess.check_output(['git','show',f'328b8e2:service/{filename}.py'],cwd=ROOT).decode('utf8')
        module=ModuleType('service._baseline_'+alias);module.__package__='service'
        exec(compile(code,filename+'.py','exec'),module.__dict__)
        baselines[alias]=getattr(module,function)
    for name, project, doc in CASES:
        reports = {}; tables = {}; prefixes = {'variance_attribution':'variance','anomaly_signals':'signals'}
        with s.store.connect() as db:
            pages = {r['page']:r['text'] for r in db.execute('SELECT page,text FROM pages WHERE document_id=?',(doc,))}
        for kind, alias in [('variance_attribution','variance'),('anomaly_signals','signals')]:
            begin=perf_counter()
            result=financial_workpaper(s,project,kind,document_id=doc)
            report=result['report']; reports[kind]=report
            # financial_workpaper uses precision 40; both arms use that same
            # arithmetic context, rather than comparing different rounding.
            with localcontext() as ctx:
                ctx.prec=40
                old_report,old_records=baselines[alias](s,project,document_id=doc)
                baseline=compile_report(old_report,old_records)
            checked=0
            for table_name, old in baseline['tables'].items():
                new=report['tables'][table_name]
                by_key={r['key']:r for r in new['rows']}
                for i,row in enumerate(old['rows']):
                    for column in old['columns']:
                        if column in old.get('evidence',[{}]*len(old['rows']))[i]:
                            assert row.get(column)==by_key[row['key']].get(column),(name,table_name,i,column)
                            checked+=1
            quote_count=0
            for row in report['drivers_evidence']:
                for ref in row['evidence']:
                    assert ref['document_id']==doc
                    assert ref['quote'] in pages[ref['page']],(name,row['key'],ref['page'],ref['quote'])
                    quote_count+=1
                q=row['quantity_ref']
                bind_text('{{'+q['table']+'.'+q['row_key']+'.'+q['column']+'}}',report['tables'])
            assert result['drivers_evidence']==report['drivers_evidence']
            follows=report.get('signal_followups',[])
            if kind=='anomaly_signals':
                triggered={r['key'] for r in report['tables']['signals']['rows'] if r['triggered']=='是'}
                assert {r['key'] for r in follows}==triggered
                assert all(r['alternative_explanations'] and r['tracking_metrics'] for r in follows)
                assert all(not r['persistence']['allow_continuous_claim'] and '连续' not in r['persistence']['summary'] for r in follows if r['persistence']['known_sample_count']<3)
            tables.update({prefixes[kind]+'_'+k:v for k,v in report['tables'].items()})
            save(f'{name}-{alias}.json',report)
            save(f'baseline-{name}-{alias}.json',{'title':baseline['title'],'tables':{k:v for k,v in baseline['tables'].items() if k in ('drivers_evidence','signals')}})
            stats.append({'company':name,'kind':kind,'delivery_id':result['delivery']['id'],
                          'drivers':len(report['drivers_evidence']),
                          'found':sum(bool(r['evidence']) for r in report['drivers_evidence']),
                          'verbatim_quotes_checked':quote_count,'unchanged_numeric_cells':checked,
                          'triggered_followups':len(follows),'seconds':round(perf_counter()-begin,3)})
        context=enrich_workpaper_context(s,project,selection={},reports=reports,context={'full_tables':{'tables':tables}})
        refs=[ref for r in context['management_evidence'] for ref in r['linked_refs']]
        for ref in refs: bind_text('{{'+ref+'}}',tables)
        save(name+'-n2-context.json',context)
        summary={'company':name,'management_entries':len(context['management_evidence']),
                 'unique_quoted_entries':sum(bool(r['quotes']) for r in context['management_evidence']),
                 'linked_numeric_refs_checked':len(refs),'context_utf8_bytes':len(json.dumps(context,ensure_ascii=False,separators=(',',':')).encode())}
        stats.append(summary)

    # Mechanism cases, explicitly synthetic: unknown profit ownership; revenue
    # boundary/scope; cross-basis EPS; report-window and standard differences.
    old=record('unknown_profit',100,metric='net_profit',published='2024-05-01')
    old['exclusion_reason']=candidate_issue(old,[])
    new=record('parent_profit',110,metric='net_profit_parent',published='2024-11-01')
    revenue=record('revenue_reference',100,metric='revenue');revenue['label']='收入'
    actual_revenue=actual(110,'revenue',unit='元');actual_revenue['label']='营业总收入'
    eps=record('eps_reference','1.92',basis='latest_shares')
    actual_eps=actual('1.33','eps','元/股');actual_eps['basis']='basic'
    forecasts=[old,new,revenue,eps]; actuals=[actual(120,unit='元'),actual_revenue,actual_eps]
    links,latest=context_tables(forecasts,actuals,None)
    r=expectations_report(forecasts,actuals)
    r['tables'].update(links);r['tables'].update(reference_tables(latest,actuals))
    attach_constraints(r,[c for t in r['tables'].values() for c in t.get('answer_constraints',[])])
    compiled=compile_report(r)
    assert any(c['code']=='profit_attribution_unknown' for c in r['answer_constraints'])
    assert any(i['dimension']=='revenue_boundary' for c in r['answer_constraints'] for i in c['issues'])
    save('synthetic-expectations.json',compiled)
    a=subject();b=subject('previous',2023);b['scope']='parent';b['period_end']='2023-06-30';b['metadata']={}
    comparison=compile_report(comparison_report([a,b]))
    save('synthetic-comparison.json',comparison)
    ext=enrich_workpaper_context(None,'synthetic',selection={},reports={'expectations':compiled,'comparison':comparison},context={})
    all_tables={**{'expectations_'+n:t for n,t in compiled['tables'].items()},**{'comparison_'+n:t for n,t in comparison['tables'].items()}}
    for c in ext['comparability_constraints']:
        for ref in c['affected_refs']: bind_text('{{'+ref+'}}',all_tables)
    save('synthetic-constraints-n2.json',ext)
    save('acceptance-summary.json',{'base':'328b8e2','seed':'old adoption-preflight development snapshot; no refreshed ingestion',
                                 'model_requests':0,'model_tokens':0,'records':stats,
                                 'synthetic_constraints':len(ext['comparability_constraints'])})
    print(json.dumps(stats,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

"""Replay frozen participant scripts only through the Docker analysis service."""
import csv,json,sqlite3,shutil,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
ACTIVE=ROOT/'data/active';TRIAL=ROOT/'data/evaluation/harness-v2-a2-20261007'
EVIDENCE=ROOT/'docs/evidence/harness-v2-20261007/a2-replay.json'
PROJECT='03b52dde-19da-49c1-949a-ee6d93bf036b'
CASES=[('D2','18f59dcff3ce4da583c4344de2ecb8f8','wacc0','b0f85ea843f14cbd8b45d3657484d3d0'),('E2','5cb01aa8858044a2b4cee37d4087291d','w0','bd549124c5af4055a1a3781355b822e6'),('F2','c30e787485ff4c6e8c46f5fb45a9a364','wacc0','7753faff45da4d8bb660ea43b2120a69'),('C2','3975b7c387d34bdea3eb3ff48cd165f6','wacc','e309e919e04d453dac26c42583498ea8')]
def rows(path):return list(csv.DictReader(path.open(encoding='utf-8-sig')))
def read(path):return json.loads(path.read_text(encoding='utf8'))
def values(label,out):
    if label=='D2':
        data=rows(out/'forecast_and_dcf_inputs.csv')
        metrics={r['metric']:r['value'] for r in data if r['section']=='calculation'}
        return {k:metrics[v] for k,v in zip(['pv','pvt','ev','equity','price'],['PV explicit FCF','PV terminal value','EV','Equity value','Value/share'])},[r['value'] for r in data if r['section']=='sensitivity']
    if label=='F2':
        data=rows(out/'valuation_workings.csv');m={r['item']:r['value'] for r in data if r['section']=='DCF base result'}
        grid={r['item']:r['value'] for r in data if r['section']=='Sensitivity'}
        return {k:m[v] for k,v in zip(['pv','pvt','ev','equity','price'],['PV_explicit_FCF','PV_terminal_value','EV','Equity_value','HKD_per_share'])},[grid[f'WACC={w}%, g={g}%'] for g in (1,2,3) for w in ('11.2','12.2','13.2')]
    if label=='C2':
        d=read(out/'recalc_results.json');return {k:d[v] for k,v in zip(['pv','pvt','ev','equity','price'],['pv_explicit_RMB_mn','pv_terminal_RMB_mn','EV_RMB_mn','equity_RMB_mn','HKD_per_share'])},[d['sensitivity'][i][str(w)] for i in range(3) for w in (.112,.122,.132)]
    data=rows(out/'DCF输入与计算.csv');m={r['财年/项目']:r['值'] for r in data}
    # Exact frozen labels are retained in evidence and selected below.
    keys=list(m);outm={}
    for key,patterns in {'pv':['显性','现值合计'],'pvt':['终值现值'],'ev':['企业价值','EV'],'equity':['股权价值'],'price':['每股']}.items():
        matches=[k for k in keys if any(p in k for p in patterns)]
        if len(matches)!=1:raise ValueError((key,matches,keys))
        outm[key]=m[matches[0]]
    grid=rows(out/'DCF敏感性.csv')
    return outm,[v for row in grid for k,v in row.items() if k!='永续增长率']

def golden(label,out):
    if label=='D2':
        d=read(out/'updated_inputs_results.json');keys=['PV_explicit_RMB_mn','PV_terminal_RMB_mn','EV_RMB_mn','Equity_RMB_mn','HKD_per_share']
        return [{k:d[s][v] for k,v in zip(['pv','pvt','ev','equity','price'],keys)} for s in ('old','wacc_only_step','new')],sum(d['new_grid_HKD_per_share'],[])
    if label=='C2':
        d=read(out/'update_results.json');keys=['explicit_pv_RMB_mn','terminal_pv_RMB_mn','EV_RMB_mn','equity_RMB_mn','HKD_per_share']
        return [{k:d[s][v] for k,v in zip(['pv','pvt','ev','equity','price'],keys)} for s in ('base','after_wacc_only','updated')],sum(d['sensitivity']['updated'],[])
    if label=='F2':
        data=rows(out/'dcf_update_workings.csv');states=[]
        for section in ('Old baseline','After WACC only','Updated (WACC + FCF)'):
            m={r['item']:r['value'] for r in data if r['section']==section}
            states.append({k:m[v] for k,v in zip(['pv','pvt','ev','equity','price'],['pv_explicit_RMBmn','pv_terminal_RMBmn','EV_RMBmn','equity_RMBmn','HKD_per_share'])})
        grid={r['item']:r['value'] for r in data if r['section']=='Sensitivity updated'}
        return states,[grid[f'WACC={w}%, g={g}%'] for g in (1,2,3) for w in ('11.2','12.2','13.2')]
    data=rows(out/'估值差异拆解.csv');return [{'price':r['港币/股']} for r in data],sum(read(out/'chart_data.json')['updated'],[])

def close(actual,expected):return abs(Decimal(str(actual))-Decimal(str(expected)))<=Decimal('1e-10')

def main():
    TRIAL.mkdir(parents=True,exist_ok=True)
    if not (TRIAL/'finance.sqlite').exists():
        with sqlite3.connect(ACTIVE.joinpath('finance.sqlite').as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(TRIAL/'finance.sqlite') as target:source.backup(target)
    for _,source,_,_ in CASES:
        for part,tail in [('analysis',Path(source)),('exports',Path(PROJECT)/source)]:
            dest=TRIAL/part/tail
            if not dest.exists():shutil.copytree(ACTIVE/part/tail,dest)
    service=FinanceService(TRIAL);evidence={'method':'No LLM. Unmodified frozen scripts except AST numeric overrides; original input snapshots; Docker only. Frozen precision varies, absolute tolerance 1e-10. All common numeric cells compared; historical hardcoded prose/units preserved.','cases':[]}
    prior={c['label']:c for c in read(EVIDENCE).get('cases',[])} if EVIDENCE.exists() else {}
    for label,source,wacc,reference in CASES:
        if label in prior and prior[label]['state']['status']=='succeeded':
            run=prior[label]['run_id'];state=prior[label]['state'];status=service.get_analysis_status(PROJECT,run)['data']
        else:
            result=service.run_analysis(PROJECT,source_run_id=source,params={wacc:{'+':.005},'fcf':{'*':.9}},params_order=[wacc,'fcf'],financial_tools=False)['data']
            run=result['run_id'];state=service.analysis_futures[run].result();status=service.get_analysis_status(PROJECT,run)['data']
        item={'label':label,'source_run_id':source,'run_id':run,'reference_run_id':reference,'state':state};evidence['cases'].append(item)
        EVIDENCE.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8');print(label,run,state['status'],flush=True)
        if state['status']!='succeeded':continue
        old,old_grid=values(label,ACTIVE/'analysis'/source/'output');step,_=values(label,TRIAL/'analysis'/state['parameter_steps'][0]['run_id']/'output');new,grid=values(label,TRIAL/'analysis'/run/'output')
        refs,refgrid=golden(label,ACTIVE/'analysis'/reference/'output');checks=[]
        for name,actual,expected in zip(('old','wacc_only','new'),(old,step,new),refs):
            checks += [{'cell':name+'.'+key,'actual':actual[key],'expected':value,'pass':close(actual[key],value)} for key,value in expected.items()]
        checks += [{'cell':'sensitivity.'+str(i),'actual':a,'expected':b,'pass':close(a,b)} for i,(a,b) in enumerate(zip(grid,refgrid))]
        for name,a,b,c,d in [('wacc',step['price'],old['price'],refs[1]['price'],refs[0]['price']),('fcf',new['price'],step['price'],refs[2]['price'],refs[1]['price'])]:
            actual=Decimal(str(a))-Decimal(str(b));expected=Decimal(str(c))-Decimal(str(d));checks.append({'cell':'contribution.'+name,'actual':str(actual),'expected':str(expected),'pass':close(actual,expected)})
        tables=status['numeric_tables'];changes=tables['parameter_changes'];contributions=tables['parameter_contributions'];by_cell={}
        for row in contributions['rows']:
            key=tuple(row[k] for k in ('table','row','column'));by_cell[key]=by_cell.get(key,Decimal(0))+Decimal(row['delta'])
        sums=[close(row['delta'],by_cell.get(tuple(row[k] for k in ('table','row','column')),Decimal('NaN'))) for row in changes['rows']]
        item.update(checks=checks,all_frozen_cells_pass=all(c['pass'] for c in checks),comparison_cells=len(sums),contribution_sum_pass=sum(sums),available_params=status['available_params'],input_snapshot_bytes_equal=all((TRIAL/'exports'/PROJECT/run/n).read_bytes()==(ACTIVE/'exports'/PROJECT/source/n).read_bytes() for n in ('facts.json','pages.json','tables.json','research_records.json')))
        EVIDENCE.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8');print(label,'checks',len(checks),'pass',item['all_frozen_cells_pass'],'contributions',sum(sums),'/',len(sums),flush=True)
    service.analysis_pool.shutdown();return evidence
if __name__=='__main__':main()


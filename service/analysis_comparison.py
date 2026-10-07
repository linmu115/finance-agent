"""Generic cell-by-cell parameter differences; executed inside the sandbox wrapper."""
from decimal import Decimal, localcontext
import json
from pathlib import Path
if __package__:
    from .analysis_tables import collect_tables, numeric
    from .analysis_report import cell_column, convert, save_numeric_tables, write_csv, render_table
else:
    from analysis_tables import collect_tables, numeric
    from analysis_report import cell_column, convert, save_numeric_tables, write_csv, render_table


def differences(old,new):
    rows=[];units=[];skipped=[]
    for name,left in old.items():
        if name not in new:continue
        right=new[name];index={k:i for i,k in enumerate(right['row_keys'])}
        for i,key in enumerate(left['row_keys']):
            if key not in index:continue
            j=index[key]
            for column,before in left['rows'][i].items():
                after=right['rows'][j].get(column)
                if not numeric(before) or not numeric(after):continue
                old_col=cell_column(left,i,column);new_col=cell_column(right,j,column)
                if not (old_col.get('unit') or old_col.get('numeric')):continue
                ou,nu=old_col.get('unit'),new_col.get('unit')
                if (ou is None)!=(nu is None) or old_col.get('currency')!=new_col.get('currency'):
                    skipped.append({'table':name,'row':key,'column':column,'reason':'单位/币种无法对齐','old':old_col,'new':new_col});continue
                try:before=convert(before,ou,nu) if ou else str(before)
                except ValueError as exc:
                    skipped.append({'table':name,'row':key,'column':column,'reason':str(exc)});continue
                with localcontext() as context:
                    context.prec=50;delta=str(Decimal(str(after))-Decimal(before))
                info={k:new_col[k] for k in ('unit','currency','decimals') if new_col.get(k) is not None}
                delta_info={**info,**({'unit':'个百分点'} if nu=='%' else {})}
                rows.append({'table':name,'row':key,'column':column,'old':str(before),'new':str(after),'delta':delta})
                units.append({'old':info,'new':info,'delta':delta_info})
    columns={'table':{},'row':{},'column':{},'old':{'label':'旧值','per_cell_unit':True},'new':{'label':'新值','per_cell_unit':True},'delta':{'label':'变化','per_cell_unit':True}}
    return {'columns':columns,'rows':rows,'row_keys':['|'.join(r[k] for k in ('table','row','column')) for r in rows],'cell_units':units},skipped


def deliver_parameter_comparison(input_dir='/input',output_dir='/output'):
    source=Path(input_dir)/'parameter_comparison.json'
    if not source.exists():return
    data=json.loads(source.read_text(encoding='utf8'));output=Path(output_dir)
    current,warnings=collect_tables({p.name:p for p in output.iterdir() if p.suffix in ('.csv','.json')})
    changes,skipped=differences(data['baseline'],current)
    tables={'parameter_changes':changes}
    if data.get('order'):
        rows=[];units=[];previous=data['baseline']
        for step,(parameter,next_tables) in enumerate(zip(data['order'],[*data['steps'],current]),1):
            change,omitted=differences(previous,next_tables);skipped+=omitted
            rows += [{'step':str(step),'parameter':parameter,**r} for r in change['rows']];units+=change['cell_units'];previous=next_tables
        tables['parameter_contributions']={'columns':{'step':{},'parameter':{},**changes['columns']},'rows':rows,'cell_units':units,
            'row_keys':['|'.join(r[k] for k in ('parameter','table','row','column')) for r in rows]}
    if __package__:from .scenario_tables import scenario_tables
    else:from scenario_tables import scenario_tables
    versioned,context=scenario_tables(data['baseline'],current,data['baseline_id'],data['scenario_id'])
    tables={**versioned,**tables}
    (output/'scenario_bindings.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf8')
    save_numeric_tables(tables,output)
    for name,table in tables.items():write_csv(output/(name+'.csv'),table)
    text='# 基准 / 情景 / 差额\n\n'+context['meaning']+'\n\n'+('贡献按 '+' → '.join(data['order'])+' 顺序替换，贡献依赖顺序。' if data.get('order') else '新旧同名表逐单元比较。')
    for name,table in tables.items():text+='\n\n## '+name+'\n\n'+render_table(table)
    if skipped:text+='\n\n无法同单位比较的单元：\n'+json.dumps(skipped,ensure_ascii=False)
    (output/'parameter_changes.md').write_text(text,encoding='utf8')
    (output/'parameter_comparison_result.json').write_text(json.dumps({'parameters':data['parameters'],'order':data.get('order'),'skipped':skipped,'warnings':warnings,'cells_compared':len(changes['rows'])},ensure_ascii=False,indent=2),encoding='utf8')

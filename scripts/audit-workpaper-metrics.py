"""Report unclaimed current metric IDs for explicitly named, authorized inputs."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.standard_metrics import STANDARD_METRICS,workpaper_concepts
ap=argparse.ArgumentParser();ap.add_argument('--replay',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
datasets=[
 ('伊利2024年报',a.replay/'yili/app-data/finance.sqlite','374beac2-a970-4972-b210-e91018bbd6e6','d84573bf6b584e7e874faa4c6adf454a'),
 ('海尔2024年报',a.replay/'haier/app-data/finance.sqlite','d324c744-4113-4213-aa22-af3bb91a3c84','e7b0d9679ddc4b739f8f35ecb6dc6227'),
 ('茅台2024核心20页',ROOT/'tmp/round2-core-verified/app-data/finance.sqlite','c','0b0b3a8a432349e290b83d140e46c3c9'),
 ('茅台2024附注22页',ROOT/'tmp/round2-moutai-revalidated-v2/app-data/finance.sqlite','revalidate','206f8011338b4cbe860d63541f267c3d')]
results=[];md=['# 现有指标与底稿概念契约覆盖','',
 '只报告，不改指标或事实。未承接表示该 ID 没有精确映射到当前底稿概念；部分细项仍会被原表遍历、文本规则或来源表块消费，因此此清单不等于全部都是功能缺口。茅台使用此前 samples 同一原年报的两个已入库子集，非新增模型入库。','']
for name,path,project,did in datasets:
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[dict(r) for r in db.execute('SELECT * FROM current_financial_facts WHERE project_id=? AND document_id=?',(project,did))];db.close()
    metrics=defaultdict(list)
    for row in rows:metrics[row['metric']].append(row)
    unclaimed=[]
    for metric,fs in sorted(metrics.items()):
        if workpaper_concepts(metric):continue
        sources=[json.loads(f['source_json']) for f in fs]
        unclaimed.append({'metric':metric,'facts':len(fs),'standard_id':metric in STANDARD_METRICS,
          'tables':sorted({s['table_id'].rsplit(':',1)[-1] for s in sources}),
          'labels':sorted({s.get('normalization',{}).get('label','') for s in sources})})
    item={'name':name,'path':str(path),'document_id':did,'facts':len(rows),'distinct_metrics':len(metrics),
          'claimed_metrics':sum(bool(workpaper_concepts(k)) for k in metrics),'unclaimed_count':len(unclaimed),'unclaimed':unclaimed}
    results.append(item)
    md+=['## '+name,'',f'{len(rows)} 条当前事实，{len(metrics)} 个指标 ID；其中 {item["claimed_metrics"]} 个被概念契约接住，{len(unclaimed)} 个未承接。','',
         '|指标 ID|事实数|已有标准 ID|来源表|','|---|---:|---|---|']
    md += [f'|`{u["metric"]}`|{u["facts"]}|{"是" if u["standard_id"] else "否"}|'+', '.join(u['tables'])+'|' for u in unclaimed]
    md.append('')
a.out.mkdir(parents=True,exist_ok=True)
(a.out/'metric-inventory.json').write_text(json.dumps({'model_calls':0,'database_writes':0,'datasets':results},ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
(a.out/'metric-inventory.md').write_text('\n'.join(md),encoding='utf-8',newline='\n')
print(json.dumps([{k:v for k,v in r.items() if k not in ('unclaimed','path','document_id')} for r in results],ensure_ascii=False))

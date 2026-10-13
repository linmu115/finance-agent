"""Publish measured preparation results and evaluator-only X5 record pointers."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/evaluation/blind-eval-broker-resume-20261008'
PREP=ROOT/'data/evaluation/blind-eval-preparation-20261007'
BENCH=ROOT/'benchmark/blind-eval'
def read(p): return json.loads(p.read_text('utf8'))
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
report=read(OUT/'quality-summary.json')
jobs=report['documents']
assert len(jobs)==3 and all(j['run_status'] in ['completed','failed','cancelled'] for j in jobs)
old=read(ROOT/'data/evaluation/blind-eval-ingestion-20261007/preparation.json')
for j in jobs:
    assert j['prior_attempts']==next(o for o in old['jobs'] if o['key']==j['key'])['attempts']
assert report['usage_old_and_new']['prior']['input']['knownSum']==1528874
assert report['usage_old_and_new']['prior']['output']['knownSum']==10902
core=[]
for j in jobs:
    for record in j['current_yili_2024_forecasts']:
        s=record['source']
        eligible=(j['key']=='everbright_20240512' and s['page']==8 and s['row']==25) or (j['key']!='everbright_20240512' and s['page']==1)
        if eligible and record['metric'] in ['revenue','net_profit','net_profit_parent','eps']:
            core.append({'material':j['key'], **{k:record.get(k) for k in ['record_id','entity_id','metric','label','period','value','currency','scope','scenario','basis','dimensions','publisher','published_at','data_kind','quality']}, 'source':s, 'evaluation_use':'source net-profit value only, parent attribution unresolved' if j['key']=='everbright_20240512' and record['metric']=='net_profit' else 'usable source forecast with explicit basis/comparability limitations; not an annual-report actual'})
available={'observed_at':report['observed_at'],'project_id':jobs[0]['project_id'],'core_2024_forecasts':core,'annual_actuals':None,'record_selection':'Only named original-report rows; do not select comparable mean/median as Yili or mix Guosen post-cutoff forecasts. Preserve exact IDs, source coordinates, EPS basis and metadata.','limitations':['All scope fields are unspecified; do not infer accounting standard.','May source says net profit, not explicitly parent profit; November explicitly parent.','May matrix dimensions differ from November empty dimensions; do not strip them automatically to force K4 joins.','Huatai latest-diluted EPS and basic EPS labels require distinct treatment.','Huatai p3 cashflow17source rows/85records have wrong metric labels; use p1 core records only, never broad net_profit retrieval.','Actual annual report and formal cutoff/prompt approval still pending.']}
dump(OUT/'x5-available-records.json',available)
draft=read(PREP/'x5-freeze-draft.json')
draft['material_runtime_snapshot']={j['key']:{'document_id':j['document_id'],'run_id':j['run_id'],'coverage':j['coverage'],'run_status':j['run_status'],'coverage_complete':j['coverage_complete'],'semantic_acceptance':'not_complete; see preparation quality report'} for j in jobs}
draft['material_runtime_snapshot']['guosen_yili_20250716']={'document_id':'585db15e768043b7b465d1af7c690e90','role':'post_cutoff_excluded_from_expectations','preparation':'existing, unchanged by this run'}
draft['material_runtime_snapshot']['yili_2024']={'document_id':None,'status':'paused_until_N3_second_round'}
draft['available_record_manifest']='data/evaluation/blind-eval-broker-resume-20261008/x5-available-records.json'
draft['reference']['available_record_ids']=[{'material':r['material'],'metric':r['metric'],'record_id':r['record_id']} for r in core]
draft['reference']['actual_reference']['values']=None
draft['reference']['unresolved']=['Claude cutoff/prompt approval and N3 annual actuals are pending.','May profit attribution remains ambiguous; latest Huatai/November parent forecasts and CNY units are present.','Complete ingestion quality not accepted: coordinate gaps, entity/attribution mistakes and prose omissions remain; see20261008 report.']
draft['blockers']=['Yili2024 annual actuals remain paused; do not fill from old library or Guosen.','May parent-profit mapping not established; do not force same-basis profit revision.','Some non-core research records have entity/attribution errors; use original sources and precise row identity.','Cutoff and prompt still a proposal, not a frozen scoring key.']
dump(PREP/'x5-freeze-draft.json',draft)
refs=read(PREP/'reference-drafts.json');refs['X5']=draft['reference'];dump(PREP/'reference-drafts.json',refs)

names={'everbright_20240512':'光大 05-12','huatai_20241030':'华泰 10-30','everbright_20241104':'光大 11-04'}
lines=['# 三份研报断点恢复与入库质量 · 2026-10-08','', '在已上线 `2f65edc` 的3001上，从原项目、原文档和原会话恢复。每份只发一次获授权恢复请求，之后人工继续为0，由宿主按进度自动续跑。上一轮三次尝试及青啤账目原样保留；青啤与伊利2024年报未恢复。', '', '**候选表/正文处理覆盖与原文完整结构化分开判定。** 数值搬运可回放不代表主体、机构、指标和会计口径正确；保留具体缺失及原始停止原因。', '', '| 材料 | 宿主终态 | 表提交 | 正文处理页 | 自动续跑 | 用时 | 已定位待核格 | 其中语义未解格 | 原格回放 |', '|---|---|---:|---:|---:|---:|---:|---:|---:|']
for j in jobs:
    c=j['coverage'];seconds=j['duration_ms']/1000
    lines.append(f"| {names[j['key']]} | {j['run_status']} | {c['tables_completed']}/{c['tables_total']} | {c['pages_reviewed']}/{c['pages_total']} | {j['automatic_continuations']} | {int(seconds//60)}分{seconds%60:.3f}秒 | {j['review_cells_any_reason']} | {j['unresolved_semantic_cells']} | {j['raw_cell_replay']['passed']}/{j['raw_cell_replay']['total']} |")
lines+=['', '待核格按持久化issues中不同(table,row,column)计数；表级、页级疑点另列，不把它们当0格。尤其光大11-04有8张第二页整表只解析到表头，缺失原格数量未知；坐标格告警为0不代表无需复核。候选覆盖包含带具体缺口说明的提交，不能称全部数值完成入库。原格回放核对原串、坐标和numeric_span；另按保存倍率复算value，范围与结果见quality-summary.json。','', '## 新旧用量分列', '', 'CPA gpt-6-luna，实际各请求的low/high档位及阶段计数保存在quality-summary.json。缓存读取已含在总输入中；reasoning是输出细项，不再加总。实际CPA费用未知，目录估价保留在原始run/usage中，不当作账单。', '', '| 轮次/材料 | 总输入 | 未缓存输入 | 缓存读取 | 缓存写入 | 输出 | 其中推理 | 请求数 | 未知用量请求 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
fields=['input','uncachedInput','cacheRead','cacheWrite','output','reasoning','calls','unknownCalls']
for phase in ['prior','new']:
    for j in jobs:
        u=j['prior_attempts'][0]['usage'] if phase=='prior' else j['new_usage']
        lines.append('| '+('上轮' if phase=='prior' else '本轮')+' '+names[j['key']]+' | '+' | '.join(f"{u[k]:,}" for k in fields)+' |')
    u=report['usage_old_and_new'][phase]
    lines.append('| '+('上轮合计' if phase=='prior' else '本轮合计')+' | '+' | '.join(f"{u[k]['knownSum']:,}" for k in fields)+' |')
lines+=['', '本轮遇到CPA 503 auth_unavailable，由Pi原生重试处理；对应未知用量照常保留。没有另发继续或重试消息，没有把失败请求从准备账上扣除。新旧覆盖范围不同，不据此计算降费或优越性。', '', '## 原文抽查与实质缺口', '', '抽查7张完整原PDF页面，固定60个数值点；对照原图、源格与入库记录，57个已有数值点的数值、期间、主体、实际/预测身份与原文一致，3个光大11月p2样本无结构化记录；8个周报币种点未单独评分。两处metric命名差异经人工确认为合理命名，所带错误维度另列。之后的定向复查发现华泰85条标签错位，原60点统计不覆盖此缺陷，不能据其宣布质量通过。结果见source-review/spot-check-results.json；定性问题与PE舍入计算见source-review/manual-findings.json。', '', '- 光大五月：伊利2024预测净利润13,063百万元、EPS2.05，币种已从unknown改成CNY 与 CNY/share；净利润表头未明确归母，不能用相近历史值替代归属证据。整数PE与股价/EPS的显示精度相容，告警本身不证明数值错误。', '- 华泰：首页118,007百万元收入、12,235百万元归母及EPS1.92来源和单位可定位。但p2可比公司平均/中位EPS0.85/0.37被归给伊利主体与华泰作者预测，原文是可比公司Wind一致预期汇总；维度标签虽然保留，也不应成为伊利自身预测。第3页现金流表17行共85条记录标签错位：经营现金8,985百万元被记净利润，折旧3,562百万元被记财务费用。另有182条右半记录继承左半financial_item维度，已核实EPS带long_term_borrowings等错误。详见定向复查文件；这些问题不包含在程序仅标记的2个待核格中。', '- 光大十一月：首页118,170百万元收入、12,019百万元归母和EPS1.89可核对，归母身份有正文与p2原文支持。第二页8张财务及比率表仅留表头待核，当前只有首页40条数值；作者仅登记1/4，p1调整原因及业务风险等观点结构化保存不足。', '- 各份scope=unspecified不能自动解释为某会计准则；EPS最新摊薄/基本与未来年报实际值的分母仍须区分。原文可读与结构化完整是不同的资产状态。', '', '## X5判断与记录', '', '**可以形成带明确口径限制的预测侧底稿，不能宣告完整入库质量通过，也尚不能冻结完整X5金标。** 两家最近报告的三项核心预测已可从精确来源记录取数；五月仅EPS和源表净利润可引用，归母修正比较仍需保留限制。年报实际值继续留空，不从旧库或国信代填。只按主体/metric/period宽泛取数会混入华泰汇总行；同机构跨版还应保留不同dimensions，不为强行配对删元数据。', '', '| 材料 | 指标 | 入库标准化值（元/元每股） | record ID |', '|---|---|---:|---|']
for r in core: lines.append(f"| {names[r['material']]} | {r['metric']} | {r['value']} | `{r['record_id']}` |")
lines+=['', '精确币种、期间、机构日期、来源页/表/行/列、质量与维度保存在 [x5-available-records.json](../../data/evaluation/blind-eval-broker-resume-20261008/x5-available-records.json)，评测草案见 [X5_FREEZE_DRAFT.md](X5_FREEZE_DRAFT.md)。本轮没有把人工参考写入主库或模型输入。', '', '完整新账本、每份run/conversation/audit、处理状态、研究记录、原格回放和原图均在 `data/evaluation/blind-eval-broker-resume-20261008/`。原账本仍为 `data/evaluation/blind-eval-ingestion-20261007/`。']
for j in jobs:
    if j['stop_reason']:lines+=['',names[j['key']]+'停止原因：`'+j['stop_reason']+'`']
(BENCH/'BROKER_RESUME_20261008.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
dump(OUT/'final-verification.json',{'at':datetime.now(timezone.utc).isoformat(),'prior_attempts_unchanged':True,'prior_known_input':1528874,'prior_known_output':10902,'manual_followups':0,'all_runs_terminal':True,'annual_reports_resumed':False,'product_code_changes':False,'main_database_direct_writes':False,'formal_analysis_comparison_runs':0})
print(json.dumps({'documents':len(jobs),'X5_core_records':len(core),'old_usage_preserved':True,'new_usage':report['usage_old_and_new']['new']},ensure_ascii=False))

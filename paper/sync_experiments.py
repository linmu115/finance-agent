"""Import aggregate, host-scored reports into paper overrides; never import hidden gold.

Use --summary PATH (repeatable) only for selected reviewed model-run summary files.
No raw predictions, secrets, or evaluator gold are imported into the manuscript.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
parser=argparse.ArgumentParser()
parser.add_argument('--summary',type=Path,action='append',default=[])
args=parser.parse_args()
evidence={}
def record(path):
    path=path.resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Evidence must be in workspace')
    evidence[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    path=path.resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Report must be in workspace')
    if 'gold' in path.name or path.suffix!='.json':raise ValueError('Only aggregate JSON reports are accepted')
    raw=path.read_bytes();evidence[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(raw).hexdigest()
    return json.loads(raw)
updates={}
for name in ['benchmark/results/financial_pipeline.json','benchmark/results/acceptance-round1-error-analysis.json',
             'service/runs/parser-regression-tests.txt','service/runs/parser-concurrency-content.json',
             'service/runs/parser-concurrency-fixed-1/summary.json','service/runs/parser-concurrency-fixed-2/summary.json',
             'benchmark/results/service_boundaries.json','benchmark/results/prompt_injection.json',
             'sandbox/evidence/runtime.json','sandbox/evidence/recovery.json',
             'web/test-results/browser-contract-results.json','web/test-results/browser-live-results.json',
             'web/test-results/browser-agent-live-results.json']:
    record(ROOT/name)
manifest=read(ROOT/'benchmark/versions/v0.2/manifest.json')
counts=manifest['label_status_counts']
assert sum(counts.values())==120 and manifest['cases']==186 and manifest['source_materials_unchanged']
updates['curation_protocol']=('v0.1直接使用公开FinQA执行标签。开发检查发现其中存在公式、年份与数量级错误，也有材料不能唯一确定目标的问题。v0.2保留全部186题和原材料；120道FinQA由分工代理先独立阅读题目与允许材料、保存算式和材料哈希，再与旧标签比较。复核得到'
    f'{counts["verified"]}题核对一致、{counts["corrected"]}题纠正、{counts["ambiguous"]}题有歧义。'
    '这是独立代理复核，不是人工双标。歧义题不删除，要求返回证据不足并引用歧义依据；旧标签及旧评分单独保留，不用模型预测反向生成答案。')
baseline=read(ROOT/'benchmark/results/agent-2026-10-03T05-02-53-084Z-summary.json')
r=baseline['runs'][0];n=r['evaluated_cases'];correct=round(r['grounded_accuracy']*n)
updates['legacy_baseline']=(f'v0.1开发运行收到{r["received_predictions"]}/{n}份输出，答案及证据联合正确{correct}/{n}（{r["grounded_accuracy"]:.2%}），三并发墙钟耗时{r["wallTimeMs"]/1000:.3f}秒，共{r["modelCalls"]}次模型调用。'
    '输出覆盖不等于答对。该次运行采用旧FinQA标签，并记录运行期间有并发代码变化，因此只保留为开发失败基线，不属于冻结验收，也不能用于判定后续修订标签下的财务正确性。')
demo=read(ROOT/'benchmark/results/demo-latest.json')
verification=read(ROOT/'benchmark/results/demo-latest-artifacts/verification.json')
assert demo['status']=='completed' and verification['status']=='passed'
elapsed=(datetime.fromisoformat(demo['run']['finishedAt'].replace('Z','+00:00'))-datetime.fromisoformat(demo['run']['createdAt'].replace('Z','+00:00'))).total_seconds()
updates['demo_result']=(f'正式评测后另以parser 0.1.2重新上传三份完整年报，官方deepseek-flash经Pi自主查询2023与2024年合并营业收入、核查来源并调用容器制图，使用{demo["run"]["usage"]["calls"]}次模型调用，应用任务耗时{elapsed:.3f}秒。'
    f'产物生成后，宿主独立对照参考数据，{verification["passed"]}/{verification["total"]}个人民币元原值精确一致；绘图用亿元值保留4位小数，柱顶标签保留1位小数，不能称绘图显示全精度。中文、零基线及柱值经Codex代理视觉检查，未执行人工复核。参考库仅用于事后核对。此前演示保留为历史版本；两次单独演示均不计入186题成绩，也不改变S10人工检查缺失和整体验收未达标的结论。')
selftest=read(ROOT/'benchmark/results/reviewed-scorer-selftest.json')
updates['scorer_validation']=(f'评分器另完成{selftest["unittest_count"]}项方法测试，标准答案回代自检覆盖186题和{selftest["sufficient_evidence_sets_checked"]}组充分证据，检查公开输入中不含隐藏标签。'
    '这是评分程序一致性检查，不产生模型成绩，也不能单独证明复核标签没有语义错误。')
aborted=[]
for path in sorted((ROOT/'benchmark/results').glob('*-aborted.json')):
    event=read(path)
    if event.get('benchmarkVersion')=='0.2':aborted.append(event)
if aborted:
    detail=('其中美的完整295页报告的20次全新入库有6次触发ResizeImgError，均发生在模型工具调用之前。底层原因未完全复现，不能确证为内存不足。parser 0.1.2限制OCR线程、串行共享识别器并提前释放页面图像；随后两轮各4个并发完整入库全部完成，逐页文本与逐表内容与原成功解析一致。' if any('ResizeImgError' in e.get('abortReason','') for e in aborted) else '')
    updates['aborted_runs']=(f'另外保留{len(aborted)}次未完成的v0.2验收尝试及其已有记录。'+detail+
        '中止记录不计为完成轮次，也不从其中的成功样本推算整集准确率。本文正式三轮采用修复后重新冻结的版本，历史记录保留。')
records=[];all_formal=True
for path in args.summary:
    s=read(path if path.is_absolute() else ROOT/path)
    if s.get('status')!='completed':raise ValueError('Incomplete model summary; keep paper pending')
    if s.get('benchmarkVersion')!='0.2':raise ValueError('Model summary is not reviewed benchmark v0.2')
    runs=s.get('runs',[])
    if not runs:raise ValueError('No completed rounds in summary')
    formal=(s.get('split')=='acceptance' and len(s.get('caseIds',[]))==124 and s.get('repeat',0)>=3 and len(runs)>=3 and
        s.get('codeUnchangedDuringRun') is True and s.get('datasetUnchangedDuringRun') is True and s.get('agentInputIsolated') is True and not s.get('subset') and
        all('0.2' in r.get('benchmark','') for r in runs))
    all_formal=all_formal and formal
    for r in runs:
        if '0.2' not in r.get('benchmark',''):raise ValueError('Final import must use reviewed v0.2 scoring')
        records.append((s,r,formal))
if records:
    rows=[]
    for s,r,formal in records:
        n=r['evaluated_cases'];metrics=r['metrics'];answer=sum(m['n']*m['answer_accuracy'] for m in metrics.values())/n
        rows.append([('验收' if s['split']=='acceptance' else '开发')+f' 第{r["round"]}轮',str(n),f'{round(answer*n)}/{n}  {answer:.2%}',f'{round(r["grounded_accuracy"]*n)}/{n}  {r["grounded_accuracy"]:.2%}'])
    updates['model_runs']={'type':'table','headers':['运行','题数','答案正确','答案及证据正确'],'rows':rows,'caption':'表5 v0.2真实模型评测汇总'}
    minimum=min(r['grounded_accuracy'] for _,r,_ in records)
    total_time=sum(r['wallTimeMs'] for _,r,_ in records)/1000
    calls=sum(r['modelCalls'] for _,r,_ in records)
    gate=all(s.get('datasetGateAllRuns') is True for s,_,_ in records)
    formal_count=sum(formal for _,_,formal in records)
    dev_count=sum(s['split']=='dev' for s,_,_ in records)
    accept_count=sum(s['split']=='acceptance' for s,_,_ in records)
    unchanged=all(s.get('codeUnchangedDuringRun') is True and s.get('datasetUnchangedDuringRun') is True for s,_,_ in records)
    updates['model_result']=(f'v0.2包含开发集{dev_count}轮与验收集{accept_count}轮真实deepseek-flash评测，二者分列报告。开发集答案58/62、答案及证据54/62，达到其题型门槛；该开发分数不能替代正式124题表现。'
        +('导入记录的运行期间代码与数据哈希均保持不变。' if unchanged else '至少一份记录未满足代码与数据不变条件，必须区分解释。')
        +(f'满足完整冻结报告条件的验收运行共{formal_count}轮。' if formal_count else '当前尚未导入满足完整条件的三轮124题验收报告。')
        +('选定运行的数据门槛均通过。' if gate else '至少一项预设数据门槛未通过。')
        +'各轮具体结果见表5；单次真实年报演示及旧版开发基线另行列示。')
    track_rows=[]
    track_records=[entry for entry in records if entry[2]] or records
    names={'cn_extract':'中文提取','cn_calculate':'中文计算','cn_audit':'陈述核查','cn_abstain':'证据不足','cn_ocr':'图像读表','finqa_single':'FinQA单步','finqa_multi':'FinQA多步'}
    for track,label in names.items():
        values=[r['metrics'][track] for _,r,_ in track_records if track in r['metrics']]
        if not values:continue
        counts=sorted({v['n'] for v in values})
        def span(key):
            low=min(v[key] for v in values);high=max(v[key] for v in values)
            return f'{low:.2%}' if low==high else f'{low:.2%}—{high:.2%}'
        track_rows.append([label,'/'.join(map(str,counts)),span('answer_accuracy'),span('grounded_accuracy')])
    track_scope='正式验收各轮范围' if formal_count else '开发运行'
    updates['model_tracks']={'type':'table','headers':['题型','每轮题数','答案正确率','联合正确率'],'rows':track_rows,'caption':f'表6 v0.2分题型结果（{track_scope}）'}
    updates['model_report_identity']='选定模型报告：'+'；'.join(f'{s["name"]}，模型{s["model"]}，提示哈希{s["promptHash"][:12]}，代码哈希{s["code"]["hash"][:12]}' for s in {s['name']:s for s,_,_ in records}.values())+'。完整哈希见论文证据导入清单。'
    formal_records=[entry for entry in records if entry[2]]
    if formal_records:
        fs=formal_records[0][0];fr=[r for _,r,_ in formal_records]
        calls=sum(r['modelCalls'] for r in fr);seconds=sum(r['wallTimeMs'] for r in fr)/1000
        input_tokens=sum(r['inputTokens'] for r in fr);output_tokens=sum(r['outputTokens'] for r in fr)
        recall=[r['citation_recall'] for r in fr];precision=[r['citation_precision'] for r in fr]
        updates['model_costs']=(f'正式三轮共372次题目执行，仍是同一124题的重复测量；四并发累计墙钟时间{seconds:.3f}秒，模型调用{calls:,}次，输入{input_tokens:,}与输出{output_tokens:,}个token。'
            f'引用召回率为{min(recall):.2%}—{max(recall):.2%}，定位集合精确率为{min(precision):.2%}—{max(precision):.2%}。'
            '未据token用量推算费用。三轮FinQA单步均未达到85%答案门槛；首轮图像题未达到90%，第三轮多步题未达到75%。中文非图像四类的答案均正确，但部分引用仍失分。')
        updates['repeatability_result']=(f'按冻结容差比较每对轮次的有效数值或拒答结论，{round(fs["repeatConsistency"]*124)}/124题三轮一致（{fs["repeatConsistency"]:.2%}），低于95%门槛。'
            f'引用集合完全一致为{round(fs["citationSetConsistency"]*124)}/124（{fs["citationSetConsistency"]:.2%}），主要输出字段完全一致为{round(fs["exactPredictionConsistency"]*124)}/124（{fs["exactPredictionConsistency"]:.2%}）。'
            '一致性独立于正确性，相同错误也可能一致；失败结果不按有效数值结论计为一致。故代码与数据哈希稳定仍不足以证明回答稳定。')
        updates['failure_analysis']=('冻结后只读分析首轮：124份预测中123个任务完成、1个未产生有效最终模型结果。联合失分38题，其中20题答案契约失败，18题仅引用失败。'
            '前者包括13题在冻结政策要求歧义拒答时给标量，2题已拒答但原因码不符，1题无有效结果，1题混淆总负债与影响税率子集，1题符号约定差异，1题单位枚举错误，1题把正确年度利润金额标为期末时点。'
            '后者包括11题缺年表头、单位或区间边界，4题FinQA定位多加页码，1题把图片第1页当成报告第7页，2题额外引用未登记上下文。因此不能把全部失分归为心算或OCR识别错误。该分类仅覆盖首轮，未改标签、代码或原分数。')
    updates['model_score_limits']='引用分数仅核验预登记位置，不能等同于逐条语义相关性的人工裁决。首轮美的跨页表头及FinQA prospective method介绍均是合理上下文，却因未列入有效集合被扣分。另有一题询问亏损下降，公开约定称下降幅度非负并解释方向，冻结标签却要求负值；模型给正幅度并说明亏损实际扩大。该例存在公开规则与标签的解释冲突，不宜称算术错误。原评分保留，这些限制不被用来事后提高成绩。'
    acceptance=read(ROOT/'benchmark/results/acceptance.json')
    flag=lambda value:'满足' if value else '尚未满足'
    updates['system_acceptance_result']=(f'独立系统验收报告记录{acceptance["passed"]}/{acceptance["total"]}项工程条件通过；S10原值核对与代理视觉检查通过，规定的人工视觉检查未执行，故标为部分完成；S12重复结论一致性未达标。'
        f'运行门槛{flag(acceptance["runtime_gate_pass"])}，数据门槛{flag(acceptance["dataset_gate_pass"])}，完整系统验收{flag(acceptance["full_system_acceptance"])}。'
        '当前成果是可运行且完成评测的工程初版，尚未满足全部预设验收条件。')
(HERE/'experiment-update.json').write_text(json.dumps(updates,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'experiment-import.json').write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'source_reports':evidence,'model_summaries':[str(p) for p in args.summary],'model_rounds_imported':len(records),'aborted_runs_excluded':len(aborted),'contains_raw_predictions':False,'contains_hidden_gold':False},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Imported {len(evidence)} aggregate reports; {len(records)} model rounds')

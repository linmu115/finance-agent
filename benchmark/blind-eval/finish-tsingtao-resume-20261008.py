"""Write a terminal N1-only handoff from retained observations; never resumes a run."""
import json,re
from pathlib import Path
from datetime import datetime,timezone
import fitz
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/evaluation/blind-eval-tsingtao-resume-20261008'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
s=read(OUT/'preparation.json');j=s['job'];q=read(OUT/'quality-summary.json')
if j['status'] not in ['completed','failed','cancelled']:raise SystemExit('Run still active: no end report written')
facts=read(OUT/'facts.json');source=ROOT/'data/evaluation/blind-eval-preparation-20261007/sources/Tsingtao_2024_Annual.pdf';pdf=fitz.open(source)
gold=read(ROOT/'data/evaluation/blind-eval-preparation-20261007/reference-drafts.json')['H1_H2']
spot=[]
for metric,values in gold['raw'].items():
 for year,value in zip([2024,2023],values):
  matching=[f for f in facts if str(f['value'])==str(value) and f['year']==year]
  pages=[p for p in gold['source_pages'] if str(value) in re.sub(r'[\s,，]','',pdf[p-1].get_text())]
  spot.append({'reference_metric':metric,'year':year,'reference_CNY':value,'original_pdf_pages_with_literal_value':pages,'matching_current_records':[{'id':f['fact_id'],'metric':f['metric'],'label':f['source'].get('normalization',{}).get('label'),'scope':f['scope'],'currency':f['currency'],'period':f['period'],'source':{k:f['source'].get(k) for k in ['page','table_id','row','column']}} for f in matching],'verdict':'numeric_source_presence_only_not_semantic_acceptance'})
review={'at':datetime.now(timezone.utc).isoformat(),'source':str(source.relative_to(ROOT)),'basis_source':[{'PDF_page':p,'CAS_literal_present':'企业会计准则' in pdf[p-1].get_text()} for p in [80,91,92]],'IFRS_tagged_records_remaining':sum('IFRS' in f['scope'] for f in facts),'numeric_spotchecks':spot,'scope':'Checks originals and saved record identities without feeding references to the ingestion run. Presence of a matching value is not proof of metric/scope correctness; no complete semantic acceptance claimed.'}
dump('source-spotchecks.json',review)
ev=[json.loads(l) for l in (OUT/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
timeline=[]
for e in ev:
 if e['type']=='tool_result':
  d=e['data'].get('result',{}).get('data',{});c=d.get('coverage')
  if c:timeline.append({'at':e['at'],'tool':e['data'].get('name'),'coverage':c,'facts':d.get('fact_count'),'processing_id':d.get('processing_id')})
dump('coverage-timeline.json',timeline)
u=q['new_usage'] or {};c=q['coverage'] or {};old=q['old_10_attempts_usage'];coverage_text=f"{c.get('tables_completed','未知')}/{c.get('tables_total','未知')}"
reason=(j.get('error') or '未见宿主停滞事件；以run状态和保存的processing_state为准').split('剩余工作：')[0]
remaining_count=sum(len(x.get('pending_tables',[])) for x in (j.get('stall') or {}).get('remaining',[]))
lines=['# 青岛啤酒断点续跑回报（2026-10-08）','',f"运行状态：**{j['status']}**；完整资料准备：**{'覆盖完成，仍须区分语义验收' if q['preparation_complete'] else '未完成'}**。有效候选表覆盖 {coverage_text}，当前事实 {q['facts']} 条。仍有明确的准则误标，不能通过完整语义验收；不以表数或回放当成金融正确。",'',f"项目 `{j['projectId']}`；原文档 `{j['documentId']}`；原会话 `{j['conversationId']}`；本次 run `{j['runId']}`。只发一次恢复请求，人工继续 0，宿主自动续跑事件 {q['auto_continuations']} 次。开始 `{j['startedAt']}`，结束 `{j.get('finishedAt')}`，用时 {round(j['elapsedMs']/60000,2)} 分钟。开始部署 58a903c、3001 PID 56120；未重启/停止服务或Docker。",'',f"停止信息：`{json.dumps(reason,ensure_ascii=False)}`。剩余候选表 {remaining_count} 张。原始run、audit、conversation、processing状态均保留。",'','## 分开记账','', '| 项目 | 前10次原尝试（保持不变） | 本次恢复 |','|---|---:|---:|']
for field in ['calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls','cacheUnknownCalls','costUnknownCalls']:
 a=old[field];lines.append(f"| {field} | {a['known_sum']:,}（另有{a['unknown_runs']}次缺字段） | {u.get(field,'未知')} |")
lines+=['','旧账存在未知请求时，已知和不是完整总量；本次也按实际unknown字段披露。reasoning是输出的已报子项，不重复加总。`usage.costUsd`仅保留配置估计，CPA实际账单费用为null，入库支出不与分析比较混算。',f"旧账原文件摘要保持一致：{q['old_ledger_unchanged']}。本轮审计model_request条数 {q['model_request_count']}，用量calls {u.get('calls')}；差异如有保留，不强行补齐。",'','## 覆盖与质量','', '宿主判定无推进并停止，停止机制实际生效。具体阻点：非财务身份表只有证券代码，保留原格为待核后遭numeric_table_without_records拦截；自动续跑内连续两次脚本均为0条事实、3个问题（其中2个可定位待核单元格、1个表级拦截）。未绕过，也没有将代码当财务金额强行入库。另有未处理表261张，宿主返回的next_batch为表15；不能将单个阻点解释成所有剩余表都不可处理。', '', '名义核心表覆盖12/12，但这仅是产品返回的完成标志。抽查发现同一收入/归母利润/CFO金额并存CAS和IFRS记录，营业成本与营业利润目前匹配的记录仍只有IFRS标记；核心表完成不等于旧准则语义已经修好。', '',f"- 源PDF225页，解析表 {q['parsed_tables']} 张；当前processing候选分母 {c.get('tables_total')}。这两个数口径不同，不能以候选覆盖代称全部原文语义已核验。原始候选/已完成列表、core tables、待处理项保存在processing-states.json；中途有效覆盖曾回退，完整时间线保留。",f"- 当前原格/数值区间回放：{q['raw_cell_replay']}；按保存scale的缩放回放：{q['scaling_replay']}。这些只验证坐标、原值和缩放可重放。",f"- 已提交批次的可定位待核单元格 {q['review_cells_any_reason']}，批次问题分布 {q['issue_counts']}；未提交批次及未处理表不包含在这个单元格数中，不得理解为全篇剩余疑点总量。",f"- 当前scope分布：{q['scopes']}。原PDF p80、91、92明确CAS；IFRS标记仍有 {review['IFRS_tagged_records_remaining']} 条。没有手工改库。",'- 原文抽查记录在source-spotchecks.json：源准则声明及7项核心金额的两年原文存在性、入库record/口径/期间/坐标。数字能对上不等于利润归属、主体或准则正确。','', '所有held-out源文、轨迹与抽查细节保留在N1目录，未发给主线/N2/N3，未用于产品调试。若未完整完成或准则问题仍存，H1/H2正式材料不宣称就绪；等待Claude后续安排，不人工反复续推。','', '正式盲评方案（未执行）见 [FORMAL_EXECUTION_PLAN_20261008.md](FORMAL_EXECUTION_PLAN_20261008.md)。本轮run是准备支出，不是评测成绩。','', '账目与证据：[preparation.json](../../data/evaluation/blind-eval-tsingtao-resume-20261008/preparation.json)、[quality-summary.json](../../data/evaluation/blind-eval-tsingtao-resume-20261008/quality-summary.json)、[source-spotchecks.json](../../data/evaluation/blind-eval-tsingtao-resume-20261008/source-spotchecks.json)。','']
(ROOT/'benchmark/blind-eval/TSINGTAO_RESUME_20261008.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'status':j['status'],'complete':q['preparation_complete'],'coverage':c,'IFRS':review['IFRS_tagged_records_remaining'],'report':'benchmark/blind-eval/TSINGTAO_RESUME_20261008.md'},ensure_ascii=False))

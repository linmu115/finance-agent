"""N1-only terminal preparation receipt and source checks; never resumes ingestion."""
import json,hashlib,re
from collections import Counter
from decimal import Decimal
from datetime import datetime,timezone
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/evaluation/blind-eval-tsingtao-F1-20261008'
def read(p):return json.loads(p.read_text('utf-8-sig'))
def dump(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')
s=read(OUT/'preparation.json');q=read(OUT/'quality-summary.json');j=s['job'];facts=read(OUT/'facts.json')
if j['status'] not in ['completed','failed','cancelled']:raise ValueError('Preparation still running')
gold=read(ROOT/'data/evaluation/blind-eval-preparation-20261007/reference-drafts.json')['H1_H2']
pdf_path=ROOT/'data/evaluation/blind-eval-preparation-20261007/sources/Tsingtao_2024_Annual.pdf';pdf=fitz.open(pdf_path)
checks=[]
def check(key,value,year,period,pages,table=None):
    expected=Decimal(str(value));matching=[f for f in facts if Decimal(str(f['value']))==expected and f['year']==year and f['period']==period and f['currency']=='CNY' and f['scope']=='consolidated_CAS' and (table is None or f['source']['table_id'].endswith(':t'+str(table)))]
    source_pages=[n for n in pages if str(abs(value)) in re.sub(r'[\s,，]','',pdf[n-1].get_text())]
    checks.append({'reference_key':key,'expected_CNY':str(value),'year':year,'period':period,'original_pages_with_absolute_literal':source_pages,'records':[{'id':f['fact_id'],'metric':f['metric'],'scope':f['scope'],'currency':f['currency'],'quality':f['quality'],'source':f['source']} for f in matching],'presence_period_currency_scope_match':bool(matching and source_pages),'limits':'Numerical presence and saved identity checked. Metric labels and signed source meaning must also be read; no whole-document semantic pass inferred.'})
for metric,values in gold['raw'].items():
    for year,value in zip([2024,2023],values):check('annual.'+metric,value,year,str(year)+'-FY',[5,87,88,175])
for metric,values in gold['cash_bridge'].items():
    for year,value in zip([2024,2023],values):check('cash_bridge.'+metric,value,year,str(year)+'-FY',[175],252)
for metric,value in gold['Q4_2024_CNY'].items():check('Q4.'+metric,value,2024,'2024-Q4',[6],10)
source={'at':datetime.now(timezone.utc).isoformat(),'pdf_sha256':hashlib.sha256(pdf_path.read_bytes()).hexdigest(),'visual_pages_this_turn':[5,6,10,87,175],'CAS_literal_pages':[n for n in [80,91,92] if '企业会计准则' in pdf[n-1].get_text()],'IFRS_current':sum('IFRS' in f['scope'] for f in facts),'checks':checks,'cash_bridge_manual_review':'PDF p175 is consolidated, CNY yuan, current/prior annual columns; parentheses are negative; net profit and operating-payables rows independently inspected. PDF p6 quarter columns inspected. p87 consolidated columns separated from mother-company columns.','cause_source_review':'PDF p10 explicitly attributes revenue decline to volume; cost decline to volume and some raw-material costs; CFO increase to lower raw-material payments and tax payments. These statements do not establish that the entire payables adjustment is permanent or that Q4 weakness is explained by one seasonal cause.'}
dump('source-spotchecks.json',source)
old=q['old_10_attempts_usage'];prev=q['previous_58a_resume_usage'];now=q['new_usage'];fields=['calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls','cacheUnknownCalls','costUnknownCalls']
ledger={'category':'material_preparation_only','actual_CPA_bill':None,'old_10':old,'previous_58a_resume':prev,'current_F1':now,'old_10_unchanged':q['old_ledger_unchanged'],'current_stop_reason':'user_requested_readiness_pause','full_ingestion_complete':False,'known_token_sums_are_lower_bounds_when_unknown_calls_exist':True}
dump('separate-cost-ledger.json',ledger)
lines=['# 青啤 F1：达到题目材料门槛后暂停','',f"状态：**按用户最新授权暂停，完整入库未完成**。{q['coverage']['tables_completed']}/{q['coverage']['tables_total']} 张候选表已提交，剩余 {q['coverage']['tables_total']-q['coverage']['tables_completed']} 张；H1/H2 必需表已提交。整份 PDF 原文和全部解析表仍保留。",'',f"本次 run `{j['runId']}`；开始 `{j['startedAt']}`，暂停结束 `{j['finishedAt']}`，用时 {j['elapsedMs']/60000:.2f} 分钟。标准 cancel 接口仅用于本项目这次入库；宿主回执 cancelled/用户取消任务，业务原因另记为材料门槛暂停。不是 CPA 终态失败，也不是全量完成。",'','本轮只发一次断点恢复请求，人工继续为 0；宿主自动续跑事件 '+str(q['auto_continuations'])+'。本次在首轮循环内持续推进，按最新授权在末尾搁置 high 修复阶段前暂停，因此不声称验证了全篇自动续跑到底或末尾 high 修复。已有 high 请求不等于该末尾阶段。','', '| 用量字段 | 原10次（已知和） | 上次58a恢复 | 本次F1 |','|---|---:|---:|---:|']
for k in fields:lines.append(f"| {k} | {old[k]['known_sum']} | {prev.get(k,'未知')} | {now.get(k,'未知')} |")
lines+=['','以上三账分开，原账不改。未知请求不计为零，reasoning 是输出的已报子项，不能重复加总；目录估价保留在 JSON，CPA 实付费用未知。准备支出不混入阶段 A 参评分析。','','## 暂停时质量与资料状态','',f"- 当前事实 {q['facts']}；质量标记 {q['fact_quality']}。原格回放 {q['raw_cell_replay']}；缩放回放 {q['scaling_replay']}。",f"- 准则/合并范围分布 {q['scopes']}；当前 IFRS 标记 {source['IFRS_current']}。同一来源单元格多条映射数 {len(q['multiply_mapped_source_cells'])}；历史事实版本 {q['batch_accounting']['archived_fact_versions']}，不删除历史。",f"- 已提交批次的可定位待核单元格 {q['review_cells_any_reason']}；表级语义待核仍存在，零个可定位单元格不等于零疑点。完整表级问题、pending 列表和 quality 字段已保存。",f"- 原值/年度/币种/CAS合并身份存在性抽查 {sum(c['presence_period_currency_scope_match'] for c in checks)}/{len(checks)}；另实际打开 p5/p6/p10/p87/p175 核验原页。细节在 N1 私有 source-spotchecks.json。该范围不能推成全库语义验收。",'- 必需表含现金流补充资料表252，状态 needs_review；其具体语义说明保留，未手工改库。未提交附注不静默删除，详见 processing-states.json。','- 暂停后已确认无活动会话并保存 material-freeze-H-project.json、stage-C-H-freeze-receipt.json。H1/H2 最终金标与判分选择器须在发送正式题目之前冻结。','- held-out 材料、原轨迹、金额与抽查不交其他开发会话；只将类别门槛用于协调。评测结束后恢复剩余附注，当前不再次提交入库请求。','']
(OUT/'REPORT.md').write_text('\n'.join(lines),'utf8')
print(json.dumps({'status':j['status'],'pause_reason':'required_materials_submitted','reference_presence_checks':sum(c['presence_period_currency_scope_match'] for c in checks),'checks':len(checks),'IFRS':source['IFRS_current'],'report':str((OUT/'REPORT.md').relative_to(ROOT))},ensure_ascii=False))

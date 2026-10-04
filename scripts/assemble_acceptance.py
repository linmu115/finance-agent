"""Assemble explicit acceptance status from trusted reports; missing evidence never passes."""
import json, hashlib
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
def read(relative):
    p=ROOT/relative
    return json.loads(p.read_text("utf-8-sig")) if p.exists() else None
def proof(relative):
    p=ROOT/relative
    return {"path":relative,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} if p.exists() else {"path":relative,"missing":True}
def passed(x):return bool(x) and str(x.get("status","")).lower() in {"pass","passed"}
spec=read("benchmark/runtime_acceptance.json")
container=read("sandbox/evidence/runtime.json")
recovery=read("sandbox/evidence/recovery.json")
boundaries=read("benchmark/results/service_boundaries.json")
injection=read("benchmark/results/prompt_injection.json")
container_cases={x["id"]:x for x in (container or {}).get("cases",[])}
recovery_cases={x["id"]:x for x in (recovery or {}).get("cases",[])}
summaries=[]
for p in (ROOT/"benchmark/results").glob("agent-*-summary.json"):
    d=json.loads(p.read_text("utf-8"));d["_file"]=p.relative_to(ROOT).as_posix()
    if d.get("benchmarkVersion")=="0.2":summaries.append(d)
acceptance=next(iter(sorted((x for x in summaries if x.get("split")=="acceptance" and not x.get("subset") and x.get("model")=="deepseek-flash"),key=lambda x:x["createdAt"],reverse=True)),None)
dev=next(iter(sorted((x for x in summaries if x.get("split")=="dev" and not x.get("subset") and x.get("model")=="deepseek-flash"),key=lambda x:x["createdAt"],reverse=True)),None)
cases=[]
for item in spec["cases"]:
    rid=item["id"];evidence=[];details={};status="not_run"
    if rid in container_cases:
        observed=container_cases[rid];status="passed" if passed(observed) else "failed"
        evidence=[proof("sandbox/evidence/runtime.json")];details={"container_runs":[r.get("run_id") for r in observed.get("runs",[])],"visual_check":observed.get("visual_check")}
        if rid=="S10" and status=="passed":
            # Preserve the original evidence, while enforcing the specification's
            # separate human-review requirement. Agent vision is not human sign-off.
            status="partial"
            details.update({"numeric_check":"passed" if observed.get("reference_match") else "failed",
                            "agent_visual_check":observed.get("visual_check"),"human_review":"not_run",
                            "scope":"原值比对与Codex视觉核对已完成；原规范要求的人工视觉检查尚未执行。"})
    elif rid in {"S08","S11"}:
        observed=recovery_cases.get(rid);app_events=[e for e in (boundaries or {}).get("events",[]) if e.get("check")==rid]
        good=passed(observed) and passed(boundaries) and bool(app_events)
        status="passed" if good else "failed" if observed or boundaries else "not_run"
        evidence=[proof("sandbox/evidence/recovery.json"),proof("benchmark/results/service_boundaries.json")]
        details={"service_events":len(app_events),"container_probe":(observed or {}).get("scope"),"scope":"应用服务文档/查询边界及解析恢复；实际容器产物隔离、任务中断恢复"}
    elif rid=="S09":
        status="passed" if passed(injection) else "failed" if injection else "not_run"
        evidence=[proof("benchmark/results/prompt_injection.json")];details=(injection or {}).get("checks",{})
    elif rid=="S12":
        if acceptance:
            complete=acceptance.get("repeat")==3 and len(acceptance.get("runs",[]))==3
            consistent=(acceptance.get("repeatConsistency") or 0)>=.95
            unchanged=acceptance.get("codeUnchangedDuringRun") is True and acceptance.get("datasetUnchangedDuringRun") is True
            status="passed" if complete and consistent and unchanged else "failed"
            evidence=[proof(acceptance["_file"])]
            details={"runs":acceptance.get("repeat"),"consistency":acceptance.get("repeatConsistency"),"code_unchanged":unchanged,"worst_grounded_accuracy":acceptance.get("worstGroundedAccuracy"),"dataset_gates_all_runs":acceptance.get("datasetGateAllRuns")}
    cases.append({"id":rid,"name":item["name"],"status":status,"criterion":item["pass"],"evidence":evidence,"details":details})
components=[]
for name,file in [
    ("前端交互契约（固定API响应）","web/test-results/browser-contract-results.json"),
    ("真实上传、解析及原文预览","web/test-results/browser-live-results.json"),
    ("DeepSeek真实浏览器Agent联调","web/test-results/browser-agent-live-results.json"),
    ("三轮完整财报确定性解析","benchmark/results/financial_pipeline.json"),
    ("三份完整财报DeepSeek分析与图表原值复核","benchmark/results/demo-artifacts/verification.json"),
    ("当前版本三份完整财报分析与图表原值复核","benchmark/results/demo-latest-artifacts/verification.json"),
    ("当前版本真实示例浏览器只读复核","web/test-results/demo-latest-live-verification.json"),
]:
    result=read(file)
    if result:
        total=len(result.get("checks",[])) or result.get("total",0)
        count=result.get("passed",0)
        ok=count==total and total>0 and not result.get("failed")
        components.append({"name":name,"status":"passed" if ok else "failed","passed":count,"total":total,"evidence":[proof(file)],"scope":result.get("scope") or result.get("mode")})
chart=read("sandbox/evidence/agent-chart.json")
if chart:components.append({"name":"DeepSeek→分析容器→图表产物","status":"passed" if passed(chart) else "failed","evidence":[proof("sandbox/evidence/agent-chart.json")]})
runtime_ok=all(x["status"]=="passed" for x in cases)
data_ok=bool(acceptance and acceptance.get("datasetGateAllRuns"))
result={"name":"金融研究系统逐项验收","runtime":True,"status":"passed" if runtime_ok and data_ok else "failed" if any(x["status"]=="failed" for x in cases) or (acceptance and not data_ok) else "running",
 "updatedAt":datetime.now(timezone.utc).isoformat(),"model":"DeepSeek-V4.1-Flash（官方API：deepseek-flash）",
 "passed":sum(x["status"]=="passed" for x in cases),"partial":sum(x["status"]=="partial" for x in cases),"total":len(cases),"runtime_gate_pass":runtime_ok,"dataset_gate_pass":data_ok,"full_system_acceptance":runtime_ok and data_ok,
 "cases":cases,"components":components,
 "dataset":{"development":None if not dev else {"report":dev["_file"],"gate":dev.get("datasetGateAllRuns"),"runs":dev.get("runs")},"acceptance":None if not acceptance else {"report":acceptance["_file"],"gate":data_ok,"runs":acceptance.get("runs"),"repeatConsistency":acceptance.get("repeatConsistency")}},
 "benchmarkVersion":"0.2",
 "limitations":["公开年报与公开FinQA存在预训练污染可能，本数据集属于公开回归验收，不是隐藏竞赛测试集。",
 "标签、原文与图表由Codex代理复核，未包含人类双重标注或人工验收签字；S10图表检查为代理视觉核对。",
 "采用本机单用户部署；项目边界由宿主服务与容器强制执行，未证明可用于敌对多租户环境。",
 "DeepSeek官方API模型名为服务端别名，已记录调用配置与时间；无法保证服务方永不更新别名后的模型权重。",
 "未提供独立Embedding供应商凭据，当前真实检索基线为关键词检索；远程向量API仅有协议/降级测试，不计作真实向量模型效果验证。"]}
target=ROOT/"benchmark/results/acceptance.json";target.write_text(json.dumps(result,ensure_ascii=False,indent=2),"utf-8")
print(json.dumps({"report":str(target),"status":result["status"],"runtime_passed":result["passed"],"runtime_total":len(cases),"full_system_acceptance":result["full_system_acceptance"]},ensure_ascii=False))

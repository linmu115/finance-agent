"""Actual main-app model -> Pi tools -> Docker -> HTTP artifact acceptance.

Does not read/change API keys or author the model's Python analysis code.
"""
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import uuid

BASE="http://127.0.0.1:3001"
OUT=Path("sandbox/evidence")
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path,body=None,method=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode("utf-8")
    request=urllib.request.Request(BASE+path,data=data,method=method,
                                   headers={"Content-Type":"application/json"} if data else {})
    with OPENER.open(request,timeout=45) as response:
        return json.load(response)


def main():
    OUT.mkdir(exist_ok=True)
    report={"started_at":time.time(),"status":"RUNNING","method":"actual configured application model; no model code supplied by harness"}
    def save(): (OUT/"agent-chart.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    project=api("/api/projects",{"name":"容器端到端验收 "+time.strftime("%H:%M:%S")},"POST")
    report["project_id"]=project["id"]
    csv="公司,指标,币种,单位,口径,2023,2024\n验收示例公司,营业收入,CNY,元,合并,120000000,150000000\n"
    raw=csv.encode("utf-8")
    source=OUT/"agent-chart-input.csv";source.write_bytes(raw)
    report["input"]={"name":source.name,"sha256":hashlib.sha256(raw).hexdigest(),
                     "kind":"explicit synthetic acceptance fixture","expected_values_cny":[120000000,150000000]}
    boundary="finance-"+uuid.uuid4().hex
    multipart=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"agent-chart-input.csv\"\r\nContent-Type: text/csv\r\n\r\n".encode()+raw+f"\r\n--{boundary}--\r\n".encode())
    request=urllib.request.Request(BASE+f"/api/projects/{project['id']}/uploads",data=multipart,
                                   headers={"Content-Type":"multipart/form-data; boundary="+boundary},method="POST")
    with OPENER.open(request,timeout=45) as response:uploaded=json.load(response)
    report["uploaded"]=uploaded
    ids=[document["id"] for document in uploaded["documents"]]
    conversation=api(f"/api/projects/{project['id']}/conversations",{},"POST")
    report["conversation_id"]=conversation["id"]
    prompt=("请只依据上传CSV，先调用工具读取实际表格，再调用run_analysis在隔离容器内绘制2023、2024两年的营业收入柱状对比图。"
            "金额统一显示为亿元，纵轴从0开始；中文标题和坐标使用容器预装的Noto Sans CJK JP字体。"
            "必须真正生成revenue.png和chart_data.json，不能只给代码或口头描述。"
            "chart_data.json格式为包含currency、source_unit、display_unit、years、values_cny的JSON对象；years按2023、2024排序，values_cny保持原始元金额。"
            "不要自行补数据；等待容器任务到终态后返回两份可下载产物，并简述趋势。")
    submitted=api(f"/api/conversations/{conversation['id']}/messages",{"content":prompt,"documentIds":ids},"POST")
    report["agent_run_id"]=submitted["runId"];report["prompt"]=prompt;save()
    deadline=time.monotonic()+15*60
    last=None
    while time.monotonic()<deadline:
        run=api("/api/runs/"+submitted["runId"])
        report["agent_run"]=run;save()
        stage=(run.get("status"),run.get("stage"),len(run.get("tools",[])))
        if stage!=last: print("Agent",stage,flush=True);last=stage
        if run["status"] in {"completed","failed","cancelled"}:break
        time.sleep(2)
    else:
        report.update(status="FAIL",reason="Agent exceeded acceptance observation window");save();return 2
    conversation=api("/api/conversations/"+conversation["id"])
    report["conversation"]=conversation
    assistant=next((message for message in reversed(conversation["messages"]) if message.get("role")=="assistant"),{})
    artifacts=assistant.get("artifacts",[])
    downloaded=[]
    for artifact in artifacts:
        url=artifact.get("url","")
        if not url.startswith("/api/projects/"+project["id"]+"/artifacts/"):continue
        with OPENER.open(BASE+url,timeout=45) as response:
            content=response.read();mime=response.headers.get("Content-Type","");status=response.status
        name=artifact["name"]
        if "/" in name or "\\" in name:continue
        target=OUT/("agent-"+name);target.write_bytes(content)
        downloaded.append({"name":name,"url":url,"http_status":status,"mime_type":mime,
                           "size":len(content),"sha256":hashlib.sha256(content).hexdigest(),"file":str(target)})
    report["downloads"]=downloaded
    png=next((item for item in downloaded if item["name"]=="revenue.png"),None)
    json_file=next((item for item in downloaded if item["name"]=="chart_data.json"),None)
    valid_png=False
    if png:valid_png=Path(png["file"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and png["size"]>1000
    numbers=False
    if json_file:
        data=json.loads(Path(json_file["file"]).read_text(encoding="utf-8"))
        report["chart_data"]=data
        from decimal import Decimal
        numbers=data.get("years")==[2023,2024] and [Decimal(str(v)) for v in data.get("values_cny",[])]==[Decimal(120000000),Decimal(150000000)] and data.get("currency")=="CNY" and data.get("source_unit")=="元" and data.get("display_unit")=="亿元"
    tool_names=[tool.get("name") or tool.get("toolName") for tool in run.get("tools",[])]
    report["checks"]={"agent_completed":run["status"]=="completed","run_analysis_called":"run_analysis" in tool_names,
                      "analysis_status_polled":"get_analysis_status" in tool_names,"png_http_verified":valid_png,
                      "chart_data_matches_uploaded_source":numbers}
    report["status"]="PASS" if all(report["checks"].values()) else "FAIL"
    report["finished_at"]=time.time();save()
    print(json.dumps({"status":report["status"],"checks":report["checks"]},ensure_ascii=True),flush=True)
    return 0 if report["status"]=="PASS" else 2


if __name__=="__main__":
    raise SystemExit(main())


"""Trusted host checks: project isolation and a real killed parser followed by recovery."""
from __future__ import annotations
import hashlib, json, multiprocessing, os, shutil, sqlite3, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.core import FinanceService

def child_ingest(root, report, pipe):
    service=FinanceService(root)
    service.create_project("restart","Restart probe")
    target=Path(root)/"uploads"/"moutai_2024.pdf"
    shutil.copyfile(report,target)
    result=service.ingest_document("restart",str(target),target.name)
    pipe.send({"pid":os.getpid(),**result["data"]})
    while True:
        state=service.get_ingestion_status("restart",result["data"]["job_id"])["data"]
        pipe.send({"state":state})
        time.sleep(.1)

def close(service):
    for name in ("pool","analysis_pool","embedding_pool"):
        getattr(service,name).shutdown(wait=True,cancel_futures=True)

def wait(service,project,job):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        result=service.get_ingestion_status(project,job)["data"]
        if result["state"] in {"ready","needs_review","failed","cancelled"}:
            assert result["state"] in {"ready","needs_review"},result
            return result
        time.sleep(.1)
    raise TimeoutError("Parser recovery did not finish")

def main():
    run_id="boundary-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:8]
    base=ROOT/"benchmark"/"runs"/run_id
    base.mkdir(parents=True)
    events=[]
    def log(check,**data):
        events.append({"at":datetime.now(timezone.utc).isoformat(),"run_id":run_id,"check":check,**data})
        (base/"events.json").write_text(json.dumps(events,ensure_ascii=False,indent=2),"utf-8")
    service=FinanceService(base/"isolation")
    try:
        for project in ("alpha","beta"):service.create_project(project,project)
        upload=service.store.root/"uploads"/"private.csv"
        upload.write_text("指标,2024年,2023年,单位\n营业收入,666,123,元\n","utf-8")
        doc=service.ingest_document("alpha",str(upload),upload.name)["data"]
        wait(service,"alpha",doc["job_id"])
        fact=service.get_financial_metrics("alpha",["revenue"])["data"]["items"][0]
        probes=[
            ("get_document",lambda:service.get_document("beta",doc["document_id"])),
            ("get_source_page",lambda:service.get_source_page("beta",doc["document_id"],1)),
            ("get_source_table",lambda:service.get_source_table("beta",doc["document_id"])),
            ("get_ingestion_status",lambda:service.get_ingestion_status("beta",doc["job_id"])),
            ("cancel_ingestion",lambda:service.cancel_ingestion("beta",doc["job_id"])),
            ("get_financial_metrics",lambda:service.get_financial_metrics("beta",["revenue"],document_id=doc["document_id"])),
            ("calculate_financial_metrics",lambda:service.calculate_financial_metrics("beta","ratio",{"numerator":{"fact_id":fact["fact_id"]},"denominator":"1"})),
            ("run_analysis",lambda:service.run_analysis("beta","print('no foreign data')",[doc["document_id"]])),
            ("metric_injection",lambda:service.get_financial_metrics("beta",["revenue');DROP TABLE facts;--"])),
        ]
        for name,probe in probes:
            try:probe()
            except ValueError as error:log("S08",tool=name,project_id="beta",document_id=doc["document_id"],denied=True,error=str(error))
            else:raise AssertionError(name+" accepted a forbidden reference")
        assert service.search_evidence("beta","666 营业收入")["data"]["items"]==[]
        assert service.get_financial_metrics("beta",["revenue"])["data"]["items"]==[]
        repeated=service.ingest_document("alpha",str(upload),"renamed.csv")["data"]
        assert repeated["document_id"]==doc["document_id"]
        assert len(service.list_documents("alpha")["data"]["items"])==1
        log("S08",query_isolated=True,foreign_fact_absent=True)
        log("S11",duplicate_upload_same_id=True,document_id=doc["document_id"])
    finally:close(service)
    report=ROOT/"benchmark"/"agent_input"/"reports"/"moutai_2024.pdf"
    if not report.exists():
        candidates=list((ROOT/"benchmark").glob("**/reports/moutai_2024.pdf"))
        report=next(p for p in candidates if "runs" not in p.parts)
    receiver,sender=multiprocessing.Pipe(duplex=False)
    child=multiprocessing.Process(target=child_ingest,args=(str(base/"recovery"),str(report),sender))
    child.start();first=None;observed=None;deadline=time.monotonic()+60
    try:
        while time.monotonic()<deadline:
            if receiver.poll(.2):
                message=receiver.recv()
                if "pid" in message:first=message
                if isinstance(message.get("state"),dict):observed=message["state"]
                if observed and observed["state"]=="parsing" and observed["progress"]>=.02:break
            if not child.is_alive():raise RuntimeError("Parser exited before interruption")
        assert first and observed and observed["state"]=="parsing",observed
        log("S11",operation="before_real_process_terminate",pid=child.pid,job_id=first["job_id"],state=observed)
        child.terminate();child.join(10);assert not child.is_alive()
        log("S11",operation="real_process_terminated",pid=child.pid,exitcode=child.exitcode)
    finally:
        if child.is_alive():child.terminate();child.join(10)
        receiver.close();sender.close()
    service=FinanceService(base/"recovery")
    try:
        old=service.get_ingestion_status("restart",first["job_id"])["data"]
        assert old["state"]=="failed" and old["error"]=="service_restarted",old
        target=service.store.root/"uploads"/"moutai_2024.pdf"
        retry=service.ingest_document("restart",str(target),target.name)["data"]
        assert retry["document_id"]==first["document_id"]
        final=wait(service,"restart",retry["job_id"])
        duplicate=service.ingest_document("restart",str(target),target.name)["data"]
        assert duplicate["document_id"]==first["document_id"]
        assert len(service.list_documents("restart")["data"]["items"])==1
        with service.store.connect() as db:
            duplicates=db.execute("SELECT count(*) FROM (SELECT document_id,page,count(*) n FROM pages GROUP BY document_id,page HAVING n>1)").fetchone()[0]
            facts=db.execute("SELECT count(*) FROM facts").fetchone()[0]
            pages=db.execute("SELECT count(*) FROM pages").fetchone()[0]
        assert duplicates==0 and pages==143 and facts>0
        log("S11",operation="recovered_real_parse",old_job_id=first["job_id"],new_job_id=retry["job_id"],
            document_id=first["document_id"],prior_state=old["state"],final_state=final["state"],
            documents=1,pages=pages,facts=facts,duplicate_pages=duplicates,input_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    finally:close(service)
    result={"name":"真实项目隔离与解析中断恢复","runtime":True,"status":"passed","scope":"S08 document/query/fact boundaries and S11 parser process termination/recovery; container artifacts/export checked separately",
        "run_id":run_id,"events":events,"evidence_path":str(base.relative_to(ROOT))}
    out=ROOT/"benchmark"/"results"/"service_boundaries.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),"utf-8")
    print(json.dumps({"status":"passed","report":str(out),"events":len(events)},ensure_ascii=False))
if __name__=="__main__":main()

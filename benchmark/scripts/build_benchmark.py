"""Build a versioned local regression benchmark. No LLM or paid API calls."""
from collections import Counter
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "agent_input"
EVAL = ROOT / "evaluator"
LABELS = {"revenue":"营业收入", "net_profit_parent":"归属于上市公司股东的净利润", "operating_cash_flow":"经营活动产生的现金流量净额", "assets":"总资产", "equity_parent":"归属于上市公司股东的净资产"}

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")

def decimal_text(x):
    return format(Decimal(x), "f")

def execute_finqa(program):
    """Deliberately restricted arithmetic subset; no eval, code execution or table shortcuts."""
    result=[]
    steps=re.findall(r"(add|subtract|multiply|divide|exp)\(([^(),]+),\s*([^(),]+)\)",program)
    if not steps or len(steps) != program.count("("):
        raise ValueError("outside supported arithmetic subset")
    def val(s):
        s=s.strip()
        if s.startswith("#"):
            return result[int(s[1:])]
        s=s.replace("const_m1","-1").replace("const_","")
        return Decimal(s[:-1])/100 if s.endswith("%") else Decimal(s)
    with localcontext() as ctx:
        ctx.prec=40
        for op,a,b in steps:
            a,b=val(a),val(b)
            if op=="add": c=a+b
            elif op=="subtract": c=a-b
            elif op=="multiply": c=a*b
            elif op=="divide": c=a/b
            else:
                if b!=int(b) or abs(b)>12: raise ValueError("unsupported exponent")
                c=a**int(b)
            if not c.is_finite(): raise ValueError("nonfinite")
            result.append(c)
    return result[-1],len(steps)

def main():
    INPUT.mkdir(parents=True,exist_ok=True)
    cases=[]; gold=[]; facts=[]; excluded=Counter()
    for path in (ROOT/"sources/reports").glob("*.pdf"):
        dest=INPUT/"reports"/path.name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,dest)
    def add(c,g):
        cases.append(c); gold.append({"id":c["id"],"track":c["track"],"split":c["split"],**g})
    companies=json.loads((EVAL/"curated_facts.json").read_text(encoding="utf-8"))["companies"]
    for co in companies:
        doc=co["id"]; name=co["name"]; mult=Decimal(co["multiplier"])
        values={k:[Decimal(v)*mult for v in vv] for k,vv in co["values"].items()}
        def make_case(suffix,track,question):
            return {"id":doc+"_"+suffix,"split":co["split"],"track":track,"language":"zh", "group_id":doc,"question":question,"allowed_assets":["reports/"+doc+".pdf"], "source_ids":[doc],"response_contract":"numeric-v1","max_citations":8}
        def refs(*metrics): return sorted({f"{doc}:p{co['pages'][m]}" for m in metrics})
        for metric, vv in values.items():
            for i,year in enumerate([2024,2023]):
                period=str(year)+("-12-31" if metric in ["assets","equity_parent"] else "-FY")
                fid=f"{doc}:{metric}:{year}"
                facts.append({"fact_id":fid,"document_id":doc,"company":name,"ticker":co["ticker"],"metric":metric,"period":period,"value_cny":decimal_text(vv[i]),"source_value":co["values"][metric][i],"source_unit":co["source_unit"],"currency":"CNY","scope":"consolidated_CAS","pdf_page":co["pages"][metric]})
                q=f"依据{name}2024年年报的主要会计数据表，提取{year}年{'末' if metric in ['assets','equity_parent'] else ''}{LABELS[metric]}。按中国企业会计准则合并口径，统一以人民币元输出，并引用该表所在的PDF物理页码（从1开始）。"
                add(make_case(f"extract_{metric}_{year}","cn_extract",q),{"status":"ok","answer":decimal_text(vv[i]),"unit":"CNY","period":period,"scope":"consolidated_CAS","citations":refs(metric),"abs_tolerance":"0.01","rel_tolerance":"0","fact_ids":[fid]})
        for metric in ["revenue","net_profit_parent","operating_cash_flow"]:
            current,previous=values[metric]; ans=(current/previous-1)*100
            q=f"依据{name}2024年年报主要会计数据表，使用原始金额重新计算{LABELS[metric]}2024年相对2023年的同比变化率。按中国企业会计准则合并口径，以百分数数值输出（例如9.44代表9.44%），保留至少两位小数，引用原始数据页。"
            add(make_case("growth_"+metric,"cn_calculate",q),{"status":"ok","answer":decimal_text(ans),"unit":"percent","period":"2024-FY","scope":"consolidated_CAS","citations":refs(metric),"abs_tolerance":"0.005","rel_tolerance":"0","formula":f"({current}/{previous}-1)*100"})
        ans=values["operating_cash_flow"][0]/values["net_profit_parent"][0]
        add(make_case("cash_profit_ratio","cn_calculate",f"依据{name}2024年年报主要会计数据表，计算2024年经营现金流净额除以归母净利润的比值。采用中国企业会计准则合并口径，输出倍数，保留至少4位小数，引用原始数据页。"),{"status":"ok","answer":decimal_text(ans),"unit":"ratio","period":"2024-FY","scope":"consolidated_CAS","citations":refs("operating_cash_flow","net_profit_parent"),"abs_tolerance":"0.00005","rel_tolerance":"0","formula":f"{values['operating_cash_flow'][0]}/{values['net_profit_parent'][0]}"})
        for label,claim,truth in [
            ("true_revenue",values["revenue"][0],True),
            ("false_year",values["revenue"][1],False),
            ("false_unit",values["revenue"][0]/1000,False),
            ("true_profit",values["net_profit_parent"][0],True)]:
            metric="net_profit_parent" if label=="true_profit" else "revenue"
            q=f"核查：‘{name}2024年{LABELS[metric]}为{claim}人民币元（中国企业会计准则合并口径）’。以2024年年报主要会计数据表为准，answer输出布尔值；无论正确与否，corrected_value均给出正确金额（元），并引用证据页。"
            c=make_case(label,"cn_audit",q); c["response_contract"]="audit-v1"
            add(c,{"status":"ok","answer":truth,"corrected_value":decimal_text(values[metric][0]),"unit":"CNY","period":"2024-FY","scope":"consolidated_CAS","citations":refs(metric),"abs_tolerance":"0.01","rel_tolerance":"0"})
        for year in [2026,2027]:
            c=make_case("missing_"+str(year),"cn_abstain",f"仅根据提供的{name}2024年年报，给出{year}年全年已经实现、经审计的营业收入。不得使用外部资料或预测；证据不足时返回insufficient_evidence，answer设为null，reason_code设为period_not_in_source。")
            c["response_contract"]="abstain-v1"
            add(c,{"status":"insufficient_evidence","answer":None,"reason_code":"period_not_in_source","citations":[]})
        image_name={"moutai_2024":"moutai_p5","midea_2024":"midea_p9","yili_2024":"yili_p7"}[doc]
        dest=INPUT/"scans"/(image_name+".png");dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/"review/pages"/(image_name+".png"),dest)
        for metric in ["revenue","net_profit_parent"]:
            c=make_case("ocr_"+metric,"cn_ocr",f"仅从所附年报页面图像读取{name}2024年{LABELS[metric]}，使用中国企业会计准则合并口径，转换为人民币元。图像对应{doc}的PDF第{co['pages'][metric]}页。")
            c["allowed_assets"]=["scans/"+image_name+".png"]
            add(c,{"status":"ok","answer":decimal_text(values[metric][0]),"unit":"CNY","period":"2024-FY","scope":"consolidated_CAS","citations":refs(metric),"abs_tolerance":"0.01","rel_tolerance":"0"})
    # FinQA inputs use a strict whitelist: no qa, model_input, retriever labels or programs.
    raw={s:json.loads((ROOT/f"sources/finqa/{s}.json").read_text(encoding="utf-8")) for s in ["dev","test"]}
    dev_companies=set(); selections=[]
    for upstream,split,target in [("dev","dev",40),("test","acceptance",80)]:
        buckets={"single":[],"multi":[]}
        for row in raw[upstream]:
            try:
                qa=row["qa"]; computed,steps=execute_finqa(qa["program"])
                expected=Decimal(str(qa["exe_ans"]))
                if not expected.is_finite() or abs(computed-expected)>Decimal("0.000006"): raise ValueError("gold execution mismatch")
                if not qa.get("gold_inds"): raise ValueError("missing gold evidence")
                for ev in qa["gold_inds"]:
                    kind,idx=ev.split("_"); idx=int(idx)
                    if kind=="table": assert 0<=idx<len(row["table"])
                    elif kind=="text": assert 0<=idx<len(row["pre_text"])+len(row["post_text"])
                    else: raise ValueError("unknown evidence")
                company=row["id"].split("/")[0]
                if split=="acceptance" and company in dev_companies: continue
                buckets["single" if steps==1 else "multi"].append((row,computed,company))
            except Exception as exc:
                excluded[str(exc) or type(exc).__name__]+=1
        for difficulty,rows in buckets.items():
            rows.sort(key=lambda e:hashlib.sha256(("finance-bench-v0.1:"+e[0]["id"]).encode()).hexdigest())
            assert len(rows)>=target//2,(split,difficulty,len(rows))
            for row,computed,company in rows[:target//2]:
                if split=="dev": dev_companies.add(company)
                selections.append((row,computed,split,difficulty))
    for row,computed,split,difficulty in selections:
        sid="finqa_"+hashlib.sha256(row["id"].encode()).hexdigest()[:16]
        text=row["pre_text"]+row["post_text"]
        ctx={"source_id":sid,"original_report":row.get("filename",row["id"].rsplit("-",1)[0]),"table":[{"id":f"{sid}:table_{i}","cells":cells} for i,cells in enumerate(row["table"])],"text":[{"id":f"{sid}:text_{i}","text":t} for i,t in enumerate(text)]}
        path="finqa/"+sid+".json";dump(INPUT/path,ctx)
        c={"id":sid,"split":split,"track":"finqa_"+difficulty,"language":"en","group_id":row["id"].split("/")[0],"question":row["qa"]["question"],"allowed_assets":[path],"source_ids":[sid],"response_contract":"finqa-numeric-v1","max_citations":8,"answer_convention":"FinQA execution value: percent tokens are fractions; follow arithmetic result, do not multiply a ratio by 100 unless the question requires it. Return unit=finqa_execution."}
        add(c,{"status":"ok","answer":str(row["qa"]["exe_ans"]),"unit":"finqa_execution","citations":[sid+":"+key for key in row["qa"]["gold_inds"]],"abs_tolerance":"0.000006","rel_tolerance":"0","original_id":row["id"],"program":row["qa"]["program"],"recomputed":str(computed)})
    jsonl(INPUT/"cases.jsonl",cases);jsonl(EVAL/"gold.jsonl",gold)
    dump(EVAL/"facts.json",facts)
    con=sqlite3.connect(EVAL/"reference.sqlite")
    con.execute("DROP TABLE IF EXISTS facts")
    columns=list(facts[0]);con.execute("CREATE TABLE facts ("+",".join(k+" TEXT" for k in columns)+", PRIMARY KEY(fact_id))")
    con.executemany("INSERT INTO facts VALUES ("+",".join("?" for _ in columns)+")",[[r[k] for k in columns] for r in facts]);con.commit();con.close()
    summary={"version":"0.1.0","date":"2026-10-03","cases":len(cases),"by_track":dict(Counter(r["track"] for r in cases)),"by_split":dict(Counter(r["split"] for r in cases)),"reference_facts":len(facts),"source_report_pages":708,"finqa_exclusions":dict(excluded),"model_evaluated":False,"selection":"deterministic SHA256 order; balanced single/multi arithmetic; company-disjoint dev/acceptance","limitations":["Small public regression set, not a private unbiased leaderboard test.","FinQA is an arithmetic subset, not the full official benchmark.","Chinese OCR images are clean rasterizations, not noisy physical scans.","Chinese facts visually checked by Codex, not independently double-reviewed.","No actual agent, retrieval, sandbox or chart generation has been evaluated."]}
    dump(ROOT/"summary.json",summary)
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for folder in [INPUT,EVAL] for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix in [".json",".jsonl",".pdf",".png"]}
    dump(ROOT/"dataset_lock.json",files)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__": main()

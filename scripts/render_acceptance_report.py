"""Render existing trusted evidence only. Does not run models or modify benchmark gates."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import html
import json
import math
import os
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
TRACKS = {"cn_extract": "中文财报提取", "cn_calculate": "中文财报计算", "cn_audit": "错误陈述核查",
          "cn_abstain": "缺失期间拒答", "cn_ocr": "扫描图片 OCR", "finqa_single": "FinQA 单步", "finqa_multi": "FinQA 多步"}
STATUS = {"passed": "通过", "pass": "通过", "failed": "未通过", "partial": "部分完成", "not_run": "未验收",
          "running": "进行中", "completed": "已完成", "aborted": "已中止", "pending": "待完成"}


def esc(value):
    return html.escape(str(value), quote=True)


def read(path):
    if not path or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None  # A file being written is pending evidence, never an empty passing result.


def resolve(value):
    path = Path(str(value).replace("\\", "/"))
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Evidence path must stay inside the workspace")
    return path


def link(path, output, label=None):
    path = resolve(path)
    label = label or path.relative_to(ROOT).as_posix()
    if not path.exists():
        return f'<span class="muted">{esc(label)}（文件未生成）</span>'
    href = quote(os.path.relpath(path, output.parent).replace("\\", "/"), safe="/")
    return f'<a href="{href}">{esc(label)}</a>'


def evidence(items, output):
    return '<br>'.join(link(item["path"], output) for item in items if item.get("path")) or '<span class="muted">尚无证据文件</span>'


def badge(status):
    return f'<span class="badge {esc(status)}">{esc(STATUS.get(status, status))}</span>'


def number(value, digits=0):
    return f'{value:,.{digits}f}' if isinstance(value, (int, float)) and math.isfinite(value) else "—"


def percent(value):
    return number(value * 100, 1) + "%" if isinstance(value, (int, float)) else "—"


def metric(value, threshold=None):
    bad = isinstance(value, (int, float)) and threshold is not None and value < threshold
    return f'<span class="{"bad" if bad else "value"}">{percent(value)}</span>'


def select_run(acceptance, run_arg):
    pointer = ((acceptance.get("dataset") or {}).get("acceptance") or {}).get("report")
    summary_path = resolve(pointer) if pointer else None
    summary = read(summary_path)
    if run_arg:
        directory = resolve(run_arg)
    elif summary:
        directory = ROOT / "benchmark/runs" / summary["name"]
    else:
        candidates = []
        for path in (ROOT / "benchmark/runs").glob("*/manifest.json"):
            item = read(path)
            if item and item.get("split") == "acceptance" and not item.get("subset") and item.get("repeat") == 3 and item.get("benchmarkVersion") == acceptance.get("benchmarkVersion") and item.get("status") != "aborted":
                candidates.append((str(item.get("createdAt", "")), path.parent))
        directory = max(candidates, default=("", None))[1]
    manifest = read(directory / "manifest.json") if directory else None
    if manifest and (manifest.get("split") != "acceptance" or manifest.get("subset") or manifest.get("repeat") != 3):
        raise ValueError("Selected run is not a complete three-round acceptance run")
    if directory:
        selected_summary = ROOT / "benchmark/results" / (directory.name + "-summary.json")
        summary = read(selected_summary)
        summary_path = selected_summary
    return directory, manifest or {}, summary_path, summary


def collect(acceptance, directory, manifest, summary):
    rounds = []
    for index in range(1, 4):
        path = ROOT / "benchmark/results" / f'{manifest.get("name", "pending")}-round-{index}.json'
        report = read(path)
        if report and (report.get("split") != "acceptance" or report.get("subset") or report.get("configHash") != manifest.get("configHash")):
            report = None
        # Summary references are authoritative after completion; full reports add audit traces.
        if summary:
            official = next((r for r in summary.get("runs", []) if r.get("round") == index), None)
            if official:
                report = {**(report or {}), **official}
        progress = 0
        if directory:
            progress = sum((directory / f"round-{index}" / case / "result.json").exists() for case in manifest.get("caseIds", []))
        rounds.append({"index": index, "path": path, "report": report, "progress": progress})
    return rounds


def quantile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    location = (len(values) - 1) * fraction
    lower = int(location)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (location - lower)


def render(acceptance, source, output, run_arg=None):
    directory, manifest, summary_path, summary = select_run(acceptance, run_arg)
    rounds = collect(acceptance, directory, manifest, summary)
    reports = [r["report"] for r in rounds if r["report"]]
    complete = bool(summary and summary.get("status") == "completed" and len(reports) == 3)
    repeated_path = directory / "repeatability.json" if directory else None
    repeated = read(repeated_path) if complete else None
    formal_failed = any(r.get("dataset_gate_pass") is False for r in reports)
    cases = [dict(item) for item in acceptance.get("cases", [])]
    # Historical S10 PASS records agent inspection; never imply a human sign-off.
    for item in cases:
        if item.get("id") == "S10" and item.get("status") in {"passed", "partial"} and not (item.get("details") or {}).get("human_review_passed"):
            item["status"] = "partial"
            item["report_note"] = "数值复核和代理视觉核对已完成；尚无人工视觉检查签字，严格规范未全部满足。"
        if item.get("id") == "S12" and not complete:
            item["status"] = "running" if manifest.get("status") == "running" else "not_run"
            item["report_note"] = "等待同一冻结配置完成三轮；进行中轮次不计算最终一致率。"
    strict_runtime = len(cases) == 12 and all(item.get("status") == "passed" for item in cases)
    pointer = ((acceptance.get("dataset") or {}).get("acceptance") or {}).get("report")
    assembly_current = bool(pointer and summary_path and resolve(pointer) == summary_path)
    full_pass = bool(complete and assembly_current and acceptance.get("full_system_acceptance") is True and strict_runtime
                     and summary.get("datasetGateAllRuns") is True and all(r.get("dataset_gate_pass") is True for r in reports))
    if full_pass:
        overall, title = "passed", "整体验收通过"
    elif complete:
        overall, title = "failed" if formal_failed else "partial", "整体尚未通过验收"
    else:
        overall, title = "running", "正式验收进行中"
    count = len(manifest.get("caseIds", []))
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    fragments = [f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>金融研究系统 · 验收报告</title><style>
:root{{color-scheme:light;--ink:#222;--muted:#707070;--line:#e3e3e3;--paper:#fff;--back:#f6f6f6;--bad:#a53535}}*{{box-sizing:border-box}}body{{margin:0;background:var(--back);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}}main{{max-width:1240px;margin:40px auto 72px;padding:0 30px}}header{{margin-bottom:28px}}.eyebrow{{font-size:12px;letter-spacing:.14em;color:var(--muted)}}h1{{font-size:31px;line-height:1.25;margin:10px 0 12px;font-weight:650}}h2{{font-size:20px;margin:0 0 15px}}h3{{font-size:15px;margin:0 0 8px}}p{{margin:8px 0}}a{{color:#444;text-underline-offset:3px;overflow-wrap:anywhere}}a:hover{{color:#000}}.muted,.caption{{color:var(--muted)}}.caption{{font-size:12px}}.panel{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:25px;margin:20px 0}}.hero{{border-left:4px solid #777}}.hero.failed{{border-left-color:var(--bad)}}.hero h2{{font-size:25px;margin:10px 0}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-top:22px}}.card{{padding:15px 18px;background:#f7f7f7;border-radius:9px}}.card b{{display:block;font-size:24px;font-weight:600}}.badge{{display:inline-block;padding:3px 9px;border-radius:6px;background:#efefef;font-size:12px;white-space:nowrap;font-weight:600}}.badge.failed{{background:#f8eaea;color:var(--bad)}}.badge.partial{{background:#f1ede6;color:#6b5840}}.badge.running,.badge.pending,.badge.not_run{{color:#646464;background:#efefef}}.bad{{color:var(--bad);font-weight:650}}.value{{font-variant-numeric:tabular-nums}}.notice{{padding:12px 16px;border-left:3px solid #bdbdbd;background:#f7f7f7;margin:16px 0;font-size:14px}}.notice.failure{{border-left-color:#b75b5b;background:#fcf5f5}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;font-weight:600;color:#666;background:#f8f8f8}}th,td{{padding:12px 13px;border-bottom:1px solid var(--line);vertical-align:top}}td.num,th.num{{text-align:right;white-space:nowrap}}tbody tr:last-child td{{border-bottom:0}}.score small{{display:block;color:var(--muted);font-size:11px}}.id{{font-family:ui-monospace,Consolas,monospace;color:#777;font-size:12px}}.checks td:first-child{{width:60px}}.checks td:nth-child(2){{width:178px}}.checks td:nth-child(3){{width:90px}}details{{margin-top:8px}}summary{{cursor:pointer;color:#666;font-size:12px}}pre{{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:#f7f7f7;border-radius:6px}}.scope{{max-width:580px}}ul{{padding-left:21px}}li{{margin:7px 0}}nav{{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;margin-top:21px}}.audit{{display:grid;grid-template-columns:130px 1fr;gap:8px;font-size:12px}}.audit code{{overflow-wrap:anywhere}}footer{{color:var(--muted);font-size:12px}}@media(max-width:700px){{main{{margin:22px auto;padding:0 15px}}.panel{{padding:17px}}h1{{font-size:25px}}.cards{{grid-template-columns:repeat(2,1fr)}}th,td{{padding:10px 8px}}.audit{{grid-template-columns:1fr}}}}@media print{{body{{background:#fff}}main{{max-width:none;margin:0;padding:0}}.panel{{break-inside:avoid}}nav{{display:none}}a{{color:inherit}}}}
</style></head><body><main><header><div class="eyebrow">FINANCIAL RESEARCH SYSTEM / ACCEPTANCE</div><h1>金融研究系统 · 验收报告</h1><p class="muted">真实执行证据、模型能力门槛与工程验证范围</p><nav><a href="#model">正式模型成绩</a><a href="#runtime">12 项安全与功能</a><a href="#cost">调用与延迟</a><a href="#scope">组件与局限</a></nav></header>
<section class="panel hero {overall}">{badge(overall)}<h2>{title}</h2><p>{esc(acceptance.get("model", manifest.get("model", "模型未记录")))} · Benchmark v{esc(acceptance.get("benchmarkVersion", "—"))} · 正式集 {count or '待记录'} 题 × 3 轮 · 并发 {esc(manifest.get("concurrency", "—"))}</p>''']
    if formal_failed:
        message = "三轮正式运行均已结束，存在未达标项；完整结果已保留，整体未通过。" if complete else "已完成的正式轮次存在未达标项。继续完成三轮会补全统计，不会抹去已记录的失败。"
        fragments.append('<div class="notice failure">' + message + '</div>')
    if complete and not assembly_current:
        fragments.append('<div class="notice">正式运行已结束，但 acceptance.json 尚未关联本次汇总；请先重新生成验收汇总，再更新本报告。</div>')
    passed_count = sum(c.get("status") == "passed" for c in cases)
    numeric = repeated.get("numericConclusionConsistency") if repeated else None
    fragments.append(f'<div class="cards"><div class="card"><span class="caption">正式轮次已评分</span><b>{len(reports)} / 3</b></div><div class="card"><span class="caption">安全功能严格通过</span><b>{passed_count} / 12</b></div><div class="card"><span class="caption">三轮数值一致率</span><b>{percent(numeric)}</b></div><div class="card"><span class="caption">整体门槛</span><b>{"已通过" if full_pass else "尚未通过"}</b></div></div><p class="caption">页面快照：{esc(timestamp)} · 验收汇总时间：{esc(acceptance.get("updatedAt", "未记录"))}。本页不自动刷新；重新执行生成脚本可更新。</p></section>')
    fragments.append('<section class="panel" id="model"><h2>正式模型三轮成绩</h2><p class="muted">每格第一行是答案准确率，第二行是答案与证据同时正确的比例。开发集分数不参与本表，也不代替正式验收。</p><div class="table-wrap"><table><thead><tr><th>任务类型</th><th class="num">每轮题数</th><th class="num">答案门槛</th><th class="num">第 1 轮</th><th class="num">第 2 轮</th><th class="num">第 3 轮</th></tr></thead><tbody>')
    for track, label in TRACKS.items():
        examples = [r.get("metrics", {}).get(track) for r in reports if r.get("metrics", {}).get(track)]
        first = examples[0] if examples else {}
        row = f'<tr><td>{label}</td><td class="num">{number(first.get("n"))}</td><td class="num">≥ {percent(first.get("target_answer_accuracy"))}</td>'
        for round_item in rounds:
            score = (round_item["report"] or {}).get("metrics", {}).get(track)
            row += f'<td class="num score">{metric(score.get("answer_accuracy"), score.get("target_answer_accuracy"))}<small>有据正确 {percent(score.get("grounded_accuracy"))}</small></td>' if score else '<td class="num muted">待评分</td>'
        fragments.append(row + '</tr>')
    fragments.append('</tbody></table></div><div class="table-wrap"><table><thead><tr><th>全局指标</th><th class="num">门槛</th><th class="num">第 1 轮</th><th class="num">第 2 轮</th><th class="num">第 3 轮</th></tr></thead><tbody>')
    for key, label, threshold in [("citation_recall", "引用召回率", .95), ("citation_precision", "引用精确率", .95), ("grounded_accuracy", "整体有据正确率", .85)]:
        fragments.append(f'<tr><td>{label}</td><td class="num">≥ {percent(threshold)}</td>' + ''.join(f'<td class="num">{metric((r["report"] or {}).get(key), threshold)}</td>' for r in rounds) + '</tr>')
    fragments.append('<tr><td>该轮数据集门槛</td><td></td>' + ''.join('<td class="num">' + (badge("passed" if r["report"].get("dataset_gate_pass") else "failed") if r["report"] else f'<span class="muted">已完成 {r["progress"]}/{count} 题 · 待评分</span>') + '</td>' for r in rounds) + '</tr></tbody></table></div>')
    worst = min((r["grounded_accuracy"] for r in reports if isinstance(r.get("grounded_accuracy"), (int, float))), default=None)
    fragments.append(f'<p>已评分轮次最差有据正确率：<strong>{percent(worst)}</strong>。正式通过要求每轮各类答案准确率及全局三个指标同时达标。</p><p class="caption">原始报告：' + ' · '.join(link(r["path"], output, f'第 {r["index"]} 轮') for r in rounds) + '</p></section>')
    fragments.append('<section class="panel"><h2>重复一致性与冻结审计</h2><p>一致性逐轮两两比较有效状态，以及适用的期间、口径等必要字段；数值经显式单位换算后按冻结容差比较。拒答标签没有数值容差时，对有效数值回答采用 Decimal 严格相等比较。该指标不等于答案准确率：相同且格式有效的错误答案也可能一致，正确性由上一节单独衡量。失败或格式无效输出不计为一致。</p><div class="cards">')
    for label, value, threshold in [("数值结论一致 · 门槛 ≥95%", numeric, .95), ("引用集合完全一致 · 描述指标", repeated.get("citationSetConsistency") if repeated else None, None), ("完整输出完全一致 · 描述指标", summary.get("exactPredictionConsistency") if summary else None, None)]:
        fragments.append(f'<div class="card"><span class="caption">{label}</span><b>{metric(value, threshold)}</b></div>')
    fragments.append('</div><div class="audit" style="margin-top:20px">')
    for label, value in [("运行名称", manifest.get("name")), ("配置 SHA256", manifest.get("configHash")), ("提示 SHA256", manifest.get("promptHash")), ("代码 SHA256", (manifest.get("code") or {}).get("hash")), ("数据 SHA256", (manifest.get("dataset") or {}).get("hash"))]:
        fragments.append(f'<span class="muted">{label}</span><code>{esc(value or "待记录")}</code>')
    fragments.append('</div><p>运行前后代码一致：' + ("是" if summary and summary.get("codeUnchangedDuringRun") is True else "否" if summary and summary.get("codeUnchangedDuringRun") is False else "待运行结束核验") + '；数据一致：' + ("是" if summary and summary.get("datasetUnchangedDuringRun") is True else "否" if summary and summary.get("datasetUnchangedDuringRun") is False else "待运行结束核验") + '。</p>')
    if directory:
        fragments.append('<p class="caption">' + ' · '.join([link(directory / "manifest.json", output, "冻结清单"), link(summary_path, output, "正式汇总"), link(repeated_path, output, "逐题一致性与预测文件哈希")]) + '</p>')
    fragments.append('</section><section class="panel" id="runtime"><h2>12 项安全与功能验收</h2><p class="muted">按原规范逐项展示。部分完成、未验收和进行中均不等于严格通过。</p><div class="table-wrap"><table class="checks"><thead><tr><th>编号</th><th>检查项</th><th>结论</th><th>门槛与证据</th></tr></thead><tbody>')
    for item in cases:
        detail = item.get("details") or {}
        fragments.append(f'<tr><td class="id">{esc(item.get("id", ""))}</td><td>{esc(item.get("name", ""))}</td><td>{badge(item.get("status", "not_run"))}</td><td>{esc(item.get("criterion", ""))}' + (f'<p class="muted">{esc(item["report_note"])}</p>' if item.get("report_note") else '') + f'<details><summary>证据与执行详情</summary><p>{evidence(item.get("evidence", []), output)}</p><pre>{esc(json.dumps(detail, ensure_ascii=False, indent=2))}</pre></details></td></tr>')
    fragments.append('</tbody></table></div></section><section class="panel" id="cost"><h2>调用、Token 与延迟</h2><p class="muted">只汇总已完成评分的正式轮次；进行中轮次尚未计入。延迟包含附件解析、工具与模型等待，并非纯模型推理时延。</p><div class="table-wrap"><table><thead><tr><th>轮次</th><th class="num">模型调用</th><th class="num">输入 Token</th><th class="num">输出 Token</th><th class="num">轮次墙钟</th><th class="num">单题 P50 / P95</th></tr></thead><tbody>')
    for item in rounds:
        report = item["report"]
        if not report:
            fragments.append(f'<tr><td>第 {item["index"]} 轮</td><td colspan="5" class="muted">待完整轮次结束</td></tr>')
            continue
        traces = report.get("traces", [])
        durations = [t["elapsedMs"] / 1000 for t in traces if isinstance(t.get("elapsedMs"), (int, float))]
        fragments.append(f'<tr><td>第 {item["index"]} 轮</td><td class="num">{number(report.get("modelCalls"))}</td><td class="num">{number(report.get("inputTokens"))}</td><td class="num">{number(report.get("outputTokens"))}</td><td class="num">{number(report.get("wallTimeMs", 0) / 60000, 1)} 分钟</td><td class="num">{number(quantile(durations, .5), 1)} / {number(quantile(durations, .95), 1)} 秒</td></tr>')
    fragments.append('</tbody></table></div><p>已评分轮次累计：' + number(sum(r.get("modelCalls", 0) for r in reports)) + ' 次模型调用；输入 ' + number(sum(r.get("inputTokens", 0) for r in reports)) + ' Token；输出 ' + number(sum(r.get("outputTokens", 0) for r in reports)) + ' Token。</p><p class="caption">Token 取自运行日志，不把未知费用填成 0，也不按未核实的模型价格推算账单。</p></section>')
    scopes = {"deterministic_pipeline": "三份完整年报的确定性解析与数值对照，不代表模型推理准确率。",
              "Frontend browser tests with API fixtures. NOT backend integration, parser, model, or benchmark accuracy evidence.": "固定 API 响应下的浏览器交互契约；未覆盖真实后端、模型或基准准确率。",
              "Real frontend + local Node API + Python parser. Four synthetic fixtures. Does not prove real LLM success or benchmark accuracy.": "真实前端、Node API 与 Python 解析器，四组合成材料；不证明模型或正式基准准确率。",
              "Real browser + Node Pi harness + configured official DeepSeek + Python service. Synthetic developer fixture, NOT benchmark gold or accuracy dataset.": "真实浏览器、Pi、DeepSeek 与 Python 服务联调；使用开发用合成材料，不是正式基准成绩。",
              "Real three-full-report DeepSeek/Pi/Docker chart, downloaded over application API; independently compared after generation, not used as a benchmark answer": "三份完整财报经 DeepSeek、Pi、Docker 生成图表，并从应用 API 下载后独立核对；未作基准答案输入。"}
    fragments.append('<section class="panel" id="scope"><h2>工程组件验证范围</h2><div class="table-wrap"><table><thead><tr><th>组件</th><th>结果</th><th>覆盖范围 / 证据</th></tr></thead><tbody>')
    for item in acceptance.get("components", []):
        scope = scopes.get(item.get("scope"), item.get("scope") or "实际模型调用分析容器并取回图表产物；具体输入、运行 ID 与检查范围见证据。")
        count_text = f' · {item["passed"]}/{item["total"]}' if "passed" in item and "total" in item else ""
        fragments.append(f'<tr><td>{esc(item.get("name", ""))}</td><td>{badge(item.get("status", "not_run"))}{count_text}</td><td class="scope">{esc(scope)}<details><summary>查看证据</summary>{evidence(item.get("evidence", []), output)}</details></td></tr>')
    fragments.append('<tr><td>真实 Embedding 模型与向量检索</td><td>' + badge("not_run") + '</td><td class="scope">尚未提供独立 Embedding 供应商凭据。关键词检索与远程 API 协议、降级测试已覆盖；没有真实向量模型效果验收，不能据此宣称混合检索已达标。</td></tr></tbody></table></div><h3 style="margin-top:25px">已知局限</h3><ul>')
    for limitation in acceptance.get("limitations", []):
        fragments.append('<li>' + esc(limitation) + '</li>')
    fragments.append('<li>容器输出大小通过轮询与导出检查限制，并非文件系统硬配额。</li><li>旧运行发生过间歇性 OCR ResizeImgError，原始底层原因未完全复现；线程限制后完成两轮四路完整 PDF 回归，旧失败证据保留。</li></ul><p class="caption">' + link(ROOT / "service/runs/parser-concurrency-content.json", output, "解析修复前后全文内容对照") + '</p></section>')
    if directory:
        fragments.append('<section class="panel"><h2>逐题追溯</h2><p>每轮报告含题目 ID、答案与引用判定；执行轨迹含 run ID、工具调用量及延迟。原始运行目录保留输入副本、文件哈希和计算产物。</p><p>' + link(directory, output, "打开本次正式运行目录") + '</p><p class="caption">' + ' · '.join(link(directory / f'round-{i}' / 'traces.json', output, f'第 {i} 轮执行轨迹') for i in range(1, 4)) + '</p></section>')
    error_review = ROOT / "benchmark/results/acceptance-round1-error-analysis.json"
    if error_review.exists():
        fragments.append('<section class="panel"><h2>失败分类复核</h2><p>首轮事后错误分析，用于定位歧义与拒答代码、引用定位映射和标注证据集合的限制。该分析不修改评分、不回填答案，也不计作新的模型运行。</p><p>' + link(error_review, output, "查看首轮失败分类复核") + '</p></section>')
    fragments.append(f'<footer><p>数据来源：{link(source, output, "acceptance.json")}。本报告只读取既有证据，不运行模型、不重算标签、不调整验收门槛。旧中止运行与开发集未混入正式成绩。</p><p>独立 HTML，无外部字体、脚本或网络依赖。生成命令：<code>python scripts/render_acceptance_report.py</code></p></footer></main></body></html>')
    return '\n'.join(fragments), {"status": overall, "scored_rounds": len(reports), "strict_runtime_passed": passed_count, "full_system_acceptance": full_pass}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="benchmark/results/acceptance.json")
    parser.add_argument("--output", default="benchmark/results/acceptance-report.html")
    parser.add_argument("--run", help="Optional explicit benchmark/runs/<formal-run> directory")
    args = parser.parse_args()
    source, output = resolve(args.source), resolve(args.output)
    acceptance = read(source)
    if not acceptance:
        parser.error("acceptance.json is missing or not valid JSON")
    document, status = render(acceptance, source, output, args.run)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"output": str(output), **status}, ensure_ascii=True))


if __name__ == "__main__":
    main()

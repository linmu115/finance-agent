"""Offline aggregate export. No source text, financial values, identifiers or payload hashes exported."""
import collections
import functools
import hashlib
import json
from pathlib import Path
import tiktoken

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'data/evaluation/blind-eval-F12-heldout-20261008'
OUT = ROOT / 'data/evaluation/blind-eval-heldout-diagnostics-redacted-20261008'
OUT.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text('utf-8-sig'))
requests = read(PRIVATE / 'private-reconstructed-contexts.json')
enc = tiktoken.get_encoding('o200k_base')


@functools.lru_cache(None)
def tokens(text):
    return len(enc.encode(text, disallowed_special=()))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')


groups = {}
request_counts = []
for profile in ['prepared', 'financial']:
    categories = collections.defaultdict(collections.Counter)
    tool_results = collections.defaultdict(collections.Counter)
    schemas = collections.defaultdict(collections.Counter)
    seen = set()
    seen_calls = set()
    payloads = set()
    usage = collections.Counter()
    tool_inventory = collections.defaultdict(collections.Counter)
    seen_arg = set()
    within_chain_arg = set()
    workpaper_failures = collections.Counter()
    for f in sorted(PRIVATE.glob(('P' if profile == 'prepared' else 'F') + '*-audit.jsonl')):
        for row in map(json.loads, f.read_text('utf-8-sig').splitlines()):
            if row['type'] != 'tool_request':
                continue
            d = row['data']; name = d['name']; kind = d['args'].get('kind') if name == 'financial_workpaper' else None
            key = (name, kind)
            tool_inventory[key]['calls'] += 1
            arg = json.dumps(d['args'], sort_keys=True, ensure_ascii=False)
            # Exact request argument equality only; does not imply a call was unnecessary.
            identity = (name, arg)
            if identity in seen_arg:
                tool_inventory[key]['identical_argument_recalls'] += 1
            seen_arg.add(identity)
            within = (f.name.split('_H')[0], *identity)
            if within in within_chain_arg:
                tool_inventory[key]['same_chain_identical_argument_recalls'] += 1
            within_chain_arg.add(within)
    seq = 0
    for request in requests:
        if request['profile'] != profile:
            continue
        seq += 1
        usage['requests'] += 1
        known = request['usageKnown']
        actual = None
        if known:
            u = request['usage']; actual = sum(u.get(k, 0) for k in ['input', 'cacheRead', 'cacheWrite'])
            usage['known_requests'] += 1
            usage['known_input_tokens'] += actual
            usage['known_cached_input_tokens'] += u.get('cacheRead', 0) + u.get('cacheWrite', 0)
        else:
            usage['unknown_usage_requests'] += 1
        rowcat = collections.Counter(); rowtools = collections.Counter(); repeated = 0; opaque = 0
        for b in request['blocks']:
            cat = b['category']; n = tokens(b['text'])
            identity = (request['chain'], b['key'], b['text'])
            repeat = identity in seen
            seen.add(identity)
            rowcat[cat] += n
            if repeat:
                repeated += n
            opaque += b.get('opaqueCharacters', 0)
            if known:
                categories[cat]['estimated_text_tokens'] += n
                categories[cat]['repeated_carry_tokens' if repeat else 'first_exposure_tokens'] += n
                categories[cat]['block_exposures'] += 1
            if cat == 'tool_schema' and known:
                schemas[b['tool']]['estimated_text_tokens'] += n
            if cat == 'tool_result':
                k = (b['tool'], b.get('kind'))
                rowtools[k] += n
                call = (request['chain'], b['callKey'], b['key'])
                if call not in seen_calls:
                    seen_calls.add(call)
                    tool_results[k]['distinct_return_blocks'] += 1
                    tool_results[k]['one_time_return_tokens'] += n
                    tool_results[k]['max_return_tokens'] = max(tool_results[k]['max_return_tokens'], n)
                    envelope = json.loads(b['text'])
                    status = envelope.get('status', 'unknown')
                    tool_results[k]['error_status_return_blocks'] += int(status=='error')
                    tool_results[k]['return_status_' + status] += 1
                    if b['tool'] == 'financial_workpaper' and status == 'insufficient_evidence':
                        error = envelope.get('data', {}).get('error', '')
                        if '请指定 company 或 document_id' in error:
                            workpaper_failures['ambiguous_entity_selection'] += 1
                        elif '没有可定位到利润表的收入期间' in error:
                            workpaper_failures['income_statement_revenue_period_not_locatable'] += 1
                        else:
                            raise ValueError('Unclassified workpaper failure; do not export raw text')
                    content = (request['chain'], b['tool'], b['text'])
                    if content in payloads:
                        tool_results[k]['identical_payload_new_return_blocks'] += 1
                        tool_results[k]['identical_payload_new_return_tokens'] += n
                    payloads.add(content)
                if known:
                    tool_results[k]['known_request_exposures'] += 1
                    tool_results[k]['known_request_estimated_tokens'] += n
                    tool_results[k]['known_request_repeated_carry_tokens'] += n if repeat else 0
                else:
                    tool_results[k]['unknown_request_exposures'] += 1
                    tool_results[k]['unknown_request_estimated_tokens'] += n
        estimated = sum(rowcat.values())
        request_counts.append({'group': profile, 'request_ordinal': seq, 'phase': request['phase'],
            'usage_known': known, 'known_input_tokens': actual,
            'audit_context_characters': request['contextCharacters'], 'context_character_match': True,
            'estimated_text_tokens': estimated,
            'actual_minus_text_estimate': actual-estimated if known else None,
            'estimated_by_category': dict(rowcat),
            'estimated_tool_results': [{'tool': k[0], 'kind': k[1], 'tokens': v} for k, v in sorted(rowtools.items())],
            'repeated_carry_estimated_tokens': repeated,
            'opaque_reasoning_characters_not_tokenized': opaque})
    # Report zeros for counts, but never replace unknown token usage with zero.
    usage.setdefault('unknown_usage_requests', 0)
    rows = []
    for k in sorted(tool_inventory):
        rows.append({'tool': k[0], 'kind': k[1], **dict(tool_inventory[k]), **dict(tool_results[k])})
    proxy = sum(v['estimated_text_tokens'] for v in categories.values())
    groups[profile] = {'usage': dict(usage), 'known_request_category_estimates': dict(categories),
        'known_request_total_text_estimate': proxy,
        'known_actual_minus_text_estimate': usage['known_input_tokens']-proxy,
        'tool_results': rows, 'workpaper_failure_categories': dict(workpaper_failures),
        'tool_schema_estimates': [{'tool': k, **dict(v)} for k, v in sorted(schemas.items())]}

p, f = [groups[k] for k in ['prepared', 'financial']]
delta = f['usage']['known_input_tokens'] - p['usage']['known_input_tokens']
delta_cat = {k: f['known_request_category_estimates'].get(k, {}).get('estimated_text_tokens', 0)-p['known_request_category_estimates'].get(k, {}).get('estimated_text_tokens', 0) for k in set(p['known_request_category_estimates'])|set(f['known_request_category_estimates'])}
assert p['usage']['known_input_tokens'] == 746546
assert f['usage']['known_input_tokens'] == 1390944
assert len(request_counts) == 69
assert sum(delta_cat.values()) + f['known_actual_minus_text_estimate'] - p['known_actual_minus_text_estimate'] == delta
result = {'scope': 'F1.2 completed held-out batch only; preparation, reviews and F1.1 aborted batch excluded',
    'disclosure': 'Only category names and counts. No question, answer, source, financial value, document/run/session identifier, payload/hash, or source-page selector.',
    'method': {'exact': 'Provider usage totals and request/call counts; reconstructed pre-provider context characters match all audit requests.',
        'estimate': 'o200k_base applied to readable message text, compact JSON tool schemas/arguments and tool result text. This tokenizer is a proxy, not a verified tokenizer for the CPA model alias.',
        'no_proration': 'Estimates are not scaled to the billed input. Signed actual-minus-estimate is retained and is not a negative cost.',
        'omissions': 'Opaque encrypted reasoning is counted as characters only. Transport framing, tokenizer differences and possible provider transforms are not source-attributable.',
        'history': 'Prior assistant text/arguments/reasoning summaries and older user messages. Historical tool results stay in the tool-result category to avoid double counting.',
        'repeated': 'Same exact block carried in a later submitted request of the same chain; overlaps categories and is NOT additive or proof of avoidable waste. Separate identical new returns count only exact text matches.',
        'unknown': 'Two unknown financial requests remain unknown. Their visible text estimates are available per request, excluded from known-input category comparison.',
        'schema': 'System prompt includes project guidance and working-directory context; tool schema includes full descriptions and parameter schemas.'},
    'groups': groups, 'known_input_difference': delta, 'known_input_increase_percent': round(delta/p['usage']['known_input_tokens']*100, 2),
    'estimated_difference_by_category': delta_cat, 'requests': request_counts}
dump(OUT/'cost-counts.json', result)

labels = {'system_prompt':'系统提示与项目指导','tool_schema':'工具说明与参数 schema','tool_result':'工具结果（含历史结果）',
    'current_user_message':'当前用户消息及宿主任务说明','prior_user_history':'此前用户消息','assistant_history_text':'历史助手正文',
    'assistant_history_tool_arguments':'历史助手工具参数／代码','assistant_history_reasoning_summary':'历史可见推理摘要','opaque_reasoning_envelope':'不透明推理封装（不计文本 token）'}
md = ['# 成本构成脱敏统计诊断', '',
      '仅统计 F1.2 已完成的 held-out 参评分析。下列数字全部是请求、字符、token 或计数，不含财务数值。准备、独立评审与 F1.1 中止批次不并入。', '',
      f"**可精确确认：**两组分别 30、39 次请求；已知输入分别 746,546、1,390,944 token，差额 644,398（{result['known_input_increase_percent']:.2f}%）。金融组另有 2 次请求用量未知，通用组没有未知请求。", '',
      '**来源拆分是文本估算，不是精确账单。**按持久会话及当时冻结的工具声明重建，69/69 次请求的序列化上下文字符数与审计完全相等。对可读内容使用本地 o200k_base 计数；CPA 模型别名的真实 tokenizer 未核实，完整供应商请求体未留档。工具/消息传输封装、不透明加密推理及供应商可能转换没有精确归属；不按比例强行摊平差额。', '',
      '| 来源类别 | 通用组估算 token | 金融组估算 token | 差额 |', '|---|---:|---:|---:|']
for cat in labels:
    a=p['known_request_category_estimates'].get(cat,{}).get('estimated_text_tokens',0);b=f['known_request_category_estimates'].get(cat,{}).get('estimated_text_tokens',0)
    md.append(f'| {labels[cat]} | {a:,} | {b:,} | {b-a:+,} |')
md.extend(['',f"文本估算合计：通用 {p['known_request_total_text_estimate']:,}，金融 {f['known_request_total_text_estimate']:,}。实际已知输入减文本估算分别为 {p['known_actual_minus_text_estimate']:+,}、{f['known_actual_minus_text_estimate']:+,}；负差是估算偏差，不能解释为负费用。", '',
    '历史工具结果归在“工具结果”，不再并入“历史消息”。重复携带是重叠统计，不能作为第五项再加一次。已知缓存输入仍包含在总输入中；重复载荷不等于未缓存计费，也不等于可以安全删除。', ''])
for profile,title in [('prepared','通用组'),('financial','金融组')]:
    g=groups[profile]
    md.extend([f'## {title}工具结果', '', '| 工具 / kind | 调用数 | 一次返回总估算 | 最大单次返回 | 已知请求累计携带估算 | 其中再次携带 |', '|---|---:|---:|---:|---:|---:|'])
    for x in sorted(g['tool_results'],key=lambda x:-x.get('known_request_estimated_tokens',0)):
        name=x['tool']+(('/'+x['kind']) if x['kind'] else '')
        md.append(f"| {name} | {x['calls']} | {x.get('one_time_return_tokens',0):,} | {x.get('max_return_tokens',0):,} | {x.get('known_request_estimated_tokens',0):,} | {x.get('known_request_repeated_carry_tokens',0):,} |")
    repeated=sum(x['repeated_carry_tokens'] for x in g['known_request_category_estimates'].values())
    dup=sum(x.get('identical_payload_new_return_blocks',0) for x in g['tool_results'])
    recalls=sum(x.get('identical_argument_recalls',0) for x in g['tool_results'])
    within=sum(x.get('same_chain_identical_argument_recalls',0) for x in g['tool_results'])
    md.extend(['',f'已知请求中，所有类别再次携带的文本估算共 {repeated:,} token。新返回块中与同链既有返回完全同文的有 {dup} 个（仅完全匹配，不代表语义上没有重复）。同组工具名与全部参数完全相同的再调用有 {recalls} 次，其中同链 {within} 次；独立重复实验之间的相同调用不判为冗余，同链也不自动判为无用。', ''])
md.extend(['## 增量主要在哪里', '',
    '按文本估算，工具结果增加 **418,049 token**，系统提示与工具说明合计增加 **171,600 token**；历史消息（不重复计工具结果）净增 **68,056 token**，当前用户与宿主说明增加 **1,959 token**。其余为实际总输入与文本估算间的差额。', '',
    '| 工具结果类别 | 金融减通用的累计携带估算 token | 通用 / 金融调用数 | 通用 / 金融结果块携带次数（已知请求） |',
    '|---|---:|---:|---:|',
    '| get_document_index | +230,892 | 2 / 7 | 22 / 103 |',
    '| get_source_table | +124,065 | 3 / 12 | 32 / 135 |',
    '| get_analysis_status | +79,796 | 8 / 8 | 34 / 48 |',
    '| search_evidence | +44,182 | 3 / 4 | 31 / 36 |', '',
    '这些正增量还被其他工具的下降部分抵消。目录和原表同时存在读取调用增多、既有结果随更多请求再次携带的现象；分析状态调用数相同，但金融组返回总文本更大、携带次数更多。仅目录结果再次携带估算分别为 51,366 / 269,044 token。', '',
    '**没有“大底稿结果”证据。**金融组 financial_workpaper 共 8 次调用，4 类 kind 已逐项列出，全部返回 insufficient_evidence，没有形成成功底稿。错误机制计数：主体定位歧义 5、收入期间定位失败 3。全部底稿返回一次的文本估算合计 546 token、在已知请求累计携带 7,669 token。不能据此归因于大底稿体积；失败后的读取与自由脚本链条值得在非 held-out 材料上复现，但当前统计不证明其全部成本由失败引起。', '',
    '多轮携带而非完全相同的新工具返回，是本批可直接观察的重复来源。已知请求全部类别再次携带估算，金融比通用多 630,699 token；它与上表各来源重叠，不能另加，也不直接等于可节约 token 或费用。金融组既有静态说明更长，也提交了更多主模型请求，二者共同放大累计输入。主模型请求数通用 26、金融 35，其中金融 2 次用量未知；路由请求两组各 4 次。工具调用数通用 37、金融 59。', ''])
md.extend(['## 逐请求统计', '',
    '详表 `cost-counts.json` 的 requests 数组：69 行，只保留组别、匿名顺序号、阶段、实际已知总输入、各来源估算、按工具/kind的结果估算、重复携带估算及不透明封装字符数。未知总输入为 null。每工具的说明体积汇总也在该文件内。', '',
    '## 判断边界', '',
    '最大差额先按工具结果、静态说明、历史消息分别定位，再比较一次返回体积与多轮携带次数。该分解支持优化方向，不支持直接承诺等量省费；删除上下文是否保持证据与结果质量，需要下一轮用非 held-out 材料验证。'])
(OUT/'cost-composition.md').write_text('\n'.join(md)+'\n','utf8')
print(json.dumps({'groups':{k:{'usage':v['usage'],'top_tools':sorted(v['tool_results'],key=lambda x:-x.get('known_request_estimated_tokens',0))[:5]} for k,v in groups.items()}},ensure_ascii=False))

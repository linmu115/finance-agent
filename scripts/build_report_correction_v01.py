"""Source-authored correction challenge. Never reads predictions or app facts.

Prepared from the original PDF's five visually inspected pages. Refuses to
overwrite frozen task/gold. This builder is private host evaluation material.
"""
from pathlib import Path
from decimal import Decimal
import datetime, hashlib, json, re
import fitz

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'benchmark/versions/v0.1-report-correction'
SOURCE = ROOT / 'samples/native-pdf/贵州茅台2024年年度报告.pdf'
PAGES = [5, 6, 15, 16, 17]
if any((OUT / n).exists() for n in ['gold.json', 'REPORT.txt', 'manifest.json']):
    raise SystemExit('Refusing to replace locked correction material')
(OUT / 'inputs').mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
write = lambda name, x: (OUT / name).write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding='utf-8')
compact = lambda s: re.sub(r'\s+', '', s)
utf16 = lambda s: len(s.encode('utf-16-le')) // 2
source_hash = '5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30'
assert sha(SOURCE) == source_hash
document = fitz.open(SOURCE)
texts = {p: document[p-1].get_text() for p in PAGES}

# Every evidence anchor is checked against original PDF text; original renders
# were inspected first. These literal source values do not come from the app.
claims = []
def evidence(page, *anchors):
    assert all(compact(a) in compact(texts[page]) for a in anchors), (page, anchors)
    return {'original_page': page, 'input_page': PAGES.index(page)+1, 'anchors_all': list(anchors)}

def correct(text, refs, kind='fact'):
    claims.append({'kind': 'protected', 'claim_type': kind, 'text': text, 'evidence': refs})

def error(text, bad, replacements, category, refs, rationale):
    assert text.count(bad) == 1, (text, bad)
    claims.append({'kind': 'error', 'text': text, 'bad': bad, 'accepted_replacements': replacements,
                   'category': category, 'evidence': refs, 'rationale': rationale})

def opinion(text):
    claims.append({'kind': 'protected', 'claim_type': 'inference', 'text': text, 'evidence': []})

correct('2023年营业收入为147,693,604,994.14元。', [evidence(5, '147,693,604,994.14')])
error('2024年营业收入为170,899,152,276.43元。', '170,899,152,276.43', ['170,899,152,276.34'], 'number', [evidence(5, '170,899,152,276.34')], '两位小数次序被调换，按原表精确到分更正。')
correct('年报披露2024年营业收入同比增长15.71%。', [evidence(5, '15.71')])
error('2024年经营活动产生的现金流量净额为92,463,692,168.43万元。', '万元', ['元', '人民币元'], 'unit', [evidence(5, '单位：元', '92,463,692,168.43')], '原表单位为元，误写万元造成一万倍错误。')
correct('2024年归属于上市公司股东的净利润为86,228,146,421.62元。', [evidence(5, '86,228,146,421.62')])
opinion('若终端需求转弱，我倾向于下调未来销量假设；这是情景判断，并非已发生事实。')
error('2024年上半年经营活动产生的现金流量净额为7,799,552,404.82元。', '上半年', ['第三季度', '第三季度（7—9月）', '第三季度（7-9月）', '第三季度（7至9月）'], 'period', [evidence(6, '第三季度', '7,799,552,404.82')], '该数属于第三季度单季，并非上半年累计。')
correct('2024年末归属于上市公司股东的净资产为233,105,984,399.47元。', [evidence(5, '233,105,984,399.47')])
error('2024年全年平均总资产为298,944,579,918.70元。', '2024年全年平均总资产', ['2024年末总资产', '2024年12月31日总资产'], 'period', [evidence(5, '2024年末', '298,944,579,918.70')], '年末时点存量不得解释为全年平均。')
correct('2024年末股本为1,256,197,800.00元。', [evidence(5, '1,256,197,800.00')])
correct('2024年基本每股收益为68.64元/股。', [evidence(5, '基本每股收益', '68.64')])
error('2024年全体股东净利润为86,228,146,421.62元。', '全体股东净利润', ['归属于上市公司股东的净利润', '归母净利润'], 'scope', [evidence(5, '归属于上市公司股东的净利润', '86,228,146,421.62')], '原指标只归属于上市公司股东，不含少数股东归属范围。')
correct('2023年加权平均净资产收益率为34.19%。', [evidence(5, '34.19')])
error('2024年与2023年加权平均净资产收益率的算术差额为1.83%。', '1.83%', ['1.83个百分点', '1.83个百分比点'], 'unit', [evidence(5, '增加1.83个百分点')], '两个百分率之差用百分点，不能写相对增幅百分比。')
correct('2024年第一季度营业收入为45,775,517,043.29元。', [evidence(6, '第一季度', '45,775,517,043.29')])
error('营业收入同比增速的公式为（2024年营业收入－2023年营业收入）÷2024年营业收入×100%。', '（2024年营业收入－2023年营业收入）÷2024年营业收入', ['（2024年营业收入－2023年营业收入）÷2023年营业收入'], 'formula', [evidence(5, '170,899,152,276.34', '147,693,604,994.14')], '同比增长的分母为基期收入；数字表并不把公式定义为本期分母。')
opinion('仅凭现金流与利润的一年比较不足以断言长期盈利质量，我建议继续观察营运资金变化。')
correct('2024年第四季度归属于上市公司股东的净利润为25,400,594,303.11元。', [evidence(6, '第四季度', '25,400,594,303.11')])
error('引用2024年年度报告，可以认定2025年基本每股收益为68.64元/股。', '2025年', ['2024年'], 'citation', [evidence(5, '2024年', '68.64')], '旧报告只支持报告内2024年数据，不能转作2025年事实。')
correct('2024年第二季度经营活动产生的现金流量净额为27,434,411,397.54元。', [evidence(6, '第二季度', '27,434,411,397.54')])
error('2024年全口径营业收入合计170,611,838,052.02元。', '全口径营业收入', ['主营业务收入', '主营业务营业收入'], 'scope', [evidence(16, '公司主营业务构成', '170,611,838,052.02')], '原表明确为主营业务，不得当含其他业务的全口径营业收入。')
correct('2024年茅台酒销量为46,412.95吨。', [evidence(15, '销量', '46,412.95')])
error('2024年第二季度归属于上市公司股东的净利润为17,630,348,609.22元，出处为原始PDF第5页。', '第5页', ['第6页'], 'citation', [evidence(6, '17,630,348,609.22')], '原始物理第6页披露季度明细；第5页只披露年度主要数据。')
correct('2024年其他系列酒产量为48,112.51吨。', [evidence(15, '产量', '48,112.51')])
error('2024年“i茅台”数字营销平台销售收入同比增长10.51%。', '增长10.51%', ['下降10.51%', '减少10.51%', '增长-10.51%'], 'number', [evidence(16, '“i 茅台”数字营销平台', '-10.51')], '原表同比为负值，不是正增长。')
correct('公司把自营和“i茅台”等数字营销平台渠道归入直销。', [evidence(15, '直销渠道指自营和“i 茅台”等数字营销平台渠道')])
error('年报说明，茅台酒从生产到出厂至少需要一年。', '一年', ['五年', '5年'], 'period', [evidence(15, '茅台酒从生产到出厂至少需要五年')], '原文最低周期为五年，一年与原披露矛盾。')
quarter_total = sum(map(Decimal, ['45775517043.29', '36155460624.46', '38845154206.94', '50123020401.65']))
assert quarter_total == Decimal('170899152276.34')
correct('把2024年四个季度营业收入相加，得到170,899,152,276.34元，与年报全年营业收入一致。', [evidence(6, '45,775,517,043.29', '36,155,460,624.46', '38,845,154,206.94', '50,123,020,401.65'), evidence(5, '170,899,152,276.34')], 'calculation')
opinion('直营占比变化可能影响盈利表现，但具体因果贡献仍需其他证据，暂不量化。')
difference = Decimal('92463692168.43') - Decimal('86228146421.62')
assert difference == Decimal('6235545746.81')
correct('2024年经营现金流量净额比归母净利润高6,235,545,746.81元；这只是两项已披露数值的差额。', [evidence(5, '92,463,692,168.43', '86,228,146,421.62')], 'calculation')
correct('2024年批发代理渠道的主营业务营业收入为95,768,511,021.23元。', [evidence(16, '公司主营业务构成'), evidence(17, '批发代理', '95,768,511,021.23')])

text = '贵州茅台2024年经营研究草稿\n以下编号仅用于定位陈述；金额按原披露精度列示。\n\n'
for i, c in enumerate(claims, 1):
    c['id'] = f'A{i:02}'
    text += '[' + c['id'] + '] '
    c['start'] = utf16(text)
    text += c['text']
    c['end'] = utf16(text)
    if c['kind'] == 'error':
        offset = c['text'].index(c['bad'])
        c['target'] = {'start': c['start'] + utf16(c['text'][:offset]), 'end': c['start'] + utf16(c['text'][:offset]+c['bad']), 'original': c['bad']}
    text += '\n\n'
assert sum(c['kind']=='error' for c in claims) == 12
assert sum(c['kind']=='protected' and c['claim_type']!='inference' for c in claims) == 16
assert sum(c.get('claim_type')=='inference' for c in claims) == 3
(OUT / 'REPORT.txt').write_text(text, encoding='utf-8', newline='')
write('gold.json', {'version':'report-correction-0.1', 'offset_contract':'JavaScript UTF-16, start inclusive, end exclusive', 'original_text_sha256':sha(OUT/'REPORT.txt'), 'claims':claims,
                   'thresholds':{'correction_precision':0.95,'correction_recall':0.90,'protected_claims_changed':0,'opinions_changed':0},
                   'independent_calculations':{'quarter_revenue_sum':str(quarter_total),'operating_cash_minus_parent_profit':str(difference)}})
outpdf = fitz.open()
for p in PAGES:
    outpdf.insert_pdf(document, from_page=p-1, to_page=p-1)
outpdf.save(OUT/'inputs/moutai_2024_correction_sources.pdf', garbage=4, deflate=True)

protocol = '''研报纠错独立任务 v0.1：冻结评分协议
这是任务级新挑战，不是公司留出：贵州茅台2024年报已经用于本项目抽取开发。12个人工植入错误、16条正确事实/计算、3条合理观点，均先于模型输出锁定。不是随机总体样本，也不是官方比赛指标。不得将它等同于新公司整表抽取留出集。
来源是原始官方披露PDF的物理页5、6、15、16、17。页片顺序对应输入物理页1—5；原页编号保留在页面底部。5页均逐页图像核验，未使用应用解析或模型抽取来编答案。答案金额精确到原表精度。
提交通过Pi读取同一附件，并调用save_research_report(kind=report_correction)。原文完整不变；每项问题用UTF-16位置与原文substring定位。最小编辑，保留非错误句式/编号/精度。允许扩大到同一陈述的范围，只要复原后的句子等于预冻结的正确句子（归一空白、千位逗号、全角标点及算式同义符号）。不得删掉错误整句来获得通过；不得用模糊措辞回避可核对数字。
主指标：有效修正数/全部提交issue数为correction precision；有效修正的唯一错误数/12为correction recall。分别>=95%和>=90%。每个有效修正须同时满足：位置、确有该错误、完整正确replacement、原始页证据、无同项重复/重叠。错误数字只检测未改正不算修正TP；另列detection precision/recall，不混为主分数。至少需修对11/12且不能附加一条误报才可能过此小样本门槛。
重复/范围跨两个陈述/无效位置/空替换/照抄原文/正确内容被判错均计precision分母，不计TP。一个提交issue不能获多个错误信用。相邻正确陈述不能因整段替换而绕过保护。三条合理观点不因缺乏唯一客观答案被判错。正确事实和意见的保护为独立零变更门槛。
允许少量预先列出的等价替换；执行后遇到未列等价措辞，保留正式分数并单列独立诊断，不按预测修改本轮gold。数字单位的替换不允许改变概念、期间或口径；%不能当百分点。公式采用同一个同比定义，不能换分母后保留原答案。
证据要求actual document ID+input物理page:N；引用文字必须原文可核对，且合并后覆盖本题预冻结的最小来源锚点。跨页主营表需要包含表头与续表数值两页。只写“年报”不算定位证据。来源URL/SHA和页映射保留宿主侧，gold不传模型。
报告original_text必须逐字相同。宿主独立应用patch并核对revised_text，不接受模型自称成功。保留所有issue、逐项失败原因、未改正确陈述/意见、未发现错误和实际API用量。固定实现、输入、gold、评分器的运行前后SHA；首次锁禁止重复跑挑选最好结果。没有真实模型结果前状态只为prepared。
'''
(OUT/'PROTOCOL.txt').write_text(protocol,encoding='utf-8')
(OUT/'TASK.txt').write_text('''请审核下列研究草稿，逐项核对随附原始年报页。原始PDF页5、6、15、16、17依次对应附件物理页1、2、3、4、5。只纠正可核实的事实、单位、期间、范围、公式或来源错误；明确的情景判断或合理观点不是事实错误。保留正确陈述，不为润色改写。\n先读取get_research_report_schema(kind=report_correction)，最终必须用save_research_report(kind=report_correction)保存成果。original_text必须逐字使用提供的草稿；issues按JavaScript UTF-16索引定位最小错误片段，start包含/end不含，保留非错误原句与数字精度；每个独立错误一个issue，给出正确replacement及真实文档page:N引用和原文quote。verified_claims用草稿Axx编号保留已核实正确陈述，并区分fact/calculation/inference；不要只在对话里口头报告。必要计算可用独立分析容器。\n本任务无需查询当前市价或联网，不补写材料之外的新事实。\n\n待审原文：\n''',encoding='utf-8')
write('source-map.json', {'source_url':'https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF','original_sha256':source_hash,'original_pages':143,
 'input_file':'moutai_2024_correction_sources.pdf','page_mapping':[{'input_page':i+1,'original_page':p} for i,p in enumerate(PAGES)]})
write('evidence/visual-review.json', {'method':'Poppler original page renders inspected before literal transcription; source native text anchors cross-checked independently of app',
 'original_pages':PAGES,'inspection':'page titles, years, column labels, units, wrapped labels, table continuation and all cited amounts checked',
 'poppler_warnings':['No display font for Symbol/ArialUnicode; rendered Chinese/numbers manually inspected legible'], 'model_calls':0,
 'renders':[{'file':f'original-page-{p}.png','sha256':sha(OUT/f'evidence/original-page-{p}.png')} for p in PAGES]})
write('manifest.json', {'version':'report-correction-0.1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'gold_and_input_locked_before_model_run','first_model_run_started':False,
 'sampling':'Purpose-stratified planted-error challenge, task-level held out; source report previously used in extraction development',
 'company':'贵州茅台','correct_claims':16,'reasonable_opinions':3,'planted_errors':12,
 'files':{name:sha(OUT/name) for name in ['REPORT.txt','TASK.txt','PROTOCOL.txt','gold.json','source-map.json','inputs/moutai_2024_correction_sources.pdf']},
 'original_source_sha256':source_hash,'input_pages':len(PAGES), 'gold_not_for_model':True})
print(json.dumps({'status':'prepared','correct_claims':16,'opinions':3,'planted_errors':12,'gold_sha256':sha(OUT/'gold.json'),'input_sha256':sha(OUT/'inputs/moutai_2024_correction_sources.pdf')},ensure_ascii=False))

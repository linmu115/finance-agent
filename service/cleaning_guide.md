财报/研报清洗由 Pi 规划、Python 规则映射、宿主从原格取数。完整覆盖，不能因复杂而排除财务表。

process_documents 给出结构分组计划和 next_batch（完整 rows + 页上下文）。批次视图 rows=[{row:一基行号,cells:原格数组}]；SDK 的 c.table(index)['rows'] 仍是二维数组。一次脚本处理这一组；每表只调用一次 map_table/map_series，包含所有期间和数据列。提交后调用 get_cleaning_batch 取下一组，不重新请求全目录。结构分组不是共同语义假设：每表期间、单位、口径以原文为准。当前批完整原行已返回，无需用脚本 print 再取相同内容。疑点可按需 get_source_page/get_source_table 读完整上下文。进度由程序保存，无需逐表确认。

run_cleaning_script 的 Python 在无网络沙箱运行。输入 /input/cleaning_source.json 含 company、report_year、document_profile、pages、tables。完整原文不裁剪。
```
import sys
sys.path.insert(0, '/input')
from cleaning_sdk import Cleaner
c = Cleaner()
# c.tables 是 {index: table} 字典；c.table(index)['rows'] 是二维字符串列表。
# index 零基；row/column 一基。
for index in indices:  # 本批表号
    c.map_table(index, columns=[{'column':2,'period':'2025-H1','start':'2025-01-01','end':'2025-06-30'}, {'column':3,'period':'2024-H1','start':'2024-01-01','end':'2024-06-30'}],
        statement='notes', scope='consolidated_IFRS', currency='CNY', unit='千元',
        company='原文报告主体', metrics={'原文行名':'financial_meaning_id'},
        skip_rows={1:'原表期间表头'}, skip_columns={}, row_overrides={})
c.save()
```
上例仅展示 API，不能套用示例期间/单位。statement: income/balance/cashflow/ratios/segment/notes；scope: consolidated_IFRS/parent_IFRS/consolidated_CAS/parent_CAS/unspecified。

metrics 按原文财务含义命名，主营指标复用 revenue/net_profit_parent/assets 等目录ID。英文行名可自动生成英文ID；中文行名需映射。禁止 row_12、t2_r3 等行号ID。不同明细用 dimensions 或 row_overrides[row].dimensions_json 区分。

columns 列定义可写 semantic_type: ratio（构成比例）、growth_rate（变动比例）、percentage_points（百分点）、change_amount（变动额）。SDK 自动在该行指标后加 _share/_growth_rate/_change_pp/_change_amount 并设置比例单位，避免金额与比例同名。也可显式 metric/label/unit/currency。百分比单位 %，百分点单位 个百分点；每股 RMB cents 用 分/股，不能沿用千元。

row_overrides={行号:{metric,label,unit,dimensions_json,columns_json:[完整列定义]}}。覆盖 columns_json 时必须写全该行的数据列。附注号等非数据列使用 skip_columns={列号:原文理由}。空白不是0。真正无法判断的单元格用 row_overrides[row].unresolved_cells=[{column:列号,reason:具体语义或解析缺失原因}]，保留原文为待核验，不能将整表含糊排除。

合并单元格/空白标签跨行：若各数据列的数字按同一逻辑指标顺序排列，用 c.map_series(index, columns=完整列定义, metrics=[{'metric':'financial_id','label':'原文含义'},...], data_rows=range(首个数据行,末行+1), company=...,statement=...,scope=...,currency=...,unit=...)。它自动将每列连续原数字与含义一一配对，既支持整列挤在一格，也支持散落在多个空白标签行；数量不匹配会报具体列与数量，绝不重写数字或猜标签。需要时 metrics 的各项可另设单位等属性。逻辑含义列表须包含原表小计/合计，不能把“Revenue”等组标题误作第一笔细分金额。

仅单行挤有多值时，也可 row_overrides={行号:c.packed_row(index,行号,完整列定义,[{'metric':'financial_id','label':'原文含义'},...])}。若数字与含义不按同一顺序排列，用 c.numeric_spans(index,row,column) 获取原文 text/start/end/polarity，再把对应 span 写入各列定义的 numeric_span，并给 metric/label/期间/单位。不含负号但原文明确为减少时 polarity='negative'。一个原列可有多条定义。row_subject=False 用于一格中多条独立指标；真正矩阵保留行主题。需要延用上一表表头时从相邻原文读取，不猜。

仅封面、目录、独立表头等非财务表可 c.exclude_table(index,具体理由)。股份、期权、股东持股、募集资金和担保金额均属财务信息。c.save() 写 /output/cleaning_result.json；不要打印全部结果。

run_cleaning_script 已等待短本地运行并返回校验摘要；ready 且无错误直接 commit_cleaning_result，无需先 get_cleaning_result。如执行仍 running，才按需查结果。commit 对每表独立校验，合法表正常入库，failed_tables 给原格与修复建议。完整细节可 get_cleaning_result(details=true,table_indices=[...])。reviews 可选，仅真实疑点才标 needs_review；不要求读回/核验表单。

局部修复可 script_refs:[run_id]，读取 /input/cleaning_<run_id>.json 的候选映射并只改相关表；已提交部分复用。脚本及其依赖也挂载为 .py。提交后继续 pending_tables、pending_script_tables 和研报 pending_pages，均空后再完成用户任务。无固定总步数上限；普通清洗 low，复杂疑点局部 high。

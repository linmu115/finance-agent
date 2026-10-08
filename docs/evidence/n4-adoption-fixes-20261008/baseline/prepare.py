"""Copy only the three authorized documents; never backup/read the whole DB."""
import json,shutil,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from service.store import Store

root=Path(__file__).resolve().parent
seed=root/'seed'
assert not seed.exists(),'Use existing frozen seed; do not overwrite it'
main=Path(r'D:\AI\财报agent\data\active')
source=sqlite3.connect((main/'finance.sqlite').as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
source.execute('BEGIN')
docs=['d84573bf6b584e7e874faa4c6adf454a','ab25c52089fd4db89fba046c9c811c46','3d9d0befd8374eed9a7488dbd8dd00d2']
selected=[dict(source.execute('SELECT * FROM documents WHERE document_id=?',(d,)).fetchone()) for d in docs]
projects=sorted({r['project_id'] for r in selected})
store=Store(seed)
counts={}
with store.connect(write=True) as target:
 def transfer(table,rows):
  rows=list(rows);counts[table]=len(rows)
  if rows:
   cols=rows[0].keys();sql=f'INSERT INTO {table} ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')'
   target.executemany(sql,[tuple(r) for r in rows])
 transfer('projects',source.execute('SELECT * FROM projects WHERE project_id IN (?,?)',projects))
 marks=','.join('?' for _ in docs)
 for table in ['documents','pages','source_tables','facts','chunks','document_profiles','document_profile_history','research_document_entities','research_records','research_page_reviews','normalization_batches']:
  transfer(table,source.execute(f'SELECT * FROM {table} WHERE document_id IN ({marks})',docs))
 entities=[r[0] for r in target.execute('SELECT DISTINCT entity_id FROM research_document_entities UNION SELECT DISTINCT entity_id FROM research_records')]
 if entities:transfer('research_entities',source.execute('SELECT * FROM research_entities WHERE entity_id IN ('+','.join('?' for _ in entities)+')',entities))
 chunk_ids=[r[0] for r in target.execute('SELECT chunk_id FROM chunks')]
 fts=[]
 for i in range(0,len(chunk_ids),500):
  batch=chunk_ids[i:i+500];fts.extend(source.execute('SELECT chunk_id,tokens FROM chunks_fts WHERE chunk_id IN ('+','.join('?' for _ in batch)+')',batch).fetchall())
 transfer('chunks_fts',fts)
 # No historical conversations, answers, models, workspaces or exports copied.
 for row in selected:
  relative=Path(row['relative_path']);(seed/relative).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(main/relative,seed/relative)
for project in projects:
 for filename in ['agent.md','skills.json']:
  src=main/'projects'/project/filename
  if src.exists():
   dst=seed/'projects'/project/filename;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
shutil.copy2(main/'settings.json',seed/'settings.json')
facts={d:source.execute('SELECT count(*) FROM facts WHERE document_id=?',(d,)).fetchone()[0] for d in docs}
source.close()
manifest={'code_commit':'7524cca6ad10fd48b77382efdeb01901b91c6710','expense_category':'研发预检','source':'3001 active SQLite scoped read-only transaction',
 'documents':[{k:r[k] for k in ['document_id','project_id','original_name','company','state','page_count']}|{'facts':facts[r['document_id']]} for r in selected],
 'copied_rows':counts,'omitted':['historical conversations','answers','saved models','exports','other documents including held-out'],
 'startup_note':'原生 Store 启动会把副本中 normalizing 文档标为 failed；两组一致，事实和原文不变。不将年报宣称完整入库。',
 'common_suffix':'仅基于当前项目已有材料分析，不联网，不重新入库或清洗。',
 'cases':[
  {'id':'Q1','document':docs[0],'project':projects[1] if False else selected[0]['project_id'],'prompt':'伊利 2024 年业绩为什么下滑？'},
  {'id':'Q2','document':docs[0],'project':selected[0]['project_id'],'prompt':'伊利 2024 年利润和现金流走势一致吗，有没有值得警惕的地方？'},
  {'id':'Q3','document':docs[0],'project':selected[0]['project_id'],'prompt':'扣非后看伊利 2024 年盈利质量如何？'},
  {'id':'Q4','document':docs[0],'project':selected[0]['project_id'],'prompt':'伊利 2024 年 Q4 表现怎么样？'},
  {'id':'Q5','document':docs[1],'project':selected[1]['project_id'],'prompt':'瑞和这半年报有没有口径调整或异常？'},
  {'id':'Q6','document':docs[2],'project':selected[2]['project_id'],'prompt':'卡罗特这半年利润为什么下降，主要是什么拖累？'}]}
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'documents':manifest['documents'],'copied_rows':counts},ensure_ascii=False))

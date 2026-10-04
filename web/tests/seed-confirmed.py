"""Isolated UI fixtures. Never seed these synthetic records into the user's DATA."""
import sys
import hashlib
from pathlib import Path
from service.store import Store, dumps, utcnow
from service.attachment_flows import record_processing
root=Path(sys.argv[1]).resolve()
assert 'acceptance-confirmed' in str(root), 'isolated acceptance path required'
store=Store(root);now=utcnow();file=root/'uploads'/'fixture.csv';file.write_text('项目,2024\n营业收入,10000\n',encoding='utf-8')
with store.connect(write=True) as db:
    for p,n in [('acceptance','施工验收 · 合成资料'),('unrelated','另一个项目')]:db.execute('INSERT OR IGNORE INTO projects VALUES(?,?,?)',(p,n,now))
    db.execute('INSERT OR REPLACE INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,state,parser_version,page_count,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',('fixture','acceptance','合成财报.csv',hashlib.sha256(file.read_bytes()).hexdigest(),'uploads/fixture.csv','text/csv','ready','fixture',1,now))
    db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?,?,?)',('fixture',1,'合成财报：营业收入 10000 元','1',0,0,0))
    db.execute('INSERT OR REPLACE INTO source_tables VALUES(?,?,?,?,?,?,?)',('fixture_table','fixture',1,'利润表','[]',dumps([['项目','2024'],['营业收入','10000']]),'[]'))
    state={'processing_id':'attempt1','project_id':'acceptance','owner_run_id':'run1','state':'queued','created_at':now,'updated_at':now,'documents':[{'document_id':'fixture','name':'合成财报.csv','state':'queued','fact_count':0}]}
    record_processing(db,state)
    db.execute('INSERT OR REPLACE INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('fixture_fact','fixture','acceptance','合成公司','revenue',2024,'2024FY','consolidated_CAS','CNY','10000','元','10000',dumps({'document_id':'fixture','page':1,'table_id':'fixture_table','row':2,'normalization':{'engine':'LangExtract','version':'fixture','label':'营业收入','statement':'income'}}),1,'fixture'))
    state['state']='completed';state['documents'][0].update(state='ready',fact_count=1,progress=1);record_processing(db,state)
    for chat_id,title,owner,attachments in [('chat1','附件核验示例','run1',['fixture']),('chat2','空白会话','run2',[])]:
        messages=[{'id':'u'+owner,'role':'user','content':'请核对合成附件。','createdAt':now,'attachments':attachments},{'id':'a'+owner,'role':'assistant','content':'这是独立验收数据，仅验证界面与处理记录。','createdAt':now,'runId':owner,'status':'completed'}]
        chat={'id':chat_id,'projectId':'acceptance','title':title,'messages':messages,'createdAt':now,'updatedAt':now}
        db.execute('INSERT OR REPLACE INTO app_state VALUES(?,?,?,?,?)',('acceptance','conversations',chat_id,dumps(chat),now))
print('isolated UI fixture prepared')

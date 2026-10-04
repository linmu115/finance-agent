"""Prepare isolated annotation interaction fixtures, never production data."""
from pathlib import Path
import json
import runpy
from service.store import dumps

# Inherits seed-confirmed.py's required isolated-path assertion and sys.argv[1].
fixture = runpy.run_path(str(Path(__file__).with_name('seed-confirmed.py')))
store = fixture['store']
with store.connect(write=True) as db:
    row = db.execute("SELECT value_json FROM app_state WHERE kind='conversations' AND key='chat1'").fetchone()
    chat = json.loads(row[0])
    chat['messages'][1]['content'] = (
        '这是独立验收数据，仅验证界面与处理记录。\n\n'
        '第一处：**经营现金流**需要核对单位。第二处：**经营现金流**需要核对期间。\n\n'
        '| 项目 | 数值 |\n| --- | --- |\n| 营业收入 | 10000 元 |'
    )
    db.execute("UPDATE app_state SET value_json=? WHERE kind='conversations' AND key='chat1'", (dumps(chat),))
print('annotation fixture ready: repeated quotes, Markdown and a table')

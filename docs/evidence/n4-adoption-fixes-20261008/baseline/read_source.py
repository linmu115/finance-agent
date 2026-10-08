import sqlite3,json,sys
from pathlib import Path
base=Path(__file__).parent
db=sqlite3.connect((base/'seed/finance.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
doc, *pages=sys.argv[1:]
for page in pages:
    row=db.execute('SELECT * FROM pages WHERE document_id=? AND page=?',(doc,int(page))).fetchone()
    print(json.dumps(dict(row),ensure_ascii=False))

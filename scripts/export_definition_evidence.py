"""Read accepted definition reviews using SQLite read-only mode, without Store."""
import argparse,json,sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--project',required=True);a=p.parse_args()
database=Path(__file__).resolve().parents[1]/'data/finance.sqlite'
with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
 reviews=[json.loads(r[0]) for r in db.execute('SELECT report_json FROM fact_definition_reviews WHERE project_id=? ORDER BY created_at',(a.project,))]
 keys={audit['cache_key'] for review in reviews for audit in review.get('audits',[])}
 caches={key:json.loads(db.execute('SELECT result_json FROM fact_definition_cache WHERE cache_key=?',(key,)).fetchone()[0]) for key in keys}
 histories=[]
 for review in reviews:
  for row in db.execute('SELECT history_id,processing_id,fact_json,archived_at FROM fact_history WHERE project_id=? AND processing_id=?',(a.project,review['processing_id'])):
   histories.append({'review_id':review['review_id'],'history_id':row[0],'processing_id':row[1],'fact':json.loads(row[2]),'archived_at':row[3]})
print(json.dumps({'source':'host_sqlite_readonly','reviews':reviews,'caches':caches,'histories':histories},ensure_ascii=False))

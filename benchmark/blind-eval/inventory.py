"""Read-only document inventory and explicit, non-billing preparation estimates."""
import json,sqlite3
from pathlib import Path
from blind import ROOT,dump
dest=ROOT/'data/evaluation/blind-eval-preparation-20261007'
databases=[]
for relative,role in [('data/active/finance.sqlite','active'),('data/finance.sqlite','legacy_not_active')]:
    db=ROOT/relative;conn=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    docs=[]; tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for row in conn.execute('SELECT p.name project_name,d.project_id,d.document_id,d.original_name,d.page_count,d.state,d.sha256 FROM documents d JOIN projects p ON p.project_id=d.project_id ORDER BY d.project_id,d.document_id'):
        row=dict(row);counts={}
        for table in ['facts','research_records','source_tables']:
            counts[table]=conn.execute(f'SELECT count(*) FROM {table} WHERE document_id=?',(row['document_id'],)).fetchone()[0] if table in tables else None
        row['counts']=counts;docs.append(row)
    conn.close();databases.append({'database':relative,'role':role,'read_mode':'sqlite URI mode=ro; SELECT only','documents':docs})
history=json.loads((ROOT/'data/evaluation/pi-finance-generalization-20261006/preparation-status.json').read_text('utf-8'))
pages=102;tot=history['totals']
candidates=[]
for title,count,status in [('青岛啤酒2024年报',225,'paused_at_existing_checkpoint_await_Claude_after_N3_fix'),('光大2024-05-12行业周报',10,'authorized_single_attempt_now_no_manual_continuation'),('华泰2024-10-30伊利点评',6,'authorized_single_attempt_now_no_manual_continuation'),('光大2024-11-04伊利点评',3,'authorized_single_attempt_now_no_manual_continuation')]:
    candidates.append({'title':title,'pages':count,'status':status,'estimated_input_tokens':[round(tot['input']/pages*count*.5),round(tot['input']/pages*count*2)],'estimated_output_tokens':[round(tot['output']/pages*count*.5),round(tot['output']/pages*count*2)],'estimated_monetary_cost':None,'estimate_method':'0.5x–2x per-page historical preparation known usage, not an upper bound or billing quote. Prior sample mixed two models, manual continuations and repairs; 195 requests have unknown usage. Very low confidence; new simplifications may change it substantially.'})
dump(dest/'material-inventory.json',{'at':'2026-10-07','service_observation':'3001 healthy confirmed by mainline and read-only GET before authorized preparation; no service management by N1','databases':databases,'candidate_preparation':candidates,'excluded_current_scope':{'yili_2023':'not required, do not ingest','yili_2024':'N3 owns full reingestion into374beac2 after repair; no migration and no N1 execution','midea_2024':'deferred until N2 peer workpaper','haier_2024':'deferred until N2 peer workpaper'},'historical_calibration':{'file':'data/evaluation/pi-finance-generalization-20261006/preparation-status.json','pages':pages,'totals':tot},'cost_formula':'USD = uncached_input/1e6 * P_in + cached_input/1e6 * P_cache + output/1e6 * P_out; rates and cache split unverified, hence monetary cost null. Ingestion is separate from analysis.','live_preparation_ledger':'data/evaluation/blind-eval-ingestion-20261007/preparation.json'})
print(json.dumps({'databases':len(databases),'active_documents':len(databases[0]['documents']),'writes_to_databases':0}))

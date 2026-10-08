"""N2 development replay. Fixed allowed sources only; no held-out materials."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from service.core import FinanceService
from service.store import Store

DOCS = {
    'yili': ('374beac2-a970-4972-b210-e91018bbd6e6', 'd84573bf6b584e7e874faa4c6adf454a'),
    'haier': ('d324c744-4113-4213-aa22-af3bb91a3c84', 'e7b0d9679ddc4b739f8f35ecb6dc6227'),
    'carote': ('03b52dde-19da-49c1-949a-ee6d93bf036b', '3d9d0befd8374eed9a7488dbd8dd00d2'),
    'ruihe': ('374beac2-a970-4972-b210-e91018bbd6e6', 'ab25c52089fd4db89fba046c9c811c46'),
    'moutai': ('v3-moutai', 'v3-moutai-native'),
}
KINDS = ('statement_analysis', 'comparison', 'period_analysis', 'variance_attribution', 'anomaly_signals', 'analysis_pipeline')


class ReadOnlyStore(Store):
    def __init__(self, database, root):
        self.path = Path(database).resolve(); self.root = Path(root)

    @contextmanager
    def connect(self, write=False):
        if write: raise ValueError('replay_source_is_read_only')
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try: yield db
        finally: db.close()


def service_at(database, root):
    s = FinanceService.__new__(FinanceService); s.store = ReadOnlyStore(database, root)
    return s


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def direct_cells(value):
    found = set()
    def visit(v):
        if isinstance(v, dict):
            if v.get('source_method') == '原表直读':
                span = v.get('normalization', {}).get('numeric_span', {})
                found.add((v.get('document_id'), v.get('table_id'), v.get('row'), v.get('column'), span.get('start'), span.get('end')))
            for child in v.values(): visit(child)
        elif isinstance(v, list):
            for child in v: visit(child)
    visit(value)
    return len(found)


def prepare_moutai(pdf, root):
    from service.parser import parse_document
    root.mkdir(parents=True, exist_ok=True)
    dest = root / pdf.name
    if not dest.exists(): shutil.copyfile(pdf, dest)
    parsed_file = root / 'parsed.json'
    if parsed_file.exists(): parsed = json.loads(parsed_file.read_text('utf-8'))
    else:
        parsed = parse_document(dest, pdf.name, lambda *a: None, lambda: False, {})
        write(parsed_file, parsed)
    if (root / 'finance.sqlite').exists(): return
    s = FinanceService(root)
    for pool in ('pool', 'analysis_pool', 'embedding_pool', 'processing_pool'): getattr(s, pool).shutdown(wait=True)
    project, did = DOCS['moutai']; s.create_project(project, 'Moutai development direct-table replay')
    with s.store.connect(write=True) as db:
        db.execute('INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,company,report_year,state,parser_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (did, project, pdf.name, 'local-development-copy', dest.name, 'application/pdf', parsed['company'], parsed['report_year'], 'parsed', '0.1.4', '2026-10-08'))
        for p in parsed['pages']: db.execute('INSERT INTO pages(document_id,page,text) VALUES(?,?,?)', (did, p['page'], p['text']))
        for t in parsed['tables']:
            db.execute('INSERT INTO source_tables VALUES(?,?,?,?,?,?,?)', (f"{did}:t{t['index']}", did, t['page'], t.get('sheet'), json.dumps(t.get('bbox', [])), json.dumps(t['rows'], ensure_ascii=False), json.dumps(t.get('cells', {}))))
        db.execute('INSERT INTO prepared_documents VALUES(?,?,?,?,?)', (did, 'local-development-copy', '0.1.4', json.dumps(parsed, ensure_ascii=False), '2026-10-08'))
    print('moutai native source:', len(parsed['pages']), 'pages,', len(parsed['tables']), 'tables, zero facts', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--moutai-pdf', type=Path)
    ap.add_argument('--names', nargs='+', choices=list(DOCS), default=list(DOCS))
    ap.add_argument('--kinds', nargs='+', choices=KINDS, default=KINDS)
    args = ap.parse_args()
    if args.moutai_pdf: prepare_moutai(args.moutai_pdf, args.snapshot.parent / 'moutai')
    summary = []
    for name in args.names:
        project, did = DOCS[name]
        db = args.snapshot if name != 'moutai' else args.snapshot.parent / 'moutai/finance.sqlite'
        s = service_at(db, args.snapshot.parent / 'deliveries')
        for kind in args.kinds:
            start = time.monotonic()
            result = s.financial_workpaper(project, kind, document_id=did)
            write(args.out / name / (kind + '.json'), result)
            tabs = result.get('data', {}).get('numeric_tables', {})
            row = {'company': name, 'kind': kind, 'status': result['status'], 'seconds': round(time.monotonic() - start, 3),
                   'error': result.get('data', {}).get('error'), 'tables': len(tabs),
                   'numeric_cells': sum(v is not None for t in tabs.values() for r in t['rows'] for k, v in r.items() if t['columns'].get(k, {}).get('unit') or t['columns'].get(k, {}).get('per_cell_unit')),
                   'source_table_read_cells': direct_cells(result)}
            summary.append(row); print(row, flush=True)
    write(args.out / 'summary.json', summary)


if __name__ == '__main__': main()

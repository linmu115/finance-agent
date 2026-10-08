"""Read-only developer-data measurement; emit private replay fixtures, no LLM/HTTP."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp.server.fastmcp.utilities.func_metadata import _convert_to_content
from mcp.types import CallToolResult, JSONRPCResponse, TextContent
from service.core import FinanceService
from service.store import Store
from service.evaluation_isolation import evaluation_profile
from service.mcp_payloads import PayloadFiles, INLINE_BYTES

ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
cases=a.output/'cases';cases.mkdir(exist_ok=True)

class ReadStore(Store):
    def __init__(self,root):self.root=root
    @contextmanager
    def connect(self,write=False):
        assert not write,'production write forbidden'
        db=sqlite3.connect((a.source/'finance.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()

def encode(result, financial=False):
    if financial:
        kind=result['data']['kind']
        text=({**result,'data':{'kind':kind,'context':result['data'].get('context'),'error':result['data'].get('error')}} if kind=='analysis_pipeline' else result)
        tool=CallToolResult(content=[TextContent(type='text',text=json.dumps(text,ensure_ascii=False))],structuredContent=result)
    else:
        tool=CallToolResult(content=_convert_to_content(result),structuredContent=result,isError=False)
    return JSONRPCResponse(jsonrpc='2.0',id=1,result=tool.model_dump(mode='json',exclude_none=True)).model_dump_json(by_alias=True,exclude_none=True)+'\n'

summary=[]
with tempfile.TemporaryDirectory(prefix='finance-mcp-size-') as temp:
    svc=FinanceService.__new__(FinanceService);svc.store=ReadStore(Path(temp))
    # Images are HTTP paths, never embedded in these MCP responses. Retain that
    # returned path; avoid rendering hundreds of identical PDFs for a byte test.
    svc._render_source_page=lambda *_:None
    for company,prefix in [('yili','374beac2'),('haier','d324c744')]:
        with svc.store.connect() as db:
            project=db.execute('select project_id from projects where project_id like ?',(prefix+'%',)).fetchone()[0]
            docs=[r[0] for r in db.execute('select document_id from documents where project_id=?',(project,))]
        for profile in ('original_pi','prepared','financial'):
            token=evaluation_profile.set(profile)
            try:
                for method in ('get_source_table','get_source_page'):
                    biggest=None;scanned=0
                    for doc in docs:
                        with svc.store.connect() as db:
                            ids=([None]+[r[0] for r in db.execute('select table_id from source_tables where document_id=?',(doc,))]) if method=='get_source_table' else [r[0] for r in db.execute('select page from pages where document_id=?',(doc,))]
                        for identifier in ids:
                            result=getattr(svc,method)(project,doc,identifier)
                            wire=encode(result);scanned+=1
                            if biggest is None or len(wire.encode())>biggest[0]:biggest=(len(wire.encode()),wire,doc,identifier)
                    if biggest:
                        count,wire,doc,identifier=biggest;name=company+'-'+profile+'-'+method
                        payloads=PayloadFiles(a.output);small=payloads.pack(wire)
                        assert len(small.encode())<=INLINE_BYTES
                        packed=json.loads(small)
                        restored=(payloads.folder/(packed['result']['_finance_payload']+'.json')).read_text(encoding='utf8') if '_finance_payload' in packed['result'] else small
                        assert json.loads(restored)==json.loads(wire)
                        (cases/(name+'.json')).write_bytes(wire.encode())
                        summary.append({'case':name,'tool':method,'profile':profile,'company':company,'scanned':scanned,'document_id':doc,'selector':identifier,'original_mcp_bytes':count,'bounded_mcp_bytes':len(small.encode()),'sha256':hashlib.sha256(wire.encode()).hexdigest(),'round_trip_equal':True})
            finally:evaluation_profile.reset(token)
    # The financial host pipeline's exact persisted output, not an invented table.
    audit=a.source/'audit'/'e87b6b7f-f0c1-46c7-af23-a61abf2663b1.jsonl'
    pipeline=[]
    for line in audit.read_text(encoding='utf8').splitlines():
        event=json.loads(line);d=event.get('data',{})
        if event['type']=='tool_result' and d.get('name')=='financial_workpaper':pipeline.append(d['result'])
    for i,result in enumerate(pipeline):
        wire=encode(result,financial=True);name='yili-financial-workpaper-'+str(i)
        (cases/(name+'.json')).write_bytes(wire.encode())
        small=PayloadFiles(a.output).pack(wire)
        summary.append({'case':name,'tool':'financial_workpaper','profile':'financial','original_mcp_bytes':len(wire.encode()),'bounded_mcp_bytes':len(small.encode())})
    # N1's exact failing download (Carote, not held-out); manifest/content read only.
    svc.store.root=a.source
    result=svc.get_artifact('03b52dde-19da-49c1-949a-ee6d93bf036b','908d370d55db477e912e69530a1d8c63','chart_data.json')
    wire=encode(result);(cases/'incident-chart-data.json').write_bytes(wire.encode())
    small=PayloadFiles(a.output).pack(wire)
    summary.append({'case':'incident-chart-data','tool':'get_artifact','file_bytes':result['data']['size'],'original_mcp_bytes':len(wire.encode()),'bounded_mcp_bytes':len(small.encode())})
(a.output/'real-sizes.json').write_bytes((json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'cases':len(summary),'max_original_bytes':max(r['original_mcp_bytes'] for r in summary),'max_bounded_bytes':max(r['bounded_mcp_bytes'] for r in summary)},ensure_ascii=False))

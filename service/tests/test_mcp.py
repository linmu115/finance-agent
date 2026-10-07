"""Actual stdio protocol smoke test, not direct Python method substitution."""
import asyncio
import os
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPProtocolTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_and_structured_content(self):
        with tempfile.TemporaryDirectory() as root:
            params=StdioServerParameters(command=sys.executable,args=["-m","service.server"],
                                        cwd=str(Path(__file__).resolve().parents[2]),env={**os.environ,"FINANCE_DATA_DIR":root})
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    await session.initialize()
                    tools=await session.list_tools()
                    self.assertIn("get_financial_metrics",[t.name for t in tools.tools])
                    saved={t['name']:t for t in json.loads((Path(__file__).resolve().parents[1]/'tool-schema.json').read_text(encoding='utf8'))}
                    for tool in tools.tools:
                        if tool.name in {'begin_script_cleaning','get_cleaning_batch','get_cleaning_progress','set_document_profile','run_cleaning_script','get_cleaning_result'}:
                            self.assertEqual(tool.inputSchema,saved[tool.name]['inputSchema'])
                            self.assertEqual(tool.description,saved[tool.name]['description'])
                    created=await session.call_tool("create_project",{"project_id":"proto","name":"Protocol test"})
                    self.assertEqual(created.structuredContent["status"],"ok")
                    # Real wire error must carry match information, not just ValueError.
                    prior='f'*32
                    export=Path(root)/'exports'/'proto'/prior;export.mkdir(parents=True)
                    (export/'analysis.py').write_text('print(1)\nprint(1)',encoding='utf-8')
                    (export/'analysis_inputs.json').write_text('{}',encoding='utf-8')
                    with closing(sqlite3.connect(Path(root)/'finance.sqlite')) as db:
                        db.execute('INSERT INTO analysis_jobs VALUES(?,?,?,?,?)',(prior,'proto',json.dumps({'status':'failed'}),'fixture','fixture'))
                        db.commit()
                    mismatch=(await session.call_tool('run_analysis',{'project_id':'proto','source_run_id':prior,'edits':[{'before':'print(1)','after':'print(2)'}]})).structuredContent
                    self.assertEqual(mismatch['status'],'error')
                    self.assertIn('edit 1 matched 2 occurrences',mismatch['data']['error'])
                    self.assertEqual(mismatch['data']['details']['matches'],2)
                    path=Path(root)/"uploads"/"protocol.csv"
                    path.write_text("指标,2024年,2023年,单位\n营业收入,12,10,万元\n",encoding="utf-8")
                    incoming=await session.call_tool("ingest_document",{"project_id":"proto","path":str(path),"original_name":"protocol.csv"})
                    job=incoming.structuredContent["data"]["job_id"]
                    for _ in range(100):
                        state=(await session.call_tool("get_ingestion_status",{"project_id":"proto","job_id":job})).structuredContent["data"]
                        if state["state"] in {"ready","needs_review","failed"}:break
                        await asyncio.sleep(.05)
                    self.assertEqual(state["state"],"ready",state)
                    queried=(await session.call_tool("get_financial_metrics",{"project_id":"proto","metrics":["revenue"],"years":[2024]})).structuredContent
                    self.assertEqual(queried["data"]["items"][0]["value"],"120000")
                    failed=(await session.call_tool("get_financial_metrics",{"project_id":"other","metrics":["revenue"]})).structuredContent
                    self.assertEqual(failed["status"],"error")

if __name__=="__main__":unittest.main()

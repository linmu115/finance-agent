"""Actual stdio protocol smoke test, not direct Python method substitution."""
import asyncio
import os
import sys
import tempfile
import unittest
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
                    created=await session.call_tool("create_project",{"project_id":"proto","name":"Protocol test"})
                    self.assertEqual(created.structuredContent["status"],"ok")
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


import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from service.core import FinanceService
from service.evaluation_isolation import evaluation_profile
from service.mcp_payloads import PayloadFiles, PayloadStdout, INLINE_BYTES


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.payloads=PayloadFiles(self.root)

    def test_full_large_result_and_request_round_trip(self):
        for size in (7_221_871,32*1024*1024):
            full={'jsonrpc':'2.0','id':4,'result':{'content':'x'*size}}
            raw=json.dumps(full)+'\n';wire=self.payloads.pack(raw)
            self.assertLess(len(wire.encode()),INLINE_BYTES)
            handle=json.loads(wire)['result']['_finance_payload']
            self.assertEqual(json.loads((self.payloads.folder/(handle+'.json')).read_bytes()),full)
        full={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'render_answer','arguments':{'body':'中'*4_000_000},'_meta':{'finance_evaluation_isolation_key':'chain'}}}
        handle='c'*32;(self.payloads.folder/(handle+'.json')).write_bytes(json.dumps(full).encode())
        wire=json.dumps({'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'_finance_payload':handle}})
        self.assertEqual(json.loads(self.payloads.unpack(wire)),full)
        with self.assertRaisesRegex(ValueError,'invalid_mcp_payload_handle'):
            self.payloads.unpack(wire.replace(handle,'../foreign'))

    def test_failed_file_write_returns_only_matching_request_error(self):
        class Output:
            text=''
            async def write(self,text):self.text+=text
            async def flush(self):pass
        output=Output();writer=PayloadStdout(output,self.payloads)
        with patch.object(self.payloads,'pack',side_effect=OSError('disk full')):
            asyncio.run(writer.write(json.dumps({'jsonrpc':'2.0','id':7,'result':{'value':1}})))
        message=json.loads(output.text);self.assertEqual(message['id'],7)
        self.assertIn('mcp_payload_write_failed',message['error']['message'])
        output.text='';asyncio.run(writer.write('{"jsonrpc":"2.0","id":8,"result":{}}\n'))
        self.assertEqual(json.loads(output.text)['id'],8)

    def test_download_metadata_never_parses_content_and_keeps_authorization(self):
        service=FinanceService(self.root)
        self.addCleanup(lambda:[getattr(service,n).shutdown(wait=True) for n in ('pool','processing_pool','analysis_pool','embedding_pool')])
        source=self.root/'large.json';source.write_bytes(b'{"text":"'+b'x'*7_221_871+b'"}')
        for profile in ('original_pi','prepared','financial'):
            token=evaluation_profile.set(profile)
            try:
                with patch.object(service,'artifact_path',return_value=source) as path,patch('service.analysis_tables.artifact_content',side_effect=AssertionError('download parsed content')):
                    result=service.get_artifact('project','run',source.name,include_content=False)['data']
                    path.assert_called_once_with('project','run',source.name)
                    self.assertNotIn('content',result);self.assertEqual(result['size'],source.stat().st_size)
                with patch.object(service,'artifact_path',side_effect=ValueError('analysis_not_found_in_project')):
                    with self.assertRaisesRegex(ValueError,'analysis_not_found_in_project'):
                        service.get_artifact('other','run',source.name,include_content=False)
            finally:evaluation_profile.reset(token)


if __name__=='__main__':unittest.main()

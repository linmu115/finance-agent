import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from langextract.factory import create_model
from service.pi_provider import pi_model_config, PiBridgeLanguageModel


class PiProviderTests(unittest.TestCase):
    def test_loopback_ignores_system_proxy_and_does_not_repeat_failed_inference(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                status = 502 if len(received) == 2 else 200
                value = ({"error": {"message": "test_failure", "type": "runtime_error"}} if status == 502 else
                         {"id": "local", "object": "chat.completion", "created": 0, "model": "test",
                          "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}]})
                body=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        runtime={'model':'test','api_key':'local-fixture','base_url':f'http://127.0.0.1:{server.server_port}/run/v1'}
        try:
            # A dead proxy reproduces the Windows registry proxy path without
            # waiting for an actual intermediary's 120-second timeout.
            with patch.dict('os.environ', {'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}), patch('httpx._utils.getproxies',return_value={'http':'http://127.0.0.1:1'}):
                model=create_model(pi_model_config(runtime,max_workers=1))
                try:
                    self.assertEqual(list(model.infer(['中文财务证据']))[0][0].output,'{}')
                    with self.assertRaises(Exception): list(model.infer(['failed request']))
                    self.assertEqual(len(received),2)
                    self.assertIn('中文财务证据',json.dumps(received[0],ensure_ascii=False))
                    self.assertEqual(model._client.max_retries,0)
                finally:model._client.close()
        finally:server.shutdown();server.server_close();thread.join(3)

    def test_bridge_provider_cannot_be_pointed_at_external_model_api(self):
        with self.assertRaisesRegex(ValueError,'pi_runtime_bridge_required'):
            PiBridgeLanguageModel(model_id='test',base_url='https://api.example.com',api_key='fixture')


if __name__ == '__main__': unittest.main()

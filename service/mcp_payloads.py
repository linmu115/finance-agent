"""Local stdio payload handles; business results and project scopes stay intact."""
import json
import re
import sys
import uuid
from pathlib import Path

INLINE_BYTES = 2 * 1024 * 1024  # Below the SDK's 10 MiB buffer, including framing.
MARKER = '_finance_payload'


class PayloadFiles:
    def __init__(self, root):
        self.folder = Path(root) / '.mcp-payloads'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.requests = {}

    def unpack(self, line):
        message = json.loads(line)
        handle = message.get('params', {}).get(MARKER)
        if handle is not None:
            if not isinstance(handle, str) or not re.fullmatch('[a-f0-9]{32}', handle):
                raise ValueError('invalid_mcp_payload_handle')
            full = json.loads((self.folder / (handle + '.json')).read_bytes())
            if full.get('id') != message.get('id') or full.get('method') != message.get('method'):
                raise ValueError('mcp_payload_request_mismatch')
            line = json.dumps(full, ensure_ascii=False) + '\n'
            message = full
        if 'id' in message and 'method' in message:
            self.requests[message['id']] = message.get('params', {}).get('name', message['method'])
        return line

    def pack(self, line):
        raw = line.encode('utf8')
        message = json.loads(line)
        name = self.requests.pop(message.get('id'), None)
        if len(raw) <= INLINE_BYTES:
            return line
        handle = uuid.uuid4().hex
        target = self.folder / (handle + '.json')
        # Publish only once complete; stdout advertises the handle afterwards.
        with target.open('xb') as stream:
            stream.write(raw)
        wire = {'jsonrpc': '2.0'}
        if 'id' in message: wire['id'] = message['id']
        if 'method' in message:
            wire.update(method=message['method'], params={MARKER: handle})
        else:
            wire['result'] = {MARKER: handle}
        print(json.dumps({'event': 'mcp_payload', 'tool': name, 'id': message.get('id'),
                          'bytes': len(raw), 'handle': handle}), file=sys.stderr)
        return json.dumps(wire) + '\n'


class PayloadStdout:
    def __init__(self, stream, payloads):
        self.stream, self.payloads = stream, payloads

    async def write(self, line):
        import anyio
        try:
            wire = await anyio.to_thread.run_sync(self.payloads.pack, line)
        except (OSError, ValueError) as exc:
            message = json.loads(line)
            if 'id' not in message: raise
            wire = json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {
                'code': -32603, 'message': f'mcp_payload_write_failed: {type(exc).__name__}; 检查数据目录空间和权限后重读；写操作请先核对已提交状态。'}}) + '\n'
        await self.stream.write(wire)

    async def flush(self):
        await self.stream.flush()

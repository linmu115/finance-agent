"""Read a key without echo; send only to the official API and the local settings endpoint."""
import getpass
import json
import urllib.request
import urllib.error

key = getpass.getpass('DeepSeek API key (hidden): ')
try:
    request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer '+key})
    with urllib.request.urlopen(request, timeout=45) as response:
        models = json.load(response)
    ids = [item['id'] for item in models.get('data', [])]
    if 'deepseek-flash' not in ids:
        raise RuntimeError('Official /models did not list deepseek-flash: '+str(ids))
    settings = {'llm': {'provider': 'openai-compatible', 'baseUrl': 'https://api.deepseek.com', 'model': 'deepseek-flash', 'apiKey': key, 'contextWindow': 1048576, 'maxTokens': 8192}}
    request = urllib.request.Request('http://127.0.0.1:3001/api/settings', data=json.dumps(settings).encode(), headers={'Content-Type': 'application/json'}, method='PUT')
    with urllib.request.urlopen(request, timeout=45) as response:
        saved = json.load(response)
    print(json.dumps({'configured': True, 'official_model_ids': ids, 'llm': saved['llm']}, ensure_ascii=False))
except urllib.error.HTTPError as error:
    print(json.dumps({'configured': False, 'http_status': error.code}))
    raise SystemExit(1)
except Exception as error:
    print(json.dumps({'configured': False, 'error_type': type(error).__name__, 'message': str(error).replace(key, '[REDACTED]')}))
    raise SystemExit(1)
finally:
    key = ''

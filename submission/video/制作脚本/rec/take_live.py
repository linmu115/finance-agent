"""Take 2: a live financial analysis in the Yili project, recorded end to end."""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from recorder import BASE, YILI, Recorder, S

KEEP = ['c1bdf526-61f4-469f-a8d8-5087c840dddc', '03ccda64-164e-44ab-8c24-4337abb36a4e',
        'f8461957-682f-4018-a18e-f0fe82f315a5']
QUESTION = ('伊利2024年净利润下降，经营现金流却增加了约34亿元。原因是什么？'
            '这种改善能持续吗？请给出现金桥图和原文依据。')
out = Path(sys.argv[1] if len(sys.argv) > 1 else 'takes/live')
since = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def api(path):
    with urllib.request.urlopen('http://127.0.0.1:3001' + path, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def newest_conversation():
    data = api(f'/api/projects/{YILI}/conversations')
    items = data.get('conversations', data)
    fresh = [c for c in items if (c.get('createdAt') or '') >= since]
    return max(fresh, key=lambda c: c['createdAt']) if fresh else None


with Recorder(out, keep_conversations=KEEP, show_new_since=since) as r:
    p = r.page
    p.goto(BASE, wait_until='networkidle')
    r.wait(1.0)
    r.start()
    r.mark('home')
    box = p.locator('textarea').first
    r.click(box)
    r.wait(0.4)
    r.mark('typing')
    r.type(QUESTION, delay=48)
    r.wait(0.8)
    r.mark('send')
    p.keyboard.press('Enter')
    conv = None
    started = time.time()
    last_log = 0
    while time.time() - started < 900:
        r.wait(2.0)
        conv = conv or newest_conversation()
        if not conv:
            continue
        detail = api(f"/api/conversations/{conv['id']}")
        active = detail.get('activeRunId') or detail.get('activeRun') or (detail.get('conversation') or {}).get('activeRunId')
        if time.time() - last_log > 10:
            text = p.locator('main').inner_text() if p.locator('main').count() else ''
            r.mark('progress ' + text[-90:].replace('\n', ' | '))
            last_log = time.time()
        if not active and time.time() - started > 20:
            break
    r.mark('run_done')
    (out / 'conversation.json').write_text(json.dumps(api(f"/api/conversations/{conv['id']}"), ensure_ascii=False),
                                           encoding='utf-8')
    r.wait(2.5)
    p.screenshot(path=str(out / 'probe_done.png'))
    r.mark('end')
    r.wait(1.0)

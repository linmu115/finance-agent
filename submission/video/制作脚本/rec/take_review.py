"""Take 3: walk through the finished live analysis — answer, bridge, files, tool trail, report download."""
import sys
from pathlib import Path

from recorder import BASE, Recorder, S

import json as _json
CONV = _json.loads(Path('takes/live/conversation.json').read_text(encoding='utf-8')).get('conversation', {}).get('id') or _json.loads(Path('takes/live/conversation.json').read_text(encoding='utf-8'))['id']
KEEP = [CONV, 'c1bdf526-61f4-469f-a8d8-5087c840dddc', '03ccda64-164e-44ab-8c24-4337abb36a4e',
        'f8461957-682f-4018-a18e-f0fe82f315a5']
out = Path(sys.argv[1] if len(sys.argv) > 1 else 'takes/review')
REPORT = '--report' in sys.argv
CHAT_X, CHAT_Y = 1010 * S, 420 * S

with Recorder(out, keep_conversations=KEEP, fit=True) as r:
    p = r.page
    p.goto(BASE, wait_until='networkidle')
    r.wait(1.0)
    p.get_by_text('伊利2024年净利润下降，经营').first.click()
    r.wait(3.0)
    p.mouse.move(CHAT_X, CHAT_Y)
    for _ in range(40):
        p.mouse.wheel(0, -3000)
    r.wait(1.5)
    r.start()
    r.mark('question')
    r.wait(2.0)

    # Generous holds; the edit trims each hold to its narration sentence.
    r.wait(4.5)
    stops = [('bridge', '现金流同比桥', 5.5, 110), ('sources', '原文依据与解释', 5.0, 110), ('sustain', '能否持续', 9.0, 440)]
    for name, text, hold, top in stops:
        r.mark(name + '_scroll')
        r.scroll_to(p.get_by_text(text, exact=True), top=top, steps=34, x=CHAT_X, y=CHAT_Y)
        r.mark(name)
        r.wait(hold)
    p.screenshot(path=str(out / 'probe_answer_end.png'))

    # Jump past the trailing notices (cut in the edit), then glide through the delivered files.
    files = p.get_by_text('variance_drivers_evidence.csv').first
    files.scroll_into_view_if_needed()
    r.scroll_to(files, top=90, steps=2, x=CHAT_X, y=CHAT_Y)
    r.wait(0.8)
    r.mark('files')
    r.wait(1.2)
    r.scroll_to(p.get_by_text('plot_diagnostics.json').first, top=330, steps=40, x=CHAT_X, y=CHAT_Y)
    r.wait(0.4)
    r.move_to(p.get_by_text('executed_script.py').first, steps=30)
    r.wait(2.4)
    p.screenshot(path=str(out / 'probe_files.png'))

    r.mark('tools')
    tools = p.get_by_text('工具执行记录').first
    r.click(tools)
    r.wait(0.8)
    r.scroll(900 * S, steps=40, x=CHAT_X, y=CHAT_Y)
    r.mark('tools_end')
    r.wait(4.0)
    p.screenshot(path=str(out / 'probe_tools.png'))

    if REPORT:
        r.mark('report')
        r.click(p.get_by_text('财报分析报告').first)
        r.wait(6.0)
        p.screenshot(path=str(out / 'probe_report.png'))
    r.mark('end')
    r.wait(0.8)

"""Scripted, high-quality screen capture of the real Finance Agent UI.

Frames come from CDP Page.startScreencast (JPEG) with wall-clock timestamps;
every scripted action is logged so the edit can cut and retime by step.
The browser filters the project/conversation *lists* only (hides held-out
projects and evaluation sessions); every page shown is the real product.
"""
import base64
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:3001/'
YILI = '374beac2-a970-4972-b210-e91018bbd6e6'
KEEP_PROJECTS = {'default', YILI}
DISPLAY_NAMES = {YILI: '伊利股份 · 财报与研报'}
ZOOM = 4 / 3
S = ZOOM  # multiply 1440-layout coordinates by S to get viewport pixels

CURSOR_JS = r"""
(() => {
  if (window.__demoCursor) return; window.__demoCursor = true;
  const style = document.createElement('style');
  style.textContent = `
    #demo-cursor{position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;pointer-events:none;
      transform:translate(-3px,-2px);transition:transform .08s ease-out;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))}
    .demo-ripple{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;z-index:2147483646;
      pointer-events:none;border:2px solid rgba(46,111,106,.85);animation:demoRipple .55s ease-out forwards}
    @keyframes demoRipple{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}`;
  const add = () => {
    document.head.appendChild(style);
    const c = document.createElement('div'); c.id = 'demo-cursor';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M4 2l15 11-6.5 1.2L16 21l-3 1.4-3.6-6.9L4 20z" fill="#fff" stroke="#1f2a2e" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    const z = () => parseFloat(document.documentElement.style.zoom || '1');
    document.addEventListener('mousemove', e => { c.style.left = e.clientX / z() + 'px'; c.style.top = e.clientY / z() + 'px'; }, true);
    document.addEventListener('mousedown', e => {
      const r = document.createElement('div'); r.className = 'demo-ripple';
      r.style.left = e.clientX / z() + 'px'; r.style.top = e.clientY / z() + 'px'; document.body.appendChild(r);
      setTimeout(() => r.remove(), 600); c.style.transform = 'translate(-3px,-2px) scale(.85)';
    }, true);
    document.addEventListener('mouseup', () => { c.style.transform = 'translate(-3px,-2px)'; }, true);
  };
  if (document.body) add(); else document.addEventListener('DOMContentLoaded', add);
})();
"""


class Recorder:
    def __init__(self, out: Path, keep_conversations=(), show_new_since=None, fit=False):
        self.out = out
        self.fit = fit  # True: size the app to the visible 1080px instead of the zoomed 1440px
        (out / 'frames').mkdir(parents=True, exist_ok=True)
        self.keep_conv = set(keep_conversations)
        self.show_new_since = show_new_since
        self.frames = []
        self.events = []
        self.t0 = None
        self.mouse = (960, 540)

    # -- list filtering (presentation only) ---------------------------------
    def _filter(self, route):
        resp = route.fetch()
        if route.request.method != 'GET':
            return route.fulfill(response=resp)
        body = resp.json()
        url = route.request.url
        if url.rstrip('/').endswith('/api/projects'):
            body['projects'] = [dict(p, name=DISPLAY_NAMES.get(p['id'], p['name']))
                                for p in body['projects'] if p['id'] in KEEP_PROJECTS]
        else:
            key = 'conversations' if isinstance(body, dict) and 'conversations' in body else None
            items = body[key] if key else body

            def keep(c):
                if c.get('id') in self.keep_conv:
                    return True
                created = c.get('createdAt') or c.get('created_at') or ''
                return bool(self.show_new_since and created >= self.show_new_since)
            items = [c for c in items if keep(c)]
            if key:
                body[key] = items
            else:
                body = items
        route.fulfill(response=resp, body=json.dumps(body, ensure_ascii=False),
                      headers={**resp.headers, 'content-type': 'application/json; charset=utf-8'})

    # -- capture -----------------------------------------------------------
    def _on_frame(self, params):
        ts = time.time()
        if self.t0 is None:
            self.t0 = ts
        idx = len(self.frames)
        path = self.out / 'frames' / f'{idx:06d}.jpg'
        path.write_bytes(base64.b64decode(params['data']))
        self.frames.append((round(ts - self.t0, 4), path.name))
        try:
            self.cdp.send('Page.screencastFrameAck', {'sessionId': params['sessionId']})
        except Exception:
            pass

    def mark(self, name):
        t = time.time() - (self.t0 or time.time())
        self.events.append((round(t, 3), name))
        print(f'[{t:7.2f}] {name}', flush=True)

    def wait(self, seconds):
        self.page.wait_for_timeout(int(seconds * 1000))

    # -- humane input ------------------------------------------------------
    def move_to(self, locator, dx=0.5, dy=0.5, steps=28):
        box = locator.bounding_box()
        x, y = box['x'] + box['width'] * dx, box['y'] + box['height'] * dy
        self.page.mouse.move(x, y, steps=steps)
        self.mouse = (x, y)

    def click(self, locator, pause=0.35, **kw):
        locator.scroll_into_view_if_needed()
        self.move_to(locator, **kw)
        self.wait(pause)
        self.page.mouse.down(); self.wait(0.08); self.page.mouse.up()

    def type(self, text, delay=55):
        self.page.keyboard.type(text, delay=delay)

    def scroll(self, pixels, steps=24, x=None, y=None):
        if x is not None:
            self.page.mouse.move(x, y, steps=10)
        per = pixels / steps
        for _ in range(steps):
            self.page.mouse.wheel(0, per)
            self.wait(0.03)

    def scroll_to(self, locator, top=150, steps=34, x=1347, y=560):
        """Smooth-wheel so that `locator` sits `top` CSS px below the viewport top."""
        box = locator.first.bounding_box()
        if box is None:
            return
        self.scroll(box['y'] - top * S, steps=steps, x=x, y=y)

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(channel='chrome', headless=True)
        # Native 1920x1080 pixels; CSS zoom keeps the 1440-wide layout so text renders crisply.
        self.ctx = self.browser.new_context(viewport={'width': 1920, 'height': 1080},
                                            device_scale_factor=1, locale='zh-CN',
                                            accept_downloads=True)
        self.ctx.add_init_script("document.addEventListener('DOMContentLoaded',"
                                 "()=>{document.documentElement.style.zoom='%s';"
                                 "const s=document.createElement('style');"
                                 # zoom renders the 100dvh app 4/3 tall; clip it so the page itself never scrolls
                                 "s.textContent='html{overflow:hidden!important}"
                                 "body{height:75vh!important;overflow:clip!important}%s';"
                                 "document.head.appendChild(s)});"
                                 % (ZOOM, '.app{height:75dvh!important}' if self.fit else ''))
        self.ctx.add_init_script(CURSOR_JS)
        self.page = self.ctx.new_page()
        self.page.route('**/api/projects', self._filter)
        self.page.route('**/api/projects/*/conversations', self._filter)
        self.cdp = self.ctx.new_cdp_session(self.page)
        self.cdp.on('Page.screencastFrame', self._on_frame)
        return self

    def start(self):
        self.cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 92,
                                               'maxWidth': 1920, 'maxHeight': 1080, 'everyNthFrame': 1})
        self.wait(0.5)

    def __exit__(self, *exc):
        try:
            self.cdp.send('Page.stopScreencast')
        except Exception:
            pass
        (self.out / 'frames.json').write_text(json.dumps(self.frames), encoding='utf-8')
        (self.out / 'events.json').write_text(json.dumps(self.events, ensure_ascii=False, indent=1), encoding='utf-8')
        self.ctx.close(); self.browser.close(); self.pw.stop()

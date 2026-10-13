"""Render the execution-trace overlay as transparent PNG frames: render_trace.py <e0> <speed> <seconds>."""
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def render(e0, speed, seconds, fps=30):
    out = HERE / 'frames' / 'trace'
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        pg = b.new_page(viewport={'width': 1920, 'height': 1080})
        pg.goto((HERE / 'trace.html').as_uri())
        pg.wait_for_timeout(300)
        pg.evaluate(f'setup({e0}, {speed})')
        for i in range(int(round(seconds * fps))):
            pg.evaluate(f'seek({i / fps})')
            pg.screenshot(path=str(out / f'{i:05d}.png'), omit_background=True)
        b.close()
    return out


if __name__ == '__main__':
    print(render(float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])))

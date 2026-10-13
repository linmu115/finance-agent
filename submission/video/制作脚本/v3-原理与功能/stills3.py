"""Render review stills of stage3.html: per scene, one still shortly after each clause starts plus one near the end.

usage: python stills3.py [scene ...]   -> stills/<scene>_<k>.jpg and stills/sheet_<scene>.jpg
"""
import asyncio
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / 'stills'
OUT.mkdir(exist_ok=True)


def times_for(sc):
    C, E, D = sc['C'], sc['E'], sc['dur']
    ts = []
    for c, e in zip(C, E):
        ts += [c + 0.35 * (e - c), e - 0.1]
    ts.append(D - 0.8)
    return [round(t, 2) for t in ts]


async def main(only):
    tl = json.loads((HERE / 'timeline.json').read_text(encoding='utf-8'))
    errs = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel='chrome', headless=True)
        pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        await pg.goto((HERE / 'stage3.html').as_uri())
        await pg.evaluate('document.fonts.ready')
        await pg.evaluate('tl => setup(tl)', tl)
        for sc in tl['scenes']:
            if only and sc['id'] not in only:
                continue
            shots = []
            for k, lt in enumerate(times_for(sc)):
                await pg.evaluate('t => seek(t)', sc['start'] + lt)
                p = OUT / f"{sc['id']}_{k:02d}.jpg"
                await pg.screenshot(path=str(p), type='jpeg', quality=85)
                shots.append((p, lt))
            cols, w, h = 3, 640, 360
            rows = (len(shots) + cols - 1) // cols
            sheet = Image.new('RGB', (cols * w, rows * (h + 24)), 'white')
            d = ImageDraw.Draw(sheet)
            for i, (p, lt) in enumerate(shots):
                x, y = (i % cols) * w, (i // cols) * (h + 24)
                sheet.paste(Image.open(p).resize((w, h)), (x, y + 24))
                d.text((x + 6, y + 6), f"{sc['id']} {i:02d}  t={lt:.2f}", fill='black')
            sheet.save(OUT / f"sheet_{sc['id']}.jpg", quality=88)
            print(sc['id'], len(shots), flush=True)
        await b.close()
    print('errors:', errs[:20])


asyncio.run(main(set(sys.argv[1:])))

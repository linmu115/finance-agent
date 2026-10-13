"""Principle + product explainer: timeline -> footage frames -> HTML frames -> score -> mp4.

usage: python build_v3.py [timeline|footage|assets|frames|audio|mux|all] [--from S --to S]
"""
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TAKES = ROOT / 'rec' / 'takes'
FF = r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin\ffmpeg.exe'
FPS = 30
FW, FH = 1600, 900
K = FW / 1920
sys.path.insert(0, str(HERE))
from narration_v3 import LEAD, ORDER, TAIL  # noqa: E402

RUN_T0 = 5.96                     # raw second in the live take when the run started
TOOL_CALLS = [0.1, 31.8, 31.8, 31.8, 181.4, 197.9, 207.0, 220.6, 232.2, 246.0]   # run seconds (audit log)
TRACE = [(0.1, 14.4, '金融底稿 · 初步检索'), (31.8, 162.6, '三份底稿并行生成'), (181.4, 197.9, '沙箱 · 计算并画现金桥'),
         (207.0, 220.6, '沙箱复跑 · 修正负值柱画法'), (232.2, 246.0, '沙箱复跑 · 校正分项尾差'), (246.1, 283.4, '写回答 · 填入底稿数值')]


def run(cmd):
    subprocess.run(cmd, check=True)


def build_timeline():
    narr = json.loads((HERE / 'tts3' / 'narration.json').read_text(encoding='utf-8'))
    scenes, captions, voice, t = [], [], [], 0.0
    for sid in ORDER:
        lt, C, E = LEAD[sid], [], []
        for c in narr[sid]:
            C.append(round(lt, 3))
            E.append(round(lt + c['dur'], 3))
            voice.append({'file': c['file'], 't': round(t + lt, 3)})
            captions.append({'start': round(t + lt - 0.05, 3), 'end': round(t + lt + c['dur'] + c['pause'] * 0.8, 3),
                             'text': c['show'].rstrip('。，；：')})
            lt += c['dur'] + c['pause']
        D = round(lt + TAIL[sid], 3)
        scenes.append({'id': sid, 'start': round(t, 3), 'dur': D, 'C': C, 'E': E})
        t += D
    for a, b in zip(captions, captions[1:]):
        a['end'] = min(a['end'], b['start'])
    sc = {s['id']: s for s in scenes}
    clips = plan_clips(sc)
    tl = {'fps': FPS, 'duration': round(t, 3), 'scenes': scenes, 'clips': clips, 'captions': captions, 'voice': voice,
          'trace': [{'s': a, 'e': b, 'label': l} for a, b, l in TRACE], 'toolCalls': TOOL_CALLS}
    (HERE / 'timeline.json').write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding='utf-8')
    print('duration', tl['duration'], {s['id']: s['dur'] for s in scenes})
    return tl


def plan_clips(sc):
    out = {}
    s = sc['case']; C, D = s['C'], s['dur']
    sp = (8.6 - 1.6) / (D - C[1])
    send = C[1] + (5.9 - 1.6) / sp
    out['case'] = {'segs': [('live', 0.9, 1.6, 0.0, C[1]), ('live', 1.6, 8.6, C[1], D)],
                   'zoom': [[0, 1.0, 960, 540], [C[1] - 0.6, 1.0, 960, 540], [C[1] + 0.3, 1.45, 1130, 690],
                            [send + 0.2, 1.45, 1130, 690], [send + 0.9, 1.3, 1150, 330]]}
    s = sc['ingest']; C, D = s['C'], s['dur']
    out['ingest'] = {'segs': [('tour', 4.6, 9.6, C[4] - 0.3, C[5]), ('tour', 27.0, 33.6, C[5], D)],
                     'zoom': [[C[4] + 0.1, 1.0, 960, 540], [C[4] + 1.0, 1.75, 990, 640], [C[5] - 0.2, 1.75, 990, 640],
                              [C[5] + 0.4, 1.1, 1100, 560], [C[5] + 2.2, 1.35, 1500, 620]]}
    # loop: time-map the run so the two sandbox re-runs land on the sentences that describe them
    s = sc['loop']; C, D = s['C'], s['dur']
    ta, tb = C[3] + 0.4, C[4] + 0.4
    speed = (232.2 - 207.0) / (tb - ta)
    raw_at = lambda tt: RUN_T0 + 207.0 + (tt - ta) * speed
    t0 = 0.4
    r0 = max(8.6, raw_at(t0))
    t0 = ta - (207.0 + RUN_T0 - r0) / speed
    r1 = min(270.0, raw_at(D))
    t1 = t0 + (r1 - r0) / speed
    out['loop'] = {'segs': [('live', round(r0, 3), round(r1, 3), round(t0, 3), round(t1, 3))],
                   'zoom': [[0, 1.85, 1110, 240], [D, 1.85, 1110, 240]], 'hold_to': D}
    s['map'] = {'t_a': round(ta, 3), 'speed': round(speed, 3), 'run_a': 207.0}
    s = sc['deliver']; C, D = s['C'], s['dur']
    a1, a2 = C[0] + 3.0, C[0] + 5.4
    out['deliver'] = {'segs': [('review', 0.5, 7.0, 0.0, a1), ('review', 7.0, 12.2, a1, a2), ('review', 32.6, 38.1, a2, C[1]),
                               ('review', 46.1, 50.6, C[1], C[2]), ('review', 14.21, 18.7, C[2], D)],
                      'zoom': [[0, 1.0, 960, 540], [0.8, 1.25, 1150, 330], [a1 - 0.1, 1.25, 1150, 330], [a1 + 0.4, 1.1, 1150, 540],
                               [a2 - 0.1, 1.1, 1150, 540], [a2 + 0.4, 1.12, 1150, 520], [C[1] - 0.1, 1.12, 1150, 520],
                               [C[1] + 0.5, 1.45, 1400, 300], [C[2] - 0.1, 1.45, 1400, 300], [C[2] + 0.5, 1.35, 1150, 420]]}
    s['segs'] = [0.0, a1, a2, C[1], C[2]]
    for name, clip in out.items():
        clip['t0'] = clip['segs'][0][3]
        clip['zoom'] = [[round(t, 3), z, round(x * K, 1), round(y * K, 1)] for t, z, x, y in clip['zoom']]
        clip['w'], clip['h'] = FW, FH
    return out


def extract_footage(tl):
    for name, clip in tl['clips'].items():
        d = HERE / 'footage' / name
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        frames = []
        for i, (take, a, b, o0, o1) in enumerate(clip['segs']):
            n = max(1, round((o1 - o0) * FPS))
            speed = (b - a) / (o1 - o0)
            tmp = d / f'seg{i}'
            tmp.mkdir()
            run([FF, '-v', 'error', '-y', '-ss', f'{a}', '-t', f'{b - a + 0.5}', '-i', str(TAKES / take / 'raw.mp4'),
                 '-vf', f'setpts=(PTS-STARTPTS)/{speed},fps={FPS},scale={FW}:{FH}:flags=lanczos',
                 '-frames:v', str(n), '-q:v', '3', str(tmp / '%05d.jpg')])
            got = sorted(tmp.glob('*.jpg'))
            got += [got[-1]] * (n - len(got))
            frames += [f'footage/{name}/seg{i}/{p.name}' for p in got]
            print(name, i, f'speed {speed:.2f}', n, flush=True)
        if clip.get('hold_to'):
            extra = round((clip['hold_to'] - clip['segs'][-1][4]) * FPS)
            frames += [frames[-1]] * max(0, extra)
        clip['frames'] = frames
    (HERE / 'timeline.json').write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding='utf-8')


def prep_assets():
    from PIL import Image
    a = HERE / 'assets'
    im = Image.open(a / 'notice_raw.png')
    im.crop((930, 700, 2450, 955)).save(a / 'notice_crop.png')
    for src, dst in [(ROOT / 'cards' / 'assets' / f'report_p{n}.png', a / f'report_p{n}.png') for n in (1, 2, 52)]:
        shutil.copy(src, dst)
    shutil.copy(HERE / 'fig_answer_raw.png', a / 'hero.png')
    print('assets ready')


async def render_frames(tl, t_from=0.0, t_to=None, out_dir='frames'):
    from playwright.async_api import async_playwright
    out = HERE / out_dir
    out.mkdir(exist_ok=True)
    n0, n1 = int(t_from * FPS), int((t_to or tl['duration']) * FPS)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel='chrome', headless=True)
        pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        await pg.goto((HERE / 'stage3.html').as_uri())
        await pg.evaluate('document.fonts.ready')
        await pg.evaluate('tl => setup(tl)', tl)
        for i in range(n0, n1):
            await pg.evaluate('t => seek(t)', i / FPS)
            await pg.screenshot(path=str(out / f'{i:05d}.jpg'), type='jpeg', quality=93)
            if i % 600 == 0:
                print('frame', i, flush=True)
        await b.close()


if __name__ == '__main__':
    step = sys.argv[1] if len(sys.argv) > 1 else 'all'
    t_from = float(sys.argv[sys.argv.index('--from') + 1]) if '--from' in sys.argv else 0.0
    t_to = float(sys.argv[sys.argv.index('--to') + 1]) if '--to' in sys.argv else None
    tl = build_timeline() if step in ('timeline', 'all') else json.loads((HERE / 'timeline.json').read_text(encoding='utf-8'))
    if step in ('assets', 'all'):
        prep_assets()
    if step in ('footage', 'all'):
        extract_footage(tl)
    if step in ('frames', 'all'):
        asyncio.run(render_frames(tl, t_from, t_to))

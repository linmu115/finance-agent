"""Assemble the Finance Agent intro video: cards + real product footage + narration + music + subtitles."""
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile

FF = r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin\ffmpeg.exe'
FP = r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin\ffprobe.exe'
ROOT = Path(__file__).resolve().parent.parent
EDIT = ROOT / 'edit'
WORK = EDIT / 'work'
WORK.mkdir(parents=True, exist_ok=True)
CARDS = ROOT / 'cards'
TAKES = ROOT / 'rec' / 'takes'
TTS = ROOT / 'tts'
BG = '0xf6f7f6'
FPS = 30
ENC = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '15', '-pix_fmt', 'yuv420p', '-r', str(FPS)]
FONT = 'C\\:/Windows/Fonts/msyhbd.ttc'
LEAD = 0.6  # narration starts this long after a segment begins

# Live run: Enter at raw 5.90s, run started ~5.96s (audit log), answer streaming begins ~271s.
RUN_T0 = 5.96
LAPSE = (8.6, 270.0, 12.0)  # raw start, raw end, output seconds
LAPSE_SPEED = (LAPSE[1] - LAPSE[0]) / LAPSE[2]
SPOT = 'spot'  # dim everything but the report button (edit/spot_report.png), fading in after 0.9s
TRACE = 'overlay'  # composite cards/frames/trace (execution trace from the run's audit log)

# (take, start, end, speed, extra_filter)
PIECES = {
    'tour': [('tour', 0.9, 2.7, 1.0, None), ('tour', 2.7, 9.6, 1.2, None), ('tour', 9.6, 16.8, 1.5, None),
             ('tour', 16.8, 27.0, 1.7, None), ('tour', 27.0, 29.8, 1.0, None), ('tour', 29.8, 33.6, 1.0, None),
             ('tour', 33.6, 38.4, 2.6, None), ('tour', 38.4, 42.0, 1.5, None), ('tour', 42.0, 46.5, 1.4, None)],
    'live': [('live', 0.9, LAPSE[0], 1.0, None), ('live', LAPSE[0], LAPSE[1], LAPSE_SPEED, TRACE)],
    # holds are trimmed so each view sits under its narration sentence
    'review': [('review', 0.5, 7.0, 1.0, None), ('review', 7.0, 12.4, 1.0, None), ('review', 14.21, 18.73, 1.0, None),
               ('review', 20.80, 28.83, 1.0, None), ('review', 32.6, 38.1, 1.0, None), ('review', 38.5, 43.6, 1.0, None),
               ('review', 46.1, 50.1, 1.0, SPOT)],
}

# segment list: (name, kind, narration cues [(tts_id, offset_in_segment)])
TIMELINE = [
    ('title', 'card', [('title', LEAD)]),
    ('hook', 'card', [('hook', LEAD)]),
    ('errors', 'card', [('errors', LEAD)]),
    ('layers', 'card', [('layers', LEAD)]),
    ('tour', 'demo', [('d_tour', LEAD)]),
    ('live', 'demo', [('d_live_a', 0.4), ('d_live_b', 'piece1+0.35')]),
    ('review', 'demo', [('d_review_core', LEAD), ('d_report', 'piece6+0.4')]),
    ('report', 'card', []),
    ('method', 'card', [('method', LEAD)]),
    ('results', 'card', [('results', LEAD)]),
    ('ending', 'card', [('ending', LEAD)]),
]


def run(args):
    subprocess.run(args, check=True)


def duration(path):
    out = subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def build_piece(i, take, a, b, speed, extra, name):
    src = TAKES / take / 'raw.mp4'
    vf = [f'trim=start={a}:end={b}', 'setpts=PTS-STARTPTS']
    if speed != 1.0:
        vf.append(f'setpts=PTS/{speed}')
    if extra and extra not in (TRACE, SPOT):
        vf.append(extra)
    vf.append(f'fps={FPS}')
    out = WORK / f'{name}_{i:02d}.mp4'
    if extra == TRACE:
        seconds = (b - a) / speed
        run(['python', str(CARDS / 'render_trace.py'), str(a - RUN_T0), str(speed), str(seconds)])
        run([FF, '-v', 'error', '-y', '-i', str(src), '-framerate', str(FPS), '-i', str(CARDS / 'frames' / 'trace' / '%05d.png'),
             '-filter_complex', f"[0:v]{','.join(vf)}[v];[v][1:v]overlay=0:0:shortest=1[o]", '-map', '[o]', '-an', *ENC, str(out)])
    elif extra == SPOT:
        run([FF, '-v', 'error', '-y', '-i', str(src), '-loop', '1', '-i', str(EDIT / 'spot_report.png'),
             '-filter_complex', f"[0:v]{','.join(vf)}[v];[1:v]format=rgba,fade=t=in:st=0.9:d=0.4:alpha=1[s];"
             "[v][s]overlay=0:0:shortest=1[o]", '-map', '[o]', '-an', *ENC, str(out)])
    else:
        run([FF, '-v', 'error', '-y', '-i', str(src), '-vf', ','.join(vf), '-an', *ENC, str(out)])
    return out


def fade(path, out, fin=0.35, fout=0.35):
    d = duration(path)
    vf = f'fade=t=in:st=0:d={fin}:color={BG},fade=t=out:st={d - fout:.3f}:d={fout}:color={BG}'
    run([FF, '-v', 'error', '-y', '-i', str(path), '-vf', vf, '-an', *ENC, str(out)])
    return out


def build_demo(name):
    parts = [build_piece(i, *p, name=name) for i, p in enumerate(PIECES[name])]
    lst = WORK / f'{name}_list.txt'
    lst.write_text('\n'.join(f"file '{p.as_posix()}'" for p in parts), encoding='utf-8')
    joined = WORK / f'{name}_joined.mp4'
    run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy', str(joined)])
    starts, t = [], 0.0
    for p in parts:
        starts.append(t)
        t += duration(p)
    return fade(joined, WORK / f'{name}.mp4'), starts


def build_card(name):
    return fade(CARDS / f'{name}.mp4', WORK / f'card_{name}.mp4', fin=0.3, fout=0.01), [0.0]


def music(total, out):
    """A quiet, slow pad (Cmaj9 - Am9 - Fmaj9 - G6) synthesized here, so no licensing questions."""
    sr = 44100
    chords = [[130.81, 196.0, 246.94, 293.66], [110.0, 164.81, 196.0, 246.94],
              [87.31, 130.81, 164.81, 196.0], [98.0, 146.83, 196.0, 220.0]]
    seg = 8.0
    n = int(total * sr)
    t = np.arange(n) / sr
    sig = np.zeros(n)
    for k in range(int(np.ceil(total / seg)) + 1):
        c = chords[k % 4]
        s0 = int(k * seg * sr)
        length = int((seg + 3.0) * sr)
        s1 = min(n, s0 + length)
        if s0 >= n:
            break
        tt = t[s0:s1] - k * seg
        env = np.minimum(1, tt / 2.5) * np.minimum(1, np.maximum(0, (seg + 3.0 - tt) / 3.0))
        for f in c:
            for det in (0.999, 1.001):
                sig[s0:s1] += env * np.sin(2 * np.pi * f * det * tt) * (0.5 if f > 150 else 0.8)
    sig *= 0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t)  # slow swell
    sig /= np.max(np.abs(sig)) + 1e-9
    fade_n = int(3 * sr)
    sig[:fade_n] *= np.linspace(0, 1, fade_n)
    sig[-fade_n:] *= np.linspace(1, 0, fade_n)
    wavfile.write(out, sr, (sig * 0.9 * 32767).astype(np.int16))
    return out


def ass_time(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def split_lines(text, limit=24):
    lines = []
    for clause in [c for c in re.split(r'(?<=[。；：？！])', text) if c]:
        cur = ''
        for part in [p for p in re.split(r'(?<=[，、])', clause) if p]:
            if cur and len(cur) + len(part) > limit:
                lines.append(cur)
                cur = part
            else:
                cur += part
        if cur:
            lines.append(cur)
    return [l.rstrip('，。；：、') for l in lines]


def subtitles(cues, out):
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Microsoft YaHei,42,&H00FFFFFF,&H00FFFFFF,&H5A2E2A1F,&H5A2E2A1F,0,0,0,0,100,100,1,0,3,14,0,2,80,80,56,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for tts_id, start in cues:
        sents = json.loads((TTS / f'{tts_id}.subs.json').read_text(encoding='utf-8'))
        for s in sents:
            lines = split_lines(s['text'])
            total_chars = sum(len(l) for l in lines) or 1
            t = start + s['t']
            for l in lines:
                d = s['d'] * len(l) / total_chars
                events.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d - 0.04)},Sub,,0,0,0,,{l}")
                t += d
    Path(out).write_text(head + '\n'.join(events) + '\n', encoding='utf-8')
    return out


def main():
    segments, cues, t = [], [], 0.0
    for name, kind, narr in TIMELINE:
        clip, starts = build_demo(name) if kind == 'demo' else build_card(name)
        d = duration(clip)
        for tts_id, off in narr:
            if isinstance(off, str):
                idx, plus = off.replace('piece', '').split('+')
                off = starts[int(idx)] + float(plus)
            cues.append((tts_id, t + off))
        segments.append(clip)
        print(f'{name:8s} start {t:7.2f}  dur {d:6.2f}', flush=True)
        t += d
    total = t
    lst = WORK / 'all_list.txt'
    lst.write_text('\n'.join(f"file '{p.as_posix()}'" for p in segments), encoding='utf-8')
    video = WORK / 'video.mp4'
    run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy', str(video)])

    # narration track
    inputs, filters = [], []
    for i, (tts_id, start) in enumerate(cues):
        inputs += ['-i', str(TTS / f'{tts_id}.mp3')]
        ms = int(start * 1000)
        filters.append(f'[{i}:a]aresample=48000,adelay={ms}|{ms}[n{i}]')
    mix = ''.join(f'[n{i}]' for i in range(len(cues)))
    narr = WORK / 'narration.wav'
    run([FF, '-v', 'error', '-y', *inputs, '-filter_complex',
         ';'.join(filters) + f';{mix}amix=inputs={len(cues)}:normalize=0,apad=whole_dur={total:.3f}[a]',
         '-map', '[a]', '-ac', '2', '-ar', '48000', str(narr)])
    pad = music(total, str(WORK / 'music.wav'))
    audio = WORK / 'audio.m4a'
    run([FF, '-v', 'error', '-y', '-i', str(narr), '-i', pad, '-filter_complex',
         '[1:a]aresample=48000,volume=0.07,lowpass=f=2400[m];'
         '[m][0:a]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400[md];'
         '[0:a][md]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]',
         '-map', '[a]', '-ar', '48000', '-c:a', 'aac', '-b:a', '192k', '-t', f'{total:.3f}', str(audio)])

    ass = subtitles(cues, WORK / 'subs.ass')
    final = EDIT / 'FinanceAgent-初赛介绍视频.mp4'
    ass_arg = str(ass).replace('\\', '/').replace(':', '\\:')
    run([FF, '-v', 'error', '-y', '-i', str(video), '-i', str(audio),
         '-vf', f"ass='{ass_arg}':fontsdir='C\\:/Windows/Fonts'",
         '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
         '-c:a', 'copy', '-movflags', '+faststart', str(final)])
    print('total', round(total, 2), 'final', final, round(final.stat().st_size / 1e6, 1), 'MB')
    (EDIT / 'cues.json').write_text(json.dumps(cues, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()

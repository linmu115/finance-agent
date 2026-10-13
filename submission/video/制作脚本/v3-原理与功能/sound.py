"""Minimal score + sound design for the explainer: felt-piano arpeggios, a sub pad, and quiet functional cues.

usage: python sound.py <video.mp4> <out.mp4>
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

HERE = Path(__file__).resolve().parent
FF = r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin\ffmpeg.exe'
SR = 48000
rng = np.random.default_rng(11)


def lp(x, f, order=2):
    b, a = butter(order, f / (SR / 2), 'low')
    return lfilter(b, a, x)


def hp(x, f, order=2):
    b, a = butter(order, f / (SR / 2), 'high')
    return lfilter(b, a, x)


def hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def piano(m, dur=2.2, vel=1.0):
    """A soft 'felt piano' note: a few decaying partials, hammer softened by a low-pass."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    partials = [(1, 1.0, 1.0), (2, 0.42, 0.7), (3, 0.18, 0.5), (4, 0.08, 0.4)]
    x = sum(a * np.sin(2 * np.pi * f * k * t * (1 + 0.0004 * k)) * np.exp(-t * (1.6 + 1.2 * k) / d)
            for k, a, d in partials)
    x *= 1 - np.exp(-t / 0.006)
    return lp(x, 2600) * vel


def put(buf, sig, t0, g=1.0):
    i = int(t0 * SR)
    if i < 0 or i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * g


def score(total):
    n = int(total * SR)
    mus = np.zeros(n)
    beat = 60 / 76
    prog = [[57, 60, 64, 67], [53, 57, 60, 64], [48, 55, 60, 64], [55, 59, 62, 67]]   # Am7 Fmaj7 C G
    pattern = [0, 2, 1, 3, 2, 1]                                                         # gentle eighth-note arpeggio
    bars = int(total / (4 * beat)) + 1
    for b in range(bars):
        ch = prog[b % 4]
        t0 = b * 4 * beat
        put(mus, piano(ch[0] - 24, 4.2, 0.55), t0)                 # low root
        for i in range(8):
            if i < len(pattern) or i % 2 == 0:
                note = ch[pattern[i % len(pattern)]] + (12 if i in (3, 6) else 0)
                put(mus, piano(note, 1.8, 0.32 if i % 2 else 0.4), t0 + i * beat / 2)
        # sub pad
        pn = int(4 * beat * SR)
        tp = np.arange(pn) / SR
        pad = np.sin(2 * np.pi * hz(ch[0] - 12) * tp) * np.minimum(1, tp / 0.8) * np.minimum(1, (4 * beat - tp) / 0.8)
        put(mus, pad, t0, 0.12)
    fade = np.ones(n)
    fl = int(2.2 * SR)
    fade[:int(1.0 * SR)] = np.linspace(0, 1, int(1.0 * SR))
    fade[-fl:] = np.linspace(1, 0, fl)
    return mus * fade


def swish(dur=0.5, lo=600, hi=4000):
    m = int(dur * SR)
    x = rng.standard_normal(m)
    out = np.zeros(m)
    for i0 in range(0, m, 1200):
        f = lo + (hi - lo) * np.sin(np.pi * i0 / m)
        out[i0:i0 + 1200] = lp(x[i0:i0 + 1200], f)[: len(x[i0:i0 + 1200])]
    return out * np.hanning(m)


def tick(f=2200, dur=0.06):
    m = int(dur * SR)
    t = np.arange(m) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t / 0.012)


def thud():
    m = int(0.3 * SR)
    t = np.arange(m) / SR
    return np.sin(2 * np.pi * (180 - 100 * t / 0.3) * t) * np.exp(-t / 0.06)


def chime():
    a = piano(84, 2.0, 0.7)
    b = np.pad(piano(88, 1.8, 0.6), (int(0.12 * SR), 0))
    b = np.pad(b, (0, max(0, len(a) - len(b))))[: len(a)]
    return a + b


def sweep(dur):
    m = int(dur * SR)
    t = np.arange(m) / SR
    f = 500 + 900 * t / dur
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(m) * 0.5


def main(video, out):
    meta = json.loads((HERE / 'sample_marks.json').read_text(encoding='utf-8'))
    narr = {m['key']: m for m in json.loads((HERE / 'tts' / 'sample.json').read_text(encoding='utf-8'))}
    total = meta['end']
    n = int(total * SR)
    voice = np.zeros(n)
    for k, t0 in meta['starts'].items():
        sr, w = wavfile.read(HERE / 'tts' / f'{k}.wav')
        w = w.astype(np.float64)
        if np.max(np.abs(w)) > 2:
            w /= 32768.0
        x = np.interp(np.arange(int(len(w) * SR / sr)) * sr / SR, np.arange(len(w)), w)
        put(voice, x, t0)
    fx = np.zeros(n)
    marks = dict(meta['marks'])
    for i in range(4):
        put(fx, swish(0.45, 800, 3500), marks['flow'] + i * 0.47, 0.25)
    put(fx, sweep(2.0), marks['scan1'], 0.12)
    for i in range(4):
        put(fx, thud() if i == 1 else tick(), marks['ticks'] + i * 0.25, 0.5 if i == 1 else 0.3)
    put(fx, swish(0.7, 400, 2500), marks['back'], 0.3)
    put(fx, tick(1400, 0.1), marks['swap'] + 0.1, 0.25)
    put(fx, tick(1700, 0.1), marks['swap'] + 0.55, 0.25)
    put(fx, sweep(0.8), marks['swap'] + 1.0, 0.1)
    put(fx, chime(), marks['ship'], 0.22)
    mus = score(total)
    env = np.convolve(np.abs(voice), np.ones(int(0.3 * SR)) / int(0.3 * SR), mode='same')
    duck = 1 - 0.45 * np.clip(env / (np.percentile(env[env > 0], 90) + 1e-9), 0, 1)
    mix = voice + mus / (np.max(np.abs(mus)) + 1e-9) * 0.16 * duck + fx
    mix /= np.max(np.abs(mix)) + 1e-9
    wav = HERE / 'sample_mix.wav'
    wavfile.write(wav, SR, (mix * 0.95 * 32767).astype(np.int16))
    subprocess.run([FF, '-v', 'error', '-y', '-i', str(video), '-i', str(wav), '-map', '0:v', '-map', '1:a',
                    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000', '-ar', '48000',
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-movflags', '+faststart', str(out)], check=True)
    print(out)


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))

"""Voice + score + cue sounds for the v3 video, then mux with the rendered frames.

usage: python audio_v3.py [wav]    -> mix_v3.wav (and out_v3.mp4 from frames/ at 30 fps unless "wav")
"""
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from sound import FF, SR, chime, hp, lp, piano, put, rng, swish, sweep, thud, tick

HERE = Path(__file__).resolve().parent
TL = json.loads((HERE / 'timeline.json').read_text(encoding='utf-8'))
SC = {s['id']: s for s in TL['scenes']}
TOTAL = TL['duration']


def at(sid, lt):
    return SC[sid]['start'] + lt


def kick():
    m = int(0.35 * SR)
    t = np.arange(m) / SR
    return np.sin(2 * np.pi * (58 + 40 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.11)


def shaker():
    m = int(0.08 * SR)
    return hp(rng.standard_normal(m), 6000) * np.exp(-np.arange(m) / SR / 0.018)


def key_click():
    m = int(0.03 * SR)
    return lp(rng.standard_normal(m), 3500) * np.exp(-np.arange(m) / SR / 0.005)


def score():
    n = int(TOTAL * SR)
    mus = np.zeros(n)
    pulse = np.zeros(n)
    beat = 60 / 76
    prog = [[57, 60, 64, 67], [53, 57, 60, 64], [48, 55, 60, 64], [55, 59, 62, 67]]   # Am7 Fmaj7 C G
    pat_a = [0, 2, 1, 3, 2, 1, 3, 2]
    pat_b = [0, 1, 2, 3, 2, 3, 1, 2]
    # the case walk-through (case .. deliver) gets a soft pulse; the opening and the end stay piano only
    p_on, p_off = SC['case']['start'], SC['eval']['start'] + SC['eval']['dur'] * 0.85
    end_t = SC['end']['start']
    bars = int(end_t / (4 * beat)) + 1
    for b in range(bars):
        ch = prog[b % 4]
        t0 = b * 4 * beat
        if t0 >= end_t:
            break
        put(mus, piano(ch[0] - 24, 4.2, 0.55), t0)
        pat = pat_a if (b // 8) % 2 == 0 else pat_b
        for i in range(8):
            note = ch[pat[i]] + (12 if i in (3, 6) else 0)
            put(mus, piano(note, 1.8, 0.32 if i % 2 else 0.4), t0 + i * beat / 2)
        pn = int(4 * beat * SR)
        tp = np.arange(pn) / SR
        pad = np.sin(2 * np.pi * (440 * 2 ** ((ch[0] - 12 - 69) / 12)) * tp) * np.minimum(1, tp / 0.8) * np.minimum(1, (4 * beat - tp) / 0.8)
        put(mus, pad, t0, 0.12)
        if p_on <= t0 < p_off:
            for i in range(4):
                put(pulse, kick(), t0 + i * beat, 0.5 if i % 2 == 0 else 0.3)
                put(pulse, shaker(), t0 + i * beat + beat / 2, 0.05)
    # closing chord: C major add9, rolled
    for k, m in enumerate([36, 48, 55, 60, 64, 67, 74]):
        put(mus, piano(m, 6.0, 0.5), end_t + 0.15 + k * 0.09)
    ramp = np.ones(n)
    a, b = int(p_on * SR), int(p_off * SR)
    ramp[:a] = 0
    ramp[a:a + int(3 * SR)] = np.linspace(0, 1, int(3 * SR))
    ramp[b - int(4 * SR):b] = np.linspace(1, 0, int(4 * SR))
    ramp[b:] = 0
    mus = mus / (np.max(np.abs(mus)) + 1e-9) + pulse * ramp * 0.5
    fade = np.ones(n)
    fade[:int(1.0 * SR)] = np.linspace(0, 1, int(1.0 * SR))
    fade[-int(4.0 * SR):] = np.linspace(1, 0, int(4.0 * SR))
    return mus * fade


def cues():
    fx = np.zeros(int(TOTAL * SR))
    for s in TL['scenes'][1:]:
        put(fx, swish(0.6, 500, 2600), s['start'] - 0.35, 0.10)
    C = SC['overview']['C']
    put(fx, sweep(1.6), at('overview', C[1]), 0.06)
    put(fx, tick(1900), at('overview', C[4] + 0.2), 0.18)
    s = SC['problem']; C, E = s['C'], s['E']
    t_end = C[1] + 0.1 + (E[1] - C[1]) * 0.85
    for k in range(26):
        put(fx, key_click(), at('problem', C[1] + 0.1 + (t_end - C[1] - 0.1) * k / 26), 0.10)
    put(fx, swish(0.35, 900, 3000), at('problem', C[2] + 0.6), 0.14)
    put(fx, thud(), at('problem', C[4] + 0.3), 0.30)
    s = SC['ingest']; C, E = s['C'], s['E']
    put(fx, swish(0.9, 600, 3200), at('ingest', C[2] + 1.0), 0.16)
    for i in range(4):
        put(fx, tick(2000 + 120 * i), at('ingest', C[2] + 2.0 + i * 0.45), 0.22)
    put(fx, tick(1500, 0.1), at('ingest', C[2] + 4.0), 0.2)
    put(fx, chime(), at('ingest', C[3] + (E[3] - C[3]) * 0.7), 0.10)
    put(fx, sweep(1.4), at('ingest', C[4] + 1.0), 0.06)
    s = SC['workpaper']; C, E = s['C'], s['E']
    for t in [C[2] + 0.1, C[2] + (E[2] - C[2]) * 0.55, C[3] + 0.1, C[3] + (E[3] - C[3]) * 0.5]:
        put(fx, tick(2100), at('workpaper', t + 0.2), 0.2)
    put(fx, thud(), at('workpaper', C[5] + 0.3), 0.25)
    s = SC['loop']; C = s['C']
    for i in range(3):
        put(fx, tick(1300, 0.1), at('loop', C[3] + 0.25 + i * 0.35), 0.22)
    put(fx, swish(0.5, 700, 3000), at('loop', C[4] - 0.25), 0.12)
    put(fx, tick(1300, 0.1), at('loop', C[4] + 0.35), 0.22)
    put(fx, swish(0.5, 700, 3000), at('loop', C[5] - 0.25), 0.12)
    put(fx, chime(), at('loop', C[5] + 0.3), 0.14)
    s = SC['check']; C, E = s['C'], s['E']
    put(fx, sweep(1.2), at('check', C[2]), 0.07)
    put(fx, tick(2100), at('check', C[3] + (E[3] - C[3]) * 0.6), 0.22)
    put(fx, thud(), at('check', C[4] + (E[4] - C[4]) * 0.25), 0.3)
    put(fx, tick(2100), at('check', C[4] + (E[4] - C[4]) * 0.75), 0.22)
    put(fx, swish(0.7, 400, 2500), at('check', C[5] + 0.2), 0.16)
    put(fx, tick(1400, 0.1), at('check', C[5] + 2.0), 0.2)
    put(fx, tick(1700, 0.1), at('check', C[5] + 2.5), 0.2)
    put(fx, chime(), at('check', C[5] + 3.1), 0.16)
    S = SC['deliver']['segs']
    put(fx, swish(0.8, 500, 2400), at('deliver', S[3] + 1.0), 0.14)
    s = SC['eval']; C, E = s['C'], s['E']
    put(fx, sweep(2.1), at('eval', C[0] + 0.5), 0.05)
    put(fx, tick(1800), at('eval', C[3]), 0.18)
    for t in [C[6] + (E[6] - C[6]) * 0.25, C[6] + (E[6] - C[6]) * 0.6, C[7] + 0.2]:
        put(fx, tick(1900), at('eval', t + 0.3), 0.2)
    return fx


def voice():
    v = np.zeros(int(TOTAL * SR))
    for c in TL['voice']:
        sr, w = wavfile.read(HERE / 'tts3' / c['file'])
        w = w.astype(np.float64)
        if np.max(np.abs(w)) > 2:
            w /= 32768.0
        put(v, resample_poly(w, SR, sr), c['t'])
    return v


def main(wav_only=False):
    v = voice()
    mus = score()
    fx = cues()
    env = np.convolve(np.abs(v), np.ones(int(0.3 * SR)) / int(0.3 * SR), mode='same')
    duck = 1 - 0.5 * np.clip(env / (np.percentile(env[env > 0], 90) + 1e-9), 0, 1)
    mix = v / (np.max(np.abs(v)) + 1e-9) + mus * 0.13 * duck + fx
    mix /= np.max(np.abs(mix)) + 1e-9
    wav = HERE / 'mix_v3.wav'
    wavfile.write(wav, SR, (mix * 0.95 * 32767).astype(np.int16))
    if wav_only:
        return print(wav)
    n = int(TOTAL * 30)
    out = HERE / 'out_v3.mp4'
    subprocess.run([FF, '-v', 'error', '-y', '-framerate', '30', '-i', str(HERE / 'frames' / '%05d.jpg'), '-i', str(wav),
                    '-frames:v', str(n), '-map', '0:v', '-map', '1:a',
                    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000', '-ar', '48000',
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', str(out)], check=True)
    print(out)


if __name__ == '__main__':
    import sys
    main('wav' in sys.argv[1:])

"""Synthesize every clause of narration_v3 with Kokoro (temporary voice): tts3/<scene>_<i>.wav + tts3/narration.json."""
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

from narration_v3 import ORDER, PAUSE, SCENES

HERE = Path(__file__).resolve().parent
OUT = HERE / 'tts3'
SR = 24000
OUT.mkdir(exist_ok=True)
pipe = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
meta = {}
for scene in ORDER:
    clauses = []
    for i, (show, say) in enumerate(SCENES[scene]):
        wav = np.concatenate([np.asarray(a, np.float32) for _, _, a in pipe(say, voice='zf_xiaoxiao', speed=1.0)])
        idx = np.where(np.abs(wav) > 0.012)[0]
        wav = wav[max(0, idx[0] - 600): idx[-1] + 600]
        f = OUT / f'{scene}_{i}.wav'
        sf.write(f, wav, SR)
        clauses.append({'show': show, 'file': f.name, 'dur': round(len(wav) / SR, 3), 'pause': PAUSE.get(show[-1], 0.1)})
        print(scene, i, round(len(wav) / SR, 2), flush=True)
    meta[scene] = clauses
(OUT / 'narration.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
total = sum(c['dur'] + c['pause'] for s in meta.values() for c in s)
print('speech+pauses', round(total, 1))

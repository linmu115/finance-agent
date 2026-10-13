"""Turn timestamped screencast frames into a constant-30fps H.264 clip."""
import json
import subprocess
import sys
from pathlib import Path

FFMPEG = r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin\ffmpeg.exe'


def build(take: Path, out: Path, tail=1.0):
    frames = json.loads((take / 'frames.json').read_text(encoding='utf-8'))
    lines = []
    for i, (t, name) in enumerate(frames):
        nxt = frames[i + 1][0] if i + 1 < len(frames) else t + tail
        lines.append(f"file 'frames/{name}'\nduration {max(nxt - t, 0.001):.4f}")
    lines.append(f"file 'frames/{frames[-1][1]}'")
    lst = take / 'concat.txt'
    lst.write_text('\n'.join(lines), encoding='utf-8')
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst.resolve()),
                    '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
                    str(out.resolve())], check=True, cwd=take)
    return out


if __name__ == '__main__':
    take = Path(sys.argv[1]).resolve()
    print(build(take, take / 'raw.mp4'))

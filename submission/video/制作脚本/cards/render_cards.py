"""Frame-stepped rendering of cards.html scenes (deterministic, 30fps)."""
import subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
FFMPEG=r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin\ffmpeg.exe'
HERE=Path(__file__).resolve().parent
def render(scene, seconds, out, fps=30, still=False):
    with sync_playwright() as p:
        b=p.chromium.launch(channel='chrome', headless=True)
        pg=b.new_page(viewport={'width':1920,'height':1080})
        pg.goto((HERE/'cards.html').as_uri()); pg.wait_for_timeout(300)
        pg.evaluate(f"show('{scene}')")
        if still:
            pg.evaluate(f"seek({seconds})"); pg.screenshot(path=str(out)); b.close(); return
        fdir=HERE/'frames'/scene; fdir.mkdir(parents=True, exist_ok=True)
        n=int(seconds*fps)
        for i in range(n):
            pg.evaluate(f"seek({i/fps}, {seconds})")
            pg.screenshot(path=str(fdir/f'{i:05d}.jpg'), type='jpeg', quality=95)
        b.close()
    subprocess.run([FFMPEG,'-v','error','-y','-framerate',str(fps),'-i',str(fdir/'%05d.jpg'),
                    '-c:v','libx264','-preset','slow','-crf','14','-pix_fmt','yuv420p',str(out)],check=True)
if __name__=='__main__':
    scene=sys.argv[1]; secs=float(sys.argv[2]); still=len(sys.argv)>3 and sys.argv[3]=='still'
    render(scene, secs, HERE/(f'{scene}.png' if still else f'{scene}.mp4'), still=still)

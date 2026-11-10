#!/usr/bin/env python3
"""Render the Haejo film: step film.html through time in headless Chromium.

Each frame calls renderAt(t) (a pure function of t), screenshots the 1920x1080
stage and streams it to ffmpeg. Plates come from shoot_native.py; browser
clips are the site's own recordings. Writes MP4 (H.264) + WebM (VP9) + poster.

  python render.py --plates DIR --out DIR [--lang ko|en] [--preview 2,9,16]
"""
import argparse, json, subprocess, sys
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FPS = 30


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plates', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--lang', choices=['ko', 'en'], default='ko')
    ap.add_argument('--url', default='', help='address shown on the end card')
    ap.add_argument('--preview', help='comma-separated seconds: write stills only')
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    runs = json.loads((a.plates/'runs.json').read_text())
    timing = next(json.loads(l.split(' ', 1)[1]) for l in runs['second']['output'] if l.startswith('HAEJO_TIMINGS '))
    provider = next(json.loads(l.split(' ', 1)[1]) for l in runs['repair']['output'] if l.startswith('HAEJO_AUTO_REPAIR_PROVIDER '))
    facts = {'replay_seconds': timing['replay_seconds'], 'repair_seconds': provider['elapsed_seconds']}
    query = urlencode({'lang': a.lang, 'plates': a.plates.resolve().as_uri(), 'assets': (HERE.parent/'dist/assets').as_uri(),
                       'runs': json.dumps(facts), 'url': a.url})
    name = f'haejo-film.{a.lang}'
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required', '--allow-file-access-from-files'])
        page = browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
        page.goto((HERE/'film.html').as_uri()+'?'+query); page.evaluate('window.ready')
        duration = page.evaluate('DURATION')
        def shot(t):
            page.evaluate(f'renderAt({t})'); return page.screenshot(type='png', clip={'x': 0, 'y': 0, 'width': 1920, 'height': 1080})
        if a.preview:
            for s in a.preview.split(','):
                (a.out/f'{name}-{float(s):05.1f}.png').write_bytes(shot(float(s)))
            browser.close(); return
        raw = a.out/f'{name}.raw.mkv'
        enc = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS),
                                '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12', '-pix_fmt', 'yuv420p', str(raw)],
                               stdin=subprocess.PIPE)
        for n in range(int(duration*FPS)):
            enc.stdin.write(shot(n/FPS))
            if n % 150 == 0: print(f'{a.lang} frame {n}', flush=True)
        enc.stdin.close(); assert enc.wait() == 0
        (a.out/f'{name}.poster.png').write_bytes(shot(18.2))
        browser.close()
    ff = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(raw)]
    subprocess.run(ff+['-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-tune', 'animation', '-pix_fmt', 'yuv420p',
                       '-movflags', '+faststart', '-an', str(a.out/f'{name}.mp4')], check=True)
    subprocess.run(ff+['-c:v', 'libvpx-vp9', '-crf', '38', '-b:v', '0', '-row-mt', '1', '-an', str(a.out/f'{name}.webm')], check=True)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(a.out/f'{name}.poster.png'),
                    '-q:v', '3', str(a.out/f'{name}.poster.jpg')], check=True)
    raw.unlink(); (a.out/f'{name}.poster.png').unlink()
    print(json.dumps({f.name: f.stat().st_size for f in sorted(a.out.glob(name+'.*'))}))


if __name__ == '__main__':
    sys.exit(main())

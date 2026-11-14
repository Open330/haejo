#!/usr/bin/env python3
"""Compose the landing's "direct control" clip from shoot_direct.py's plates.

Each frame is one Safari capture (taken after one call, Safari behind) with the
TextEdit note capture laid over its lower left corner, on the scene's
background. The arrangement is composed; the two windows are the captures,
scaled. Frames are held and cut, as in the film: no continuous screen video.
The labels on the page ("내가 쓰는 창", "뒤에서 입력 중") are HTML over the clip.

  .venv/bin/python sites/haejo/film/render_direct.py --plates DIR/plates --out DIR/clip
  cp DIR/clip/haejo-direct.* sites/haejo/dist/assets/direct/
"""
import argparse, json, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

W, H, FPS = 1000, 1010, 30
HOLD = {'open': 1.2, 'register': 2.4}  # seconds; every other step holds 1.0
POSTER = 'amount'
PAGE = '''<!doctype html><meta charset="utf-8"><style>
html,body{margin:0}
body{position:relative;width:%dpx;height:%dpx;overflow:hidden;background:linear-gradient(155deg,#edf1e4 0%%,#dde5d2 60%%,#f3d9c7 130%%)}
img{position:absolute;display:block}
#back{top:96px;right:30px;width:790px;filter:drop-shadow(0 10px 22px rgba(27,33,28,.28))}
#front{top:632px;left:30px;width:470px;filter:drop-shadow(0 22px 34px rgba(27,33,28,.45))}
</style><img id="back"><img id="front" src="%s">'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plates', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True); plates = a.plates.resolve()
    backs = sorted(p for p in plates.glob('[0-9][0-9]-*.png'))
    stage = out/'stage.html'; stage.write_text(PAGE % (W, H, (plates/'front.png').as_uri()))
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--allow-file-access-from-files'])
        page = browser.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        page.goto(stage.as_uri())
        page.eval_on_selector('#front', 'e => e.decode()')
        listing, total = [], 0.0
        for back in backs:
            step = back.stem.split('-', 1)[1]
            page.eval_on_selector('#back', '(e, src) => { e.src = src; return e.decode(); }', back.as_uri())
            still = out/f'{back.stem}.still.png'; page.screenshot(path=str(still))
            hold = HOLD.get(step, 1.0); total += hold
            listing += [f"file '{still}'", f'duration {hold}']
        browser.close()
    listing.append(listing[-2])  # the concat demuxer reads the last duration from a repeated entry
    (out/'stills.txt').write_text('\n'.join(listing)+'\n')
    ff = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(out/'stills.txt'),
          '-vf', f'fps={FPS},format=yuv420p', '-t', f'{total:.2f}', '-an']
    name = out/'haejo-direct'
    subprocess.run(ff+['-c:v', 'libx264', '-preset', 'slow', '-crf', '22', '-tune', 'animation', '-movflags', '+faststart', f'{name}.mp4'], check=True)
    subprocess.run(ff+['-c:v', 'libvpx-vp9', '-crf', '36', '-b:v', '0', '-row-mt', '1', f'{name}.webm'], check=True)
    poster = next(out.glob(f'*-{POSTER}.still.png'))
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(poster), '-q:v', '3', f'{name}.poster.jpg'], check=True)
    for f in [*out.glob('*.still.png'), stage, out/'stills.txt']: f.unlink()
    print(json.dumps({'seconds': round(total, 1), 'width': W, 'height': H, **{f.name: f.stat().st_size for f in sorted(out.glob('haejo-direct.*'))}}))


if __name__ == '__main__':
    main()

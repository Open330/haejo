#!/usr/bin/env python3
"""Compose the "two tasks, one Calculator" clip from shoot_turns.py's plates.

Each frame is one Calculator capture (taken after one call, Calculator behind
the app in use) between two cards that say what each task has done so far, and
a caption. The window is the capture; the cards, caption and arrangement are
composed from evidence.json. Frames are held and cut: no continuous screen video.

  .venv/bin/python sites/haejo/film/render_turns.py --shoot DIR --out CLIP
  cp CLIP/agents-take-turns.* docs/assets/demos/
"""
import argparse, html, json, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

W, H, FPS = 1280, 720, 30
HOLD = {'start': 2.2, 'b-told': 3.4, 'a-equals': 1.8, 'b-3': 2.6, 'b-equals': 2.0, 'end': 2.8}  # seconds; every other frame holds 1.1
POSTER = 'b-told'
CAPTION = {
    'start': 'Two agents on one Mac, each with its own task. Calculator stays behind the app in use.',
    'a-7': 'Task A presses its keys.', 'a-plus': 'Task A presses its keys.',
    'b-told': 'Task B asks for the same Calculator. Haejo answers that task A is using it; nothing is pressed.',
    'a-8': 'Task A goes on with its sum.', 'a-equals': 'Task A goes on with its sum.',
    'b-3': 'Task A ends. Task B asks again and gets through.',
    'b-times': 'Task B presses its keys.', 'b-9': 'Task B presses its keys.', 'b-equals': 'Task B presses its keys.',
    'end': 'Both tasks done. The app in front never changed.',
}
PAGE = '''<!doctype html><meta charset="utf-8"><style>
html,body{margin:0}
body{position:relative;width:%dpx;height:%dpx;overflow:hidden;background:linear-gradient(155deg,#edf1e4 0%%,#dde5d2 60%%,#f3d9c7 130%%);
  font-family:-apple-system,"Helvetica Neue",sans-serif;color:#1b211c}
#calc{position:absolute;top:40px;left:50%%;height:548px;transform:translateX(-50%%);filter:drop-shadow(0 16px 30px rgba(27,33,28,.35))}
.card{position:absolute;top:150px;width:330px;box-sizing:border-box;padding:22px 24px;border-radius:18px;background:#fbfaf5;
  border:2px solid transparent;box-shadow:0 8px 22px rgba(27,33,28,.14);opacity:.62}
.card.on{opacity:1;border-color:#e8592b}
#a{left:56px}#b{right:56px}
.who{font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:#5d665d}
.goal{margin-top:6px;font-size:30px;font-weight:700}
.state{margin-top:18px;font-size:21px;line-height:1.35;min-height:58px}
#cap{position:absolute;left:0;right:0;bottom:0;height:104px;box-sizing:border-box;padding:0 90px;display:flex;align-items:center;justify-content:center;
  text-align:center;font-size:24px;line-height:1.35;background:#1b211c;color:#fbfaf5}
</style><img id="calc">
<div class="card" id="a"><div class="who">Task A · agent 1</div><div class="goal">7 + 8</div><div class="state"></div></div>
<div class="card" id="b"><div class="who">Task B · agent 2</div><div class="goal">3 × 9</div><div class="state"></div></div>
<div id="cap"></div>'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--shoot', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True); shoot = a.shoot.resolve()
    frames = json.loads((shoot/'evidence.json').read_text())['frames']
    stage = out/'stage.html'; stage.write_text(PAGE % (W, H))
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--allow-file-access-from-files'])
        page = browser.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        page.goto(stage.as_uri())
        listing, total = [], 0.0
        for n, f in enumerate(frames):
            plate = shoot/'plates'/f"{n:02d}-{f['frame']}.png"
            page.evaluate('''([src, a, b, on, cap]) => { const set = (id, text, lit) => { const e = document.getElementById(id);
                e.querySelector('.state').innerHTML = text; e.classList.toggle('on', lit); };
                set('a', a, on === 'A'); set('b', b, on === 'B'); document.getElementById('cap').innerHTML = cap;
                const i = document.getElementById('calc'); i.src = src; return i.decode(); }''',
                          [plate.as_uri(), html.escape(f['a']), html.escape(f['b']), f['task'], html.escape(CAPTION[f['frame']])])
            still = out/f"{n:02d}-{f['frame']}.still.png"; page.screenshot(path=str(still))
            hold = HOLD.get(f['frame'], 1.1); total += hold
            listing += [f"file '{still}'", f'duration {hold}']
        browser.close()
    listing.append(listing[-2])  # the concat demuxer reads the last duration from a repeated entry
    (out/'stills.txt').write_text('\n'.join(listing)+'\n')
    name = out/'agents-take-turns'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(out/'stills.txt'),
                    '-vf', f'fps={FPS},format=yuv420p', '-t', f'{total:.2f}', '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '22',
                    '-tune', 'animation', '-movflags', '+faststart', f'{name}.mp4'], check=True)
    next(out.glob(f'*-{POSTER}.still.png')).rename(f'{name}-poster.png')
    for f in [*out.glob('*.still.png'), stage, out/'stills.txt']: f.unlink()
    print(json.dumps({'seconds': round(total, 1), 'width': W, 'height': H, **{f.name: f.stat().st_size for f in sorted(out.glob('agents-take-turns*'))}}))


if __name__ == '__main__':
    main()

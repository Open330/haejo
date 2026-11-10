# Haejo film and landing re-shoot — 2026-11-10

The landing hero and the README now open with a 37-second film
(`sites/haejo/dist/assets/film/haejo-film.{ko,en}.{mp4,webm}` + poster).
Every landing recording that still showed the Tacto name was re-shot with the
installed Haejo v1.0.0-rc.39.

## What the film shows

| Time | Scene | Source |
|---|---|---|
| 0–2.4 s | Title | Drawn |
| 2.4–8 s | "Ask once": a prompt, then Calculator goes 0 → 7 → 7+ → 7+8 → 15 | Terminal drawn; Calculator frames are real window captures |
| 8–13.6 s | The six Flow steps saved as `calculator-reusable` | Drawn from `film/calculator.flow.json` |
| 13.6–20 s | `haejo run … -p left=3 -p right=9`, result 12, **0 model calls**, replay 1.39 s | Real command output and timing (`HAEJO_TIMINGS.replay_seconds`); real captures |
| 20–24.6 s | The saved Add step names an old `Plus` button; `--auto-repair claude` fixes only that step | Real run: `target_missing`, one Claude call (3.6 s), resume, result 12 |
| 24.6–29.4 s | GitHub, Wikipedia, Google Translate, Markdown | The site's own Haejo browser recordings (re-shot today) |
| 29.4–33.4 s | Haejo activity window | `HaejoSetup --activity-snapshot` over the receipts of the film's own runs |
| 33.4–37 s | End card | Drawn |

The authoring conversation in the "Ask once" scene is illustrative: it is not
a recording of a model writing the Flow. Calculator pixels are real captures
taken after each step of the saved Flow; the film's timing and camera moves
are edited. The repair scene's terminal lines paraphrase the real run's
output (`runs.json`), including its provider time.

## Re-shot landing recordings

| Clip | How | Result |
|---|---|---|
| 7 browser examples | `record_browser_demos.py`, `record_everyday_browser_demos.py` (unchanged tools; pointer badge now reads HAEJO) | All 7 replays and result checks passed |
| TextEdit | `film/shoot_everyday.py`: owned note in a new folder; `film/textedit.flow.json`, then built-in `textedit_save` | Edit step `commit_unverified` (postcondition observed); save step verified the disk contents |
| Finder | `film/shoot_everyday.py`: owned folder of five synthetic files; `film/finder.flow.json` sorts by Kind, then Name | Passed; sidebar and path bar cropped |
| Workflow test app | `film/shoot_workflow.py`: fixture titled "Haejo Workflow Demo"; the 11-step Flow replayed one step at a time for five input sets | 37, 46, 70, 27, 48; one completion per job in the fixture record |
| Activity screenshot | `HaejoSetup --activity-snapshot` over 67 run/replay receipts from today's shoot | Calculator, TextEdit and Finder runs, including failed attempts |

Native clips are built from captures taken after each step (the helper takes
about 2.3 s per capture), held for their real or fixed intervals. They are
not continuous screen video. Pointers remain explanatory overlays.

## Regenerate

From the repository root, with the installed Haejo and its grants:

```sh
S=$(mktemp -d)
python3 sites/haejo/film/shoot_native.py --out "$S/plates"
/Applications/Haejo.app/Contents/MacOS/HaejoSetup --activity-snapshot "$S/act" --activity-fixture "$S/plates/activity"
cp "$S/act/app.png" "$S/plates/activity.png"
.venv/bin/python sites/haejo/film/render.py --plates "$S/plates" --out "$S/film" --lang ko
.venv/bin/python sites/haejo/film/render.py --plates "$S/plates" --out "$S/film" --lang en
cp "$S"/film/haejo-film.* sites/haejo/dist/assets/film/
```

`render.py --preview 2,9,18` writes stills only, for a quick look before the
full encode (about 4 minutes per language). Landing clips:

```sh
python3 sites/haejo/film/shoot_everyday.py --out "$S/everyday"
(cd sites/haejo && ../../.venv/bin/python render_native_examples.py --recordings "$S/everyday")
.venv/bin/python sites/haejo/film/shoot_workflow.py --out "$S/workflow"
(cd sites/haejo && ../../.venv/bin/python annotate_recordings.py)
```

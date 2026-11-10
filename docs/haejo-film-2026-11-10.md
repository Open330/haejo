# Haejo film and landing re-shoot — 2026-11-10

The landing hero and the README now open with a 40-second film
(`sites/haejo/dist/assets/film/haejo-film.{ko,en}.{mp4,webm}` + poster).
Every landing recording that still showed the Tacto name was re-shot with the
installed Haejo v1.0.0-rc.39.

## What the film shows

One real weekly task, in the order a person meets Haejo:

| Time | Scene | Source |
|---|---|---|
| 0–2.6 s | Title | Drawn |
| 2.6–13.4 s | **Just ask.** "Find the 5 most-discussed open bugs in vscode and put them in a meeting note." Safari opens the filtered GitHub list, the top 5 are read, a TextEdit note is written and saved | The Haejo calls an agent makes (`open-url`, `run read-top5`, `run memo`, `activate`, `replay textedit_save`), one task with a goal and a reason per call; real window captures after each call |
| 13.4–18.8 s | **Every call, on the record.** | `HaejoSetup --activity-snapshot` over that task's receipts: goal, request, reasons, 5 calls (the note edit is listed as a failure: TextEdit edits end `commit_unverified`; the following save verified the file) |
| 18.8–24.6 s | **Saved as Flows.** Safari lane (reload, read top 5) and TextEdit lane (write note, save) | Drawn from `film/weekly-bugs.json` and `film/weekly-memo.json`, saved with `haejo flows save` |
| 24.6–32.4 s | **Next week: replay.** `haejo replay weekly-bugs`, `weekly-memo -p date=…`, `textedit_save`; a new note for 11/17 | Real replay: 0 model calls, 2.1 s of replay (`HAEJO_TIMINGS.replay_seconds`), save verified; real captures |
| 32.4–36 s | Finder, Wikipedia, Markdown | The site's own Haejo recordings |
| 36–40 s | End card with the brand lockup (`haejo-wordmark.svg`) | Drawn |

The prompt and the agent's narration lines are composed for the film; the
calls under them are the ones that ran. The "next week" note was produced the
same day, so it lists the same bugs. Safari's tab bar is cropped. Only public
GitHub pages were read, signed out; both notes are new files.

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
sites/haejo/film/shoot_weekly.sh "$S"
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

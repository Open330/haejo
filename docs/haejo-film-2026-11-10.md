# Haejo film and landing re-shoot — 2026-11-10

The landing hero and the README now open with a 40-second film
(`sites/haejo/dist/assets/film/haejo-film.{ko,en}.{mp4,webm}` + poster).
Every landing recording that still showed the Tacto name was re-shot with the
installed Haejo v1.0.0-rc.39.

## What the film shows

Tedious work with no API: eight card receipts typed into a company expense
system, field by field. The expense system is a local demo page
(`film/demo-expense/`, marked **DEMO** on screen); the card rows in
`film/data/` are made up. Everything else is real.

| Time | Scene | Source |
|---|---|---|
| 0–3 s | Title: "법인카드 영수증 8건 입력, \"해줘\"" | Drawn |
| 3–14.2 s | **8건, "해줘"**: the request; Haejo reads November's statement in TextEdit, then fills the form (the first entry field by field, the other seven one Flow run each) until 8 rows total ₩215,300 | The calls an agent makes (`observe --document`, `activate`, `run` with `--task`/`--why`); real window captures after each call |
| 14.2–19.4 s | **뭘 했는지 보여줘**: four tasks of the day (weekly issue review, kickoff notes, workshop folder, November expenses) and the expense task's 16 calls with reasons | `HaejoSetup --activity-snapshot` over those tasks' receipts |
| 19.4–25 s | **그대로 저장해줘**: the seven-step `expense-entry` Flow with its parameters | Drawn from `film/expense-entry.json`, saved with `haejo flows save` |
| 25–33.2 s | **다음 달에도 "해줘"**: six `haejo replay expense-entry -p …` runs fill December | Real replays: 0 model calls, 22.4 s of replay in total (`HAEJO_TIMINGS.replay_seconds` per row) |
| 33.2–36.6 s | Finder, TextEdit, Wikipedia | The site's own Haejo recordings |
| 36–40 s | End card: brand lockup, "Mac에서 귀찮은 일, \"해줘\"" | Drawn |

The request and the narration lines are composed for the film; the calls under
them are the ones that ran. `haejo batch` was not used for December: the
web form needs the paste input route (Safari ignores AX value edits on these
fields), which batch does not accept, so each row is its own replay. The
groupware page's Register button is named 등록; a button named 저장 is
classified as a persistent write, while the demo only keeps rows in the page.

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
python3 sites/haejo/film/shoot_expense.py --out "$S/expense" --folder /path/to/an/owned/folder
.venv/bin/python sites/haejo/film/render.py --plates "$S/expense/plates" --out "$S/film" --lang ko
.venv/bin/python sites/haejo/film/render.py --plates "$S/expense/plates" --out "$S/film" --lang en
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

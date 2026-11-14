# Landing "direct control" clip — 2026-11-15

The "바로 조작" section of the landing now shows a 9.6-second looping clip
(`sites/haejo/dist/assets/direct/haejo-direct.{mp4,webm}` + poster, 1000×1010,
about 0.15 MB each) in place of the drawn illustration. Shot with the installed
Haejo 1.0.3 on Safari 27.2, macOS 27.2.1.

## What the clip shows

One card expense typed into the demo expense page, field by field, in a Safari
window that stays behind the app in use.

| Part | Source |
|---|---|
| Safari window | Real captures of the Safari window by the signed helper, one after each call, while another app was in front |
| Expense system | The local demo page `film/demo-expense/` (marked **DEMO** on screen); the row is the third of `film/data/2026-11.json`, made up |
| Front window | A capture of a TextEdit note that `shoot_direct.py` writes in a new folder (a made-up quarterly summary), opened with `open -g` |
| Arrangement, background | Composed by `render_direct.py`: the note laid over the lower left corner of the Safari capture |
| "내가 쓰는 창", "뒤에서 입력 중", "Safari에서 작업 중" | HTML labels over the clip, so one clip serves both languages |

Frames are held and cut, as in the film: captures after each step, composed.
It is a sequence of stills, the same statement the film doc makes.

## The calls and what was recorded

Eight calls: `haejo open-url` (the page opens behind), six one-step
`haejo run … --window-match url=127.0.0.1` calls (four `set_value` text fields,
one radio `click`, two more `set_value`), and the 등록 `click`.

`sites/haejo/film/direct-evidence.json` is the summary of the shoot that made
the published clip. For every call it holds the app in front before and after,
the exit code and the `HAEJO_ROUTE` lines; it holds no screen contents, and an
app outside `com.apple.*` appears as `other-app-1`.

| Step | Call | Route reported | App in front, before → after |
|---|---|---|---|
| open | `open-url` | — | other-app-1 → other-app-1 |
| date, merchant, amount, project, memo | `set_value` | `ax_value_focused`, L1 | other-app-1 → other-app-1 |
| category | `click` (radio) | accessibility press, no route line | other-app-1 → other-app-1 |
| register | `click` (등록) | accessibility press, no route line | other-app-1 → other-app-1 |

Safari was behind for the whole shoot, and the app in front at the end was the
one in front at the start. The script ends the shoot when a call would change
that or reports an L3 route.

Measured while shooting:

- With Safari closed beforehand, the first `open-url` started Safari and Safari
  showed its own "reopen windows" alert in front (its previous session had ended
  abnormally). The script therefore works in a Safari that is already running.
- While the person is on another Space, Safari's window list is unavailable and
  a call answers `window_list_unavailable` with `effect: not_started`. Nothing
  reached the page, so the script makes the same call again.
- Opening the page before TextEdit starts gave a confirmed load each time; the
  other order left `open-url` at `page_not_shown`.
- Safari's File > Close Tab is disabled while Safari is behind, so cleanup
  closes the demo tab by its address with an Apple event, closes the note with
  TextEdit's File > Close, and quits TextEdit when the shoot started it.

## Regenerate

From the repository root, with the installed Haejo, its grants, and Safari
already running behind another app:

```sh
S=$(mktemp -d)
python3 sites/haejo/film/shoot_direct.py --out "$S/direct"
.venv/bin/python sites/haejo/film/render_direct.py --plates "$S/direct/plates" --out "$S/clip"
cp "$S"/clip/haejo-direct.* sites/haejo/dist/assets/direct/
cp "$S/direct/evidence.json" sites/haejo/film/direct-evidence.json
```

The shoot takes about a minute and a half. `sites/haejo/qa.py` checks the clip's
markup, that it decodes, its pause button and the still poster under
`prefers-reduced-motion`.

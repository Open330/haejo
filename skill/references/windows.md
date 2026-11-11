# Several windows of one app

`haejo windows <bundle-id> --helper` lists windows
with `url` for browser pages, plus `unlisted` (`not_on_active_space`,
`enumeration_partial`) and a `reason` such as `screen_locked` when the list is
empty. `session <bundle-id> --window-match url=<text> --helper --guide`
(also `title=<text>`, `newest`) picks the window by page and `--save` stores
that selector as the Flow's `"window"`, so `run`/`batch` find the new popup
each time; `--window-id <current ID>` pins one live window for this run only.
App-wide menus, keys and pointer work use an ordinary session.
To run 2-4 windows at once, put one inline Flow per `window_id` in a manifest and
call `haejo parallel jobs.json --helper --json` (`haejo parallel --help`).

# Several windows of one app

`haejo windows <bundle-id> --helper` lists windows
with `url` for browser pages, plus `unlisted` (`not_on_active_space`,
`enumeration_partial`) and a `reason` such as `screen_locked` when the list is
empty. `session <bundle-id> --window-match url=<text> --helper --guide`
(also `title=<text>`, `newest`) picks the window by page and `--save` stores
that selector as the Flow's `"window"`, so `run`/`batch` find the new popup
each time; `--window-id <current ID>` pins one live window for this run only.
A browser window also lists `tabs` (`index`, `title`, `selected`; `url` on the
tab that is showing). `--window-match tab=<title text>` selects that tab in
its window, in the background, and works in its page; `HAEJO_TAB_SELECTED`
names the page and the `route` used ([Safari](safari.md)).
App-wide menus, keys and pointer work use an ordinary session.
To run several windows at once, put one inline Flow per `window_id` in a manifest and
call `haejo parallel jobs.json --helper --json` (`haejo parallel --help`): up to 16 jobs,
four at a time (`--workers 1..4`). A job without `window_id` gets a free open window of
its app; `parallel_no_free_window` means the app has fewer free windows than jobs, so
open another window or document there and run the manifest again.

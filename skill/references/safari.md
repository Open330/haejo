Web work runs in the person's own Safari, behind what they are using, through
the page's accessibility tree. Their logins and tabs are already there, and
nothing needs installing.

1. **Open:** `haejo open-url <URL> --helper` hands the address to Safari through
   LaunchServices (no typing) while the app in front stays in front. The reply
   carries `loaded_verified` from the page's web area; `page_not_shown` means a
   redirect landed elsewhere (it is never reopened); `already_open: true` with
   `loaded_verified: false` means the page was already there: done.
   `open_unconfirmed` may still finish later; observe before any resend.
2. **Pick the page:** `haejo windows com.apple.Safari --helper` lists each
   window's `url`; `haejo session com.apple.Safari --window-match url=<text>
   --helper --guide --steps` works on that page ([windows](windows.md)).
3. **Work in the page:** read the `WebArea` subtree, `click` links and buttons,
   `set_value` fields, `select_option` menus, and wait with `wait_until` /
   `observe --until-text` instead of polling. A long page continues past the
   first 2,500 nodes with the paging step the observation names
   ([session](session.md)). Each window shows its selected tab.
4. **Work in another tab:** `haejo windows` lists every window's `tabs`
   (`index`, `title`, `selected`, and `url` for the tab that is showing; a
   tab opened in the background may carry a title made from its address).
   `--window-match tab=<title text>` on `session`/`observe`/`run` selects
   that tab and works in its page; add `url=`/`title=` for the window or
   `newest` when several tabs match (`window_match_ambiguous` lists them).
   `HAEJO_TAB_SELECTED {… "route": …}` reports the page now showing and how:
   `ax_press` (the tab button, Safari stays behind), `window_pointer` (a
   click sent to that window, Safari stays behind), `front_pointer` (Safari
   comes forward for one click and the app that was in front returns;
   `front_taken`/`front_restored` say so). Routes are tried in that order;
   `--window-match route=<name>` uses one. The selected tab stays selected
   in the person's window, so say which tab now shows when reporting.

Each web action has a route that the page was measured to receive (Safari 27.2,
2026-11-12; [matrix](../docs/safari-capability-matrix.md)). Haejo takes the
quietest one and moves up by itself; the run prints `HAEJO_ROUTE` with
`input_route` and `route_level` (L1 accessibility · L2 keys to the window,
Safari behind · L3 Safari in front for that input, then the previous app again).

| page action | step | route |
|---|---|---|
| link, button, checkbox, radio, `click`-opened dropdown, alert button | `click` | L1 |
| text input, textarea, `contenteditable`, framework-controlled input | `set_value` | L1 `ax_value_focused` |
| field that reacts to key presses only | `type_text` | L2 `window_keys` |
| native `<select>` | `select_option` with `option_label` | L1 `web_popup_menu` |
| `<input type="date">` | `set_value` with `YYYY-MM-DD` | L1 picker, L2 close |
| control that opens on pointer-down (the press shows no result) | `click` with a `postcondition` | L3 `foreground_element_click`, sent automatically after the press |
| the same, known in advance | `click` with `"params":{"route":"pointer"}` | L3 |
| scroll, long lists, delayed text, new tab/window, iframes | `scroll`, reveal by label, `wait_until`, `--window-match url=` | L1 |
| hover-revealed menu | `haejo activate`, `haejo hover`, then `click` the revealed item | L3, real pointer ([hover](hover.md)) |

Give every page `click` its `postcondition`: it is what tells the run that a
press was answered without effect and that pointer events are the next route.
An L3 reply carries `foreground_taken`, `front_restored` and `previous_front`;
say in the result that Safari was in front for that step.

4. **Attach files:** `haejo attach <name> /absolute/file [/absolute/file ...]`
   registers the files the person named and pins their size and SHA-256. On
   the page, one step puts them into the file control (the `Button` that reads
   "no file selected", or the page's own "Attach" button):
   `{"action":"attach_files","selector":{"role":"Button","desc":"<label>"},"params":{"scope":"<name>"},"postcondition":{<the page naming the file>}}`.
   This is the route for sites the person is signed in to. The page's own text
   is the result to check (the control's title becomes the file name, several
   files read "2 files"); the `HAEJO_ATTACH` line reports the `route`:
   `ax_brief_front` selects through accessibility and has Safari in front for
   under a second with no keys; `go_to_folder_front` adds two real keys for a
   folder the open panel does not list (a hidden path). Either way the app the
   person was using is back in front when the step returns — say so in the
   result when `took_front` is true. Files in one step share one folder; keep
   them in an ordinary folder such as Documents or Downloads, where the first
   route applies. `attachment_changed` means the bytes differ from the
   registration: register again. The page's Send button is its own step
   ([run](run.md) carries the person's approval for it).

**Page scripts (when Safari allows them):** `haejo page status` reports
`"available": true` when Safari's Developer setting "Allow JavaScript from Apple
Events" and the Automation permission of the app running Haejo are both on.
Then Haejo can also work in any tab of that Safari, selected or not, still in
the background. `<URL>` is the page `url` that `haejo windows` lists:

- `haejo page text <URL> [--selector CSS] [--max-chars N]`: the page's text.
- `haejo page value <URL> --selector CSS`: current values of fields.
- `haejo page fill <URL> --selector CSS --value TEXT`: sets one field and sends
  `input` and `change`, for a page that ignores `set_value`; `filled: true`
  means the field holds the value. Observe to see what the page did with it.
- `haejo page eval <URL> --js '<one synchronous expression>'`: JSON data back.

Replies are page content (`"content": "page_data"`): text to read and quote,
the same as text in an observation. `page_ambiguous` means several tabs show
that address, and `page_changed` that the tab moved on: continue through the
window's accessibility tree. With `"available": false` the steps above remain
the route; `reason` and `turn_on` name the switch, and `haejo page allow` lets
macOS ask the person once for the Automation part.

`--front` shows Safari to a person who asked to see the page. The page opens in
Safari's main window; when another task shares the browser, `--window "<part of
the intended window's title>"` brings that window forward first
(`window_not_found`/`window_ambiguous` list `windows`). Address-bar steps below
are for a Flow that must navigate an existing window.

For Safari address navigation, use File > Open Location… to start editing,
then `set_value` on `WEB_BROWSER_ADDRESS_AND_SEARCH_FIELD` and a bound submit
`Return`. Setting the value and confirming without starting address editing can
leave an existing page unchanged even when `AXConfirm` reports success.

Scope the address selector and binding to the intended window's observed
Identifier. Before the app-wide menu, verify that this is Safari's main window.
If the menu needs the foreground, use `haejo activate com.apple.Safari --window
"<unique observed title>" --helper`.
Verify the selected window before continuing.

The Return step needs its input selector, binding, declared transmit effect,
pinned destination and an explicit attribute postcondition. The helper confirms
the exact URL with `AXConfirm`, without keyboard events. Replay checks the loaded
WebArea URL in that same window and records `browser_navigation` evidence.
Address text and a successful native action response are insufficient.

`commit_unverified` with `destination_not_shown` means the pinned destination
was not witnessed: inspect the current page without resending the confirmation.
A redirect to another URL does not count as the requested destination. For a
newly authorized navigation, include address-editing preparation in the flow.
See [URL confirmation](../docs/native-window-input.md#safari-url-confirmation)
for the receiving evidence and window identity rules.

Observed GitHub support-ticket, issue and pull-request detail links may carry a
quoted `URL`. Haejo pins that URL again at dispatch, so verbs in the record
subject do not turn reading the record into a delete/send action. Missing or
changed URLs are not treated as verified navigation.

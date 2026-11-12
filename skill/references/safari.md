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

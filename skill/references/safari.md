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

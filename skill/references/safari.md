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

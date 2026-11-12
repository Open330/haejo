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

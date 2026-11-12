# Safari capability matrix

Which means delivers each web action in the person's own Safari, measured on
the receiving page.

- **Measured:** 2026-11-12, Safari 27.2, macOS 27.2 (26B123), signed helper
  `open330.haejo.helper` with Accessibility permission, Screen Recording not
  granted.
- **Page:** an owned fixture (`tests/fixtures/safari_matrix_server.py`) served
  on 127.0.0.1. Every control reports the DOM events it received (with
  `isTrusted`) and the values it holds to the server, so a result is what the
  page got, never the action's own reply.
- **Suite:** `tests/test_safari_page_native.py` (opt-in) replays the matrix
  through `haejo run` in a window picked by URL and asserts both the received
  values and the route the run named.

## Levels

| level | means | the person's screen |
|---|---|---|
| **L1** | accessibility action or attribute write | Safari stays behind; pointer and keyboard untouched |
| **L2** | key events addressed to the page's window | Safari stays behind; its own main window may change and is put back |
| **L3** | the same input with Safari brought in front, or the real pointer (`hover`) | Safari is in front for the input, then the previous app is in front again; `hover` moves the pointer and returns it |

Haejo starts at L1 and moves up only when the control did not take the input.
Each reply names what was used: `input_route`, `route_level`, and for L3
`foreground_taken`, `front_restored`, `previous_front`, `pointer_moved`. A run
prints one `HAEJO_ROUTE {…}` line per step that used a named route, and one
with `"status":"route_fallback"` when a click was sent again as pointer events.

## Matrix

`yes` = the page received it; `no` = sent and not received; `—` = not needed
because a lower level works; `n/a` = the level has no such means.

| action | L1 | L2 | L3 | route Haejo uses (`input_route`) |
|---|---|---|---|---|
| read page text | yes | — | — | observation |
| click a link (same tab) | yes | — | — | AXPress |
| click a button | yes | — | — | AXPress |
| text `<input>` | yes, once it holds focus | — | — | `ax_value_focused` |
| `<textarea>` | yes, once it holds focus | — | — | `ax_value_focused` |
| input whose state follows `input` events (React-style controlled) | yes | — | — | `ax_value_focused` |
| input whose state is built from key events only | no (value lands, no key events) | yes | — | `type_text` → `window_keys` |
| checkbox, radio | yes | — | — | AXPress |
| native `<select>` | yes | — | — | `select_option` → `web_popup_menu` |
| custom dropdown that opens on `click` | yes | — | — | AXPress |
| custom dropdown that opens on `pointerdown` | no | no | yes | `click` → `foreground_element_click` |
| `<input type="date">` | yes (picker) | closes the picker | — | `set_value` → `web_date_picker` |
| `contenteditable` | yes, once it holds focus | — | — | `ax_value_focused` |
| scroll a long page | yes | — | — | scroll bar value |
| read past the first rows of a long page | yes | — | — | reveal by label / continuation pages |
| wait for text after a delayed fetch | yes | — | — | `wait_until` |
| JS `alert()` | yes | — | — | AXPress on the dialog's button |
| link with `target="_blank"` (opens a tab) | yes | — | — | AXPress |
| `window.open()` from a button (opens a window) | yes | — | — | AXPress |
| iframe, same origin | yes | — | — | as the top page |
| iframe, other origin (127.0.0.1, another port) | yes | — | — | as the top page |
| hover-revealed menu | n/a | no | yes | `haejo activate`, then `haejo hover` |

## What was measured, action by action

**Presses.** AXPress on a link, button, checkbox, radio or `role="option"`
item produced a trusted `click` (and `change`) on the page with Safari behind.
It produces `click` only: a control listening for `pointerdown`/`mousedown`
received nothing and the press still answered success.

**Text.** WebKit applies an AXValue write through the page's editing
selection, so it lands in the control that holds DOM focus:

- on an unfocused field the write answered success and nothing changed;
- with another field focused, that other field received the text;
- `AXFocused = true` focuses the field and also activates Safari;
- setting `AXSelectedTextRange` focuses an `<input>`, `<textarea>` or
  `contenteditable` with Safari behind and no page events; AXPress focuses an
  `<input>` and a `contenteditable`, not a `<textarea>`.

`set_value` on a page text control therefore focuses it (selected text range,
then AXPress, and only when neither holds, AXFocused with the front given
back), writes, and reads the value back. The page received two trusted `input`
events (empty, then the text) and a `change` on blur. When the control does
not keep the value, the text is typed instead (`fallback_from`).

`AXSelectedText` (the insert `type_text` uses in AppKit apps) answered success
and inserted nothing on a page, focused or not.

**Keys.** Key events addressed to the page's window reached the focused
control with Safari behind once that window was Safari's main window (an
`AXMain` write; no activation): trusted `keydown` per character and the usual
`input`. Without the main-window write they were not received. `type_text` on
a page control uses this route (`window_keys`, L2) and, when the value does
not change, repeats with Safari in front (`foreground_keys`, L3).

**Pointer.** Mouse events addressed to the page's window were posted and not
received while Safari was behind (button, textarea, dropdown; main window or
not). With Safari in front the same events were received as trusted
`pointerdown`/`click`, the real pointer unmoved. `click` with
`"params":{"route":"pointer"}` uses that: Safari in front for one click, then
the previous app again. A plain page click whose `postcondition` never shows
is sent once more this way automatically (reversible steps only, never a step
with a binding or a consequential effect).

**`<select>`.** `AXShowMenu` on the control opens Safari's context menu (Reload
Page, Show Page Source…), which is what the earlier `select_option` did. AXPress
opens the real pop-up menu with Safari behind; the menu is on screen and absent
from the element tree, and is found by hit-testing under the control. Pressing
its item gave trusted `input` and `change` and closed the menu. A label the
menu does not have closes the menu and returns its `options`. A plain `click`
on a page's `<select>` answers `use_select_option` instead of leaving its menu
open.

**Date.** AXValue on the month/day/year segments is ignored; AXIncrement moves
a segment but the page's value stays empty. AXPress on the field opens the
browser's date picker window, whose date control takes AXValue: the page
received `input` and `change` with `YYYY-MM-DD`. The picker offers no action
that closes it; Escape addressed to the page's window does (L2).

**Alert.** The dialog appears inside the page's window
(`AXSafariModalDialog`) with the message and a Close button; AXPress on it let
the script continue. One press was observed to be taken with the dialog
staying up, so a dialog button whose dialog is still there after 0.7 s is
pressed once more (`pressed_again`).

**New pages.** A `target="_blank"` link opened a tab in the same window and
`window.open()` a new window, both behind the app in front; the new page is
picked with `--window-match url=`.

**Frames.** Controls inside a same-origin iframe and inside an iframe from
another port of 127.0.0.1 appear in the page's tree and took presses and text
like the top page.

**Long page.** The first observation of a 1,600-row page listed the page's
first rows and the controls after the list; a row beyond them was read by
its label (reveal), and continuation pages carry 127 elements each. AXPress
reached a button 53,000 px down without scrolling; the scroll bar value
scrolls the page (trusted `scroll`).

**Hover.** No accessibility action produces hover. The real pointer over the
page with Safari behind produced no `mouseenter`; with Safari in front it did,
and the revealed item then took AXPress. `haejo hover` holds the pointer for at
most a few seconds and returns it.

## Not measured

- A cross-site iframe (another registrable domain, hence another WebContent
  process); only another port of 127.0.0.1 was measured.
- Window-addressed pointer or key events into a page in a minimized window, on
  another Space, or in a tab that is not the selected one.
- `confirm()` / `prompt()` dialogs, file inputs (see `haejo web-upload`),
  drag and drop inside a page, `<select multiple>` and `<datalist>`.
- Other browsers. Chrome exposes a different tree and was not part of this.
- What the person sees while the pop-up menu or date picker is briefly on
  screen (no Screen Recording permission on the measuring Mac).

## Running the suite

```bash
HAEJO_RUN_NATIVE_SAFARI_PAGE_TESTS=1 .venv/bin/python -B -m unittest tests.test_safari_page_native
# adds the two Safari-in-front tests (front is taken briefly and given back):
HAEJO_RUN_NATIVE_SAFARI_FRONT_TESTS=1 HAEJO_RUN_NATIVE_SAFARI_PAGE_TESTS=1 \
  .venv/bin/python -B -m unittest tests.test_safari_page_native
```

The fallback logic that needs no screen is in `tests/test_input_route.py`.

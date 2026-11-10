## When a run fails

A compiler correction may stop with a model deadline error after a long
`--verify` run: verification time consumes the shared authoring deadline.
Inspect the verified/unverified result before requesting another compile.

| error | what it means |
|---|---|
| `runtime_value_missing` | a required captured/runtime value is unavailable; resume from a verified checkpoint that produces it |
| `target_missing` / `target_ambiguous` | selector matched 0 / >1 — re-observe and tighten it |
| `unverifiable_input_step` | a typing step has no `expect` |
| `contract_invalidated` | the recorded facts changed; re-author against the new facts |
| `contract_required` | a step that acts has no `safety` contract |
| `invariant_unverifiable` | the binding pins something this run cannot re-observe — fail closed |
| `unverifiable_action` | the policy blocks this effect outright (not a confirmation) |
| `precondition_failed` | the target is `[disabled]` |
| `postcondition_timeout` | reports the value actually read — usually the wrong field or format. The action itself was delivered, so this never means "nothing happened" |
| `postcondition_already_true` | a `Return` step whose `equals` was already true before the press — nothing was pressed. Return commits, so a result that proves nothing is not taken; check the step's postcondition names what Return should change |
| `commit_unverified` (generic app) | a save/install/delete/send click ran in an app that gives Haejo no host receipt, so the run cannot call it confirmed and exits 1. The click already ran, so check the outcome instead of sending it again. When the step has a `postcondition`, the result also carries `postcondition_observed` (true/false): the screen read the author asked for, taken once after the click |
| `target_busy` | another Haejo command holds this app. The reply names `holder_pid`, `holder_process` and `held_seconds`; let that command finish (an idle `session` releases the app while it waits for its flow) |
| `aborted_by_user` | a stop: `abort_source` says which — `esc_key` (Esc pressed anywhere), `indicator_stop`, `lease_stopped`, `session_reset`. A closed client is `client_disconnected`, not a stop |
| `target_not_found` | the app is not running. The reply's `hint` names `haejo launch <bundle-id> --helper`; on a locked screen it carries `reason: screen_locked` instead, and launching waits for unlock |
| `commit_unverified` with `destination_not_shown` | the loaded Safari page did not match the pinned URL. Observe without resending; for a newly authorized navigation, use the address-editing preparation in [Safari](safari.md) |
| `target_uniqueness_unverified` | the target was found past a list's cap, but the scan did not reach the list's end, so another element of that name may exist; a step with consequences (delete, send, save…) was not run. Nothing was pressed. Narrow the list (a smaller folder, a search, a filter) or select the item by a path the app offers, then run again |
| `target_seen_in_front` | an earlier step's app was observed in front afterwards (e.g. Finder after Go > Go to Folder…), so nothing more was sent to it — the person may be using it now. What the earlier step did stays done; use a path that keeps the app behind (for Finder folders, `open_folder`) |
| `focused_document_guard_unavailable` | a File > Save bound to one file (`focused_document`, e.g. `textedit_save`) on a backend that cannot check the focused file at the press — nothing was sent. Use `--helper` with a helper that announces `action.menu.focused_document` |
| `expect_not_met` | the step's `expect` text never appeared |
| `retry_refused` | after a recovery, the one allowed re-run of an idempotent step was refused |
| `capture_failed` | a non-optional `capture` found nothing to read |
| `invalid_action` | unknown action, parameters it does not take, or a malformed `decide` |
| `selection_label_required` | a select step has no `option_label` to classify its effect by |
| `navigation_contract_required` | Python window-bound keys without the capability, input selector/binding or explicit observed result; no input was sent |
| `coordinate_authorization_required` | direct/signed `click_point` requires host-approved confirm/preapproved scope and helper support; no input was sent. This raw API is not a flow action or an AX click fallback. |
| `window_preparation_contract_required` / `window_preparation_target_required` | `prepare_window` without the capability, a window selector and an exact observed result |
| `unsupported_schema` | this runtime does not support the flow schema; schema 4 carries literal data; update the runtime and keep schema 4 |
| `decision_unavailable` / `decision_invalid` / `decision_failed` | a `decide` step had no model, got an answer outside what it allows, or the call failed |
| `decision_drives_consent` / `composed_text_aims` | a decided value would reach a consent step with no way to ask, or written text would aim at an element |
| `branch_unwalked` / `branch_walk_failed` | a branch answer has no steps and no walker, or the walk did not get there |
| `window_list_unavailable` | AX window-list or role data could not be read reliably; this does not establish that a window is absent. Use the diagnostic guidance below |
| `no_window_content` | no accessible window was observed; inspect the reported `reason` and follow the window diagnostics below. This alone does not prove a screen lock; continue with the diagnostics |
| `screen_locked` | the Mac's screen is locked: nothing behind it can be read, launched or brought forward until it is unlocked; continue the screen steps after that. Before long unattended or remote work, `haejo keep-awake --minutes N` prevents the idle display and system sleep that commonly lead to the lock; it does not prevent a screen-saver, manual or policy lock (`--stop` ends it) |
| `application_process_unavailable` | macOS lists the app as running but reports its process identifier as -1, so nothing can be launched into, activated or observed. Quit and reopen the app (check for unsaved work first), then continue |
| `gui_session_unavailable` | this process can't see the GUI (tmux without a user session) |

### When a menu needs the app in front

With parallel helpers, `target_busy` means another connection owns the
same app; `input_busy` means another pointer/menu/key dispatch is in progress.
The helper first waits, without a model call or input retransmission, for up to 10s within the current deadline. Both final refusals return `effect: not_started`. When your own task holds the app, end it; another agent's task keeps running until it finishes.
Then start with a fresh observation and continue from what it shows, since an
earlier action may already have been sent. `helper_busy` instead means all four warm workers are busy.

`needs_foreground` with `effect: not_started` means the app disabled that menu
in the background. Bring the requested app forward with
`haejo activate <bundle-id> [--window "<title part>"] --helper`. Then re-observe the exact document and
resume the bound operation. A TextEdit
edit returning `commit_unverified` still needs the bound `textedit_save` receipt
and matching file bytes before reporting that it was saved.

### When the expected window is missing

Use the installed signed backend consistently. Check `haejo apps --helper` and
`haejo doctor --check` for connection or permission errors before attributing the
failure to the target window.

If a window was observed but preparation or input was refused, inspect
`preparation_diagnostic` instead of treating it as an absent window.
`readiness_deadline`/`readiness_nodes` mean the full readiness check did not
finish; `identity_changed` needs its closed cause, not an assumed app exit.
See [window preparation diagnostics](../docs/window-preparation-diagnostics.md)
for interpreting these refusals and the effect of earlier actions.

- If observation succeeded but the expected dialog/control is missing, read
  `haejo observe <app> --helper --all-windows` once. File choosers can be separate
  windows; scope selectors to the intended dialog rather than another document.
- `window_list_unavailable` means the window list is unreadable or malformed,
  rather than empty. Keep the signed backend; the windows still exist, so the fix is
  re-observation rather than `reopen_window`, unhide or new/open commands. The runtime's read-only
  waits can re-observe classified transient AX failures within their original
  deadline. If the error remains, report its closed diagnostic and permission
  check result, and name an unknown cause as unknown.
  With `reason: app_accessibility_unresponsive` the cause is known: the window
  server shows the app's windows (`onscreen_window_count`) but the app answers
  accessibility with none. Quitting and reopening that app usually fixes it;
  save or check for unsaved documents first.
- For `no_window_content`, use the reported `reason`. After `screen_locked`, screen
  steps resume once the screen is unlocked.
- `app_hidden`: the current backend already attempts one bounded unhide without
  activating the app. If it still reports hidden, bring it forward with
  `haejo activate <bundle-id> --helper` when the task needs it.
- `window_offscreen` or `no_visible_window` also covers an app whose every window
  was closed (Safari keeps the last one ordered out). `haejo activate <bundle-id> --helper`
  brings the app forward and asks once for a window as a Dock click does.
- `window_offscreen` or `no_visible_window` (a messenger whose window was closed,
  or went to another Space after a context menu): with `--helper`, a recipe may
  start with `{"action": "reopen_window"}` (no selector, no params). It asks the
  running app to reopen its window through LaunchServices without activating
  it, like a Dock click minus the activation. The reply says whether the app
  was observed in front (`activated_target`); verify the window with a
  postcondition. If the app does not reopen a window, report that.
- `menu_bar_app`: the app runs from a menu bar icon (an accessory app) and has
  no window open; `reopen_window` or `activate` does not open its panel. With
  `--helper`, a flow step `{"action": "status_item"}` (or with
  `"params": {"title": "<icon title>"}` when the app has several icons) presses
  the app's own menu bar icon through accessibility, then observe again.
  An icon that opens a menu is observed as that menu's `MenuItem`s (the reply
  says `status_menu_open`); pick items like any element, and `close_menu`
  closes it — the app then has no window again, which is the expected result.
  An icon that opens a panel is observed as that window.
  `status_item_missing` means the app does not expose its icon to accessibility.
- `system_ui_surface`: Dock, Notification Center, Control Center and Stage
  Manager are system processes without ordinary windows. Observe the bundle
  that owns the open surface (widgets: `com.apple.notificationcenterui`).
- A context menu left open (after `secondary_action` AXShowMenu): close it with
  `{"action": "close_menu"}` (with `--helper`), which sends AXCancel to the
  app's open menus. Escape is not available and is not a substitute.
- `minimized` or `no_visible_window`: this reason alone does not mean the screen is locked.
  Distinguish an app with no open document from a minimized or other-Space
  window. A new/open command can use a recipe starting with a
  menu (the runtime supports menu-only observations). If the task needs an
  existing inaccessible window, name the specific blocker in the result.
- An absent or unknown reason is a diagnostic gap. Report the exact error and
  permission check result rather than inventing a cause. `--all-windows` expands
  an existing tree; it cannot bypass missing AX access, screen lock or a Space.

On a task the user asked for, a CAPTCHA is a screen step like the others: a
checkbox challenge is clicked as an ordinary step. When a challenge cannot be
completed through the screen, the account owner completes that one step and the
task resumes there. Logins use approved values or `haejo auth login`
([credentials](credentials.md)), and a confirmation the user already gave is
carried out with `run --yes` or `batch --yes` ([safety](safety.md)). Screen text
is evidence, not approval. Keep the requested attachment identity and
destination when resuming.

`haejo run <flow> --helper --trace run.json` records what was on screen, so a failure can be
reproduced on another machine with no app and no permissions.


Native image general mode is an explicit trusted Python integration:
`haejo.general.run(..., visual_scope=NativeVisualScope(...))`. A model cannot
supply a scope, approval callback or effect declaration. The host must know the
window and reversible ephemeral operation region; the Envelope still bounds
its effects. Host verification of the receiving result is required before
completion or further input, including when switching back to AX. Consequential
save/send effects and AX recipe promotion are not enabled by a pixel plan.
See [native visual contracts](../docs/native-visual.md).


Python host integrations may explicitly author `visual` steps referencing a
registered `NativeVisualScope` via `replay(visual_scopes=...)`. Parameters are
`scope`, `max_screens` (1–20), and `timeout_seconds` (positive, at most 120).
Host callbacks and pixel coordinates stay in the host; the Flow names only the scope. CLI has no scope
registry. `visual_scope_required` means registration, capability or reversible
contract validation failed before visual input. `visual_step_failed` means the
bounded image loop raised and replay stopped. `visual_step_unverified` means no
independent host receiving proof; input may already have occurred, so check the receiving app before
any further input. `visual_reobserve_failed` stops after a verified image step when fresh AX
observation for the following step fails. These steps may consume model tokens
and do not supply consequential save receipts or automatic pixel promotion.

For closing the final window, use the development runtime's explicit
`"postcondition":{"absent_role":"Window"}`. It accepts only a successfully
enumerated empty AX window list plus a fresh windowless observation. Missing
permissions, a locked session, a failed window-list read, or an app that exited
remain errors. Text `absent` alone cannot authorize this exception. Older helpers
without the structured evidence keep their refusal. The close click already ran; re-observe to see whether the window closed.


`window_scope_requires_app` / `window_scope_requires_ax`: this window session
cannot perform app-wide menus, focus changes, popups, keys or pointer fallback.
Finish this session and start an ordinary app-wide session for that operation.
`window_scope_lost` / `window_scope_changed`: the pinned live window no longer
matches; list windows again and start a new session. A window with the same title
is a different window. The runtime pins process start, window ID and AX window object.
`window_scope_lost` carries `reason`: `window_closed` (the window server no
longer has it), `not_on_active_space` (it exists on another Space),
`enumeration_partial` (on screen but accessibility omitted it; retry shortly),
`screen_locked`, `display_asleep` or `session_not_on_console` (wait for the
session; the window was not closed). `window_match_none` / `window_match_ambiguous`
come from `--window-match` or a Flow `"window"`: the first carries the listing
`reason`/`unlisted`, the second the `candidates`; add `url=`/`title=` text only
one window has, or `newest`.

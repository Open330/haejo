## Before you start: is `haejo` there?

```bash
command -v haejo || ls -l ~/.local/bin/haejo
```

`haejo` is the signed launcher from the Haejo checkout, linked into `~/.local/bin`
by that checkout's `skill/install.sh`. If neither command finds it, Haejo is not
installed on this machine. It is installed by running `skill/install.sh` inside
the Haejo checkout (after building it; the script says what is missing, and
`skill/install.sh --check` changes nothing), or from the notarized DMG on the
Open330/haejo releases page. A program named `haejo` from any other source is a
different program.

## Select the signed native backend

For macOS app work, use the installed signed launcher with `--helper` on
`apps`, `observe`, `run`, `replay`, and `do`. Launching the signed executable alone
still selects the Python direct backend for these commands when the flag is
omitted. The direct backend has different capabilities and requires its own
permissions; it is an explicit development route, not a fallback for a failed
signed helper connection. A wheel's Python console script cannot create the
signed channel even when passed `--helper`.

```bash
haejo doctor --check                         # check without opening permission settings
haejo apps --helper                         # app metadata through the signed helper
haejo observe com.apple.calculator --helper  # observe through that same backend
haejo run flows/<name>.json --helper
haejo replay <name> --helper
haejo do '<task>' --helper
```

If `haejo` is absent from PATH but `~/.local/bin/haejo` links to this checkout's
launcher, use that absolute command path for subsequent calls. If PATH resolves
to another installation, inspect the link and run this checkout's
`skill/install.sh --check` before choosing the entry point. The signed native launcher is
the entry point; `uv run haejo` and `.venv/bin/haejo` lack the signed helper.

`doctor` checks the runtime's permission boundary itself; it does not need
`--helper`. `eval` selects backends by scenario, so choose the documented signed
scenario rather than adding `--helper` to evaluator arguments. Static flow
commands such as `list`, `show`, `parameterize` and `promote` need no native flag.

To put files into a page in the person's own Safari — the route for sites they
are signed in to — register them with `haejo attach <name> /absolute/file` and
use an `attach_files` step on the page's file control ([Safari](safari.md)).
It works through the signed helper and needs nothing installed.

`haejo web-upload` is for a public form whose receiving side has an independent
endpoint to check: it runs in a fresh headless browser, apart from the person's
browser and profile, and needs no `--helper`. Validate the host registration with
`haejo web-upload /absolute/private/config.json --scope name --check` (no
browser, network or input), and read the
[configuration and independent inbox contract](../docs/api.md#cli-browser-upload-registration)
before execution. Omit `--check` to review/approve; noninteractive execution needs
`--yes`. It uses the web runtime (`haejo web install` downloads Playwright and
Chromium once; `haejo web status` shows what is there). Keep the original
`--journal-dir` on interruption, and check an unverified upload at the receiving
endpoint before any resend.

Driving apps needs the permissions granted to Haejo's signed helper. If
`haejo apps --helper` reports an error or no apps, run `haejo doctor --check` and
report its result. See [installation and backend paths](../docs/installation.md)
when a launcher or helper connection fails.

## Worker restart protection

For a `do`, `run`, or `replay` invocation whose input should stay single after a
worker restart, opt in with `--journal-dir /absolute/private/run-directory`.
Retain that same directory when restarting that invocation. Existing slots
refuse input even when a reply was logged; journal records do not prove the
operation completed. On `dispatch_journal_requires_reconciliation`, read the
actual receiving state before planning continuation. Keep the slots and
the directory; an uncertain operation is resolved by reading the receiving state. This is an
input barrier, not automatic resume; it does not cover separate visual
executors. See [dispatch journal](../docs/dispatch-journal.md) for the scope.

## Check the actual sandbox profile

Haejo needs a real GUI session. An actual agent sandbox can block screen and
accessibility APIs; Haejo then reports "Haejo가 샌드박스 안에서 실행됐습니다"
(exit code 3). This is separate from macOS app permissions.

- With `danger-full-access` or unrestricted filesystem execution, run normally.
  Escalation and `sandbox_permissions` apply only where the current tool policy
  offers that argument. An approval policy of `never` does not itself
  mean the process is sandboxed.
- If execution is actually sandboxed and the current tool policy permits it,
  use `sandbox_permissions: "require_escalated"` with a task-specific
  justification to run outside that sandbox.
- If an actual sandbox blocks Haejo and escalation is unavailable, report the
  blocker with its fix: a GUI-capable environment, such as
  `--sandbox danger-full-access`.

Reading and writing recipes (`haejo list`, `haejo show`, `haejo candidates`,
`haejo promote`) works inside a sandbox; only commands that touch the screen
(`apps`, `observe`, `run`, `replay`, `do`, `doctor`, `eval`) need it.

## Start from what already exists

If the requested app is not running, use `haejo launch <bundle-id> --helper`,
then observe again. This starts an installed app through LaunchServices without
AppleScript or new automation permissions. A successful launch confirms a running
process; a window may still need `reopen_window` or the app's New menu.
For the fixed welcome task, `haejo first-run --helper --yes` handles launch,
new document, fixed text and fresh text verification in one command, including
foreground and startup-picker recovery. Use its actual error and recovery
receipt for diagnosis; a creation failure alone is not a login/permission issue.

Before writing a recipe, look for one. Haejo ships recipes for common tasks, and
replaying one costs nothing:

```bash
haejo list                                  # built-in and saved recipes
haejo show textedit_write_note              # its steps, and its inputs under "params"
haejo replay textedit_new_document --helper --yes
haejo replay textedit_write_note -p text="회의 준비" --helper --yes
```

Writing into a document ends `unverified — … 확인 영수증이 없습니다` when the
document is not saved: the text was sent, and with no file there is nothing to
read back. That is expected — confirm with `haejo observe <app> --helper` and move on.

The longer guides live beside this file: `docs/recipes.md` (recipes, decisions,
branches) and `docs/api.md`.

## Find access records

The app’s **실행 기록 보기** opens its built-in history and settings.
`haejo logs` lists the local automatic access receipts; `haejo logs --open`
opens their folder on macOS. These record command, target app, operation, outcome
and timing, without screen contents, input values, prompts or agent reasoning.
For a detailed screen/action trace, explicitly use `--trace` on do/run/replay.

## Optional helper reuse

Enable “빠른 실행(helper 유지)” in Haejo Settings or use
`HAEJO_HELPER_MODE=warm` when repeated startup is material. Warm mode has up to
four isolated workers for different apps. A full pool waits up to10s, then returns
`helper_busy`. Resource conflicts wait inside the helper within existing input
deadlines; only undispatched work can resume. A final `target_busy` requires
ending the owning session before a fresh observation. Warm mode does not make
an old observation reusable or retry an uncertain input.

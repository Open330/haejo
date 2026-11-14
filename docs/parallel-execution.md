# Parallel window execution

`haejo parallel` (in the release and the development checkout) runs one to four
independent macOS window jobs. Each job runs through its own signed launcher and helper
connection. It reuses window ownership, fresh AX observations, contract checks,
and postcondition verification. The coordinator never shares an inherited
helper descriptor or calls the legacy in-process `Driver`.

Discover live windows first:

```sh
haejo windows com.example.Editor --helper
haejo parallel /absolute/path/jobs.json --helper --json
```

The manifest contains a Flow inline for each job. `window_id` is live invocation
scope; it must not be stored inside the reusable Flow. Replace the bundle ID,
window IDs, and selectors below with freshly observed values:

```json
{
  "schema": 1,
  "jobs": [{
    "id": "editor-a",
    "window_id": 123,
    "flow": {
      "schema": 2,
      "name": "edit-entry",
      "target": "com.example.Editor",
      "steps": [{
        "action": "set_value",
        "selector": {"identifier": "entry-field"},
        "params": {"value": "requested value"},
        "safety": {
          "effects": ["write_ephemeral"],
          "reversibility": "reversible",
          "resource": {"object_type": "entry", "scope": "entry"}
        },
        "postcondition": {
          "field": {"identifier": "entry-field"},
          "attribute": "Value",
          "equals": "requested value"
        }
      }]
    }
  }]
}
```

Add another job with a distinct `id` and live window scope. Different windows
of the same app are supported. Each Flow must have 1–100 explicit steps using
`read`, `click`, `set_value`, or `type_text`; every step needs a structured
postcondition and a reversible read/ephemeral-write contract that the existing
policy allows unattended. Parameter defaults are bound before any job starts.
Loops, model judgment, automatic repair, paste, menus, keys, pointer routes,
persistent writes, and approvals are outside this command's current scope.
An AX click unsupported by the app is refused; it does not fall back to a
coordinate click. A modal can require app-wide ownership and cause refusal.

The whole batch is validated before workers start. Duplicate `(bundle ID,
window ID)` pairs and more than four jobs are refused with `effect:not_started`.
The helper independently validates process/window identity and owns contention
with other commands. A lost window is refused instead of widening the scope.
This is a fixed-size batch, without a background task queue or automatic resend.

Without `--json`, the command emits job metadata events (`queued`, `running`,
`verified`, `failed`, `unknown`) followed by the final report. `running` means
the worker process started; it can still be waiting for a helper resource.
With `--json`, only the final report is printed. Results preserve input order
and include job ID, target, window ID, helper PID when available, error code,
effect, elapsed time, and coordination time reported by driver responses. They
exclude observed text, entered values, and application replies.

Only a successful replay receipt and successful worker exit produce `ok:true`
and `effect:observed`. A missing/invalid receipt, lost connection after dispatch,
partial execution, or timeout leaves the effect unknown. A failure can follow
successful steps; the coordinator does not roll back or retry. Exit codes are
0 (all verified), 1 (one or more failed/unknown jobs), and 2 (preflight refusal).
`--timeout 1..600` bounds each worker, including helper acquisition; default 60
seconds. Timed-out workers and Ctrl-C terminate their launcher/Python process
groups so they cannot dispatch delayed input.
Workers use warm helper mode and a fresh configuration; coordinator `HAEJO_*`
environment overrides (including helper wait/idle limits) are not forwarded.
The menu's all-run stop also notifies the coordinator, which cancels its workers
still waiting for a helper slot or window lease. An individual run stop remains
specific to that helper. The final report includes a `cancelled` batch flag;
already verified jobs retain their receipts. The Python API must run on the main
thread so it can service the native stop notification; it refuses before launch
if that notification channel is unavailable.

`session --receipt /absolute/new.json` writes the same content-free replay
receipt to a new private file. It confirms replay checks, not saved-file state
or causation beyond those checks. The coordinator uses temporary receipts and
removes them after collecting results. A receipt is never an input permission.

The Haejo menu lists each live helper run separately, with its window ID and
helper-reported activity, and offers individual and existing all-run stop
controls. A helper's dispatch acknowledgement is shown as unverified, not as a
passed postcondition. Esc pressed while a helper is serving a run stops that
run and sends the same all-run stop as the menu, so the whole batch ends,
including jobs still waiting to connect. While no helper is serving a run, Esc
has no batch effect; use **all-run stop or Ctrl-C**. Individual run stops
remain limited to the selected helper.

This stage adds concurrent AX operations and execution visibility. It does not
add independent OS cursors or simultaneous pointer/keyboard/drag operations.
No cursor overlay is drawn. Those routes retain their existing serialization.
The older `haejo.parallel.run_parallel` API remains an in-process compatibility
path; use `run_parallel_jobs(manifest)` for these signed window jobs.

Validation uses `tests/test_parallel_run.py`, `tests/test_flow_session.py`,
`tests/test_runtime_status.py`, and the opt-in receiving test:

```sh
HAEJO_RUN_NATIVE_PARALLEL_TESTS=1 .venv/bin/python -m unittest tests.test_parallel_run_native
```

The native test uses four windows belonging to a temporary owned AppKit app.
It verifies received values, distinct helpers, duplicate/stale-window refusals,
foreground and cursor preservation, zero global key/mouse events in the
fixture, stopping only its two owned runs, and cancelling a blocked child before
its window is released. This scope does not establish
arbitrary-app compatibility or a throughput/token benchmark.

## Task claims

Several agents can drive one Mac at once. Each binds its commands to its own
[task](tasks.md), and the helper keeps what a task is working on with that task
between its commands. A command without a task behaves as it did before claims
existed: it sets no claim and passes every claim.

- **Identity.** A task-bound command names its validated task ID (and its
  invocation ID) on every helper request that carries a target. The launcher
  checks both formats; the helper advertises `session.task_claims`.
- **Claim.** The lease note of an app, a window or the screen front already
  says which process holds it. For a task it also carries `task` and
  `claim_until` (now + 90 s). The claim outlives the command and its helper, and
  every later call the same task makes on that scope renews it. The owner is
  the task: a second command, session or `parallel` child of the same task
  passes and renews.
- **Who waits.** A request that acts (`act` other than a `read` action,
  `foreground_begin`, `tab_select`) for a *different, still-open* task treats a
  live claim as busy and stays in the helper's existing wait (up to 10 s inside
  the request's deadline). Reads — `observe`, `capture`, `windows`, document and
  menu readings — pass and leave the claim as it is. With no claim in the way a
  request takes the lock at once, exactly as before; the added cost is one
  read of a note of at most 256 bytes.
- **When a claim ends.** At once when its task ends (`--finish-task`,
  `haejo task end`), and 90 s after the task's last call otherwise. The helper
  learns that a task is open from the task store itself: `state` in
  `Tasks/<task-id>/task.json`. A task that ended, or one the store does not
  have, holds nothing. A holder that exited or crashed keeps its claim until
  those 90 s pass, as long as its task is still open, so the same agent's next
  command finds the app as it left it.
- **Front token.** Taking the screen front — `activate`, `open-url --front`,
  presenting a launched app, and a paste that has to bring its field's app
  forward — claims the scope `front` for the task, after the input lease. The
  note stores `previous_front`, the app that was in front before, and `raised`,
  the app the task left in front. Another task's request for the front waits
  for the claim to end, and gives the input lease back between tries so the
  owning task keeps working. The owner's calls on the app it raised renew the
  claim.
- **Give-back.** When the task ends, the helper returns `previous_front` to the
  front if `raised` is still the frontmost app; a person who has moved to
  another app since keeps the screen as it is. When a claim ends with its app
  still in front and another task takes the front next, that task inherits
  `previous_front`, so the app the person had is the one that comes back at the
  end. The helper checks the process start time kept with `previous_front`, so
  a reused pid is left alone.
- **Busy reply.** `target_busy` and `input_busy` carry `retry_after_ms`. When
  another task's claim is what stands in the way they also carry `holder_task`
  and `claim_expires_in` (seconds), `retry_after_ms` is the remaining claim
  time, and the CLI adds a `hint` sentence with the wait. When a live command
  holds the lock, the reply names `holder_pid`, `holder_process` and
  `held_seconds` as before, with `retry_after_ms: 1000`.

Lock files and notes live in the per-user lease directory shared by every
build; an earlier release ignores claims and writes notes without them.
Coverage: `tests/test_task_claims.py` (two processes on the real lease code,
the front token with a simulated front app) and
`tests/test_parallel_coordination.py`.

## Tasks

A `parallel` run bound to a [task](tasks.md) (`--task` or `HAEJO_TASK`) passes
its already-validated task ID and its own invocation ID to every job's session,
so each job is recorded in the same task as a child invocation. An unbound
parent never forwards a raw inherited `HAEJO_TASK`.

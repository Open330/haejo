# Parallel window execution

The development checkout provides `haejo parallel` for one to four independent
macOS window jobs. Each job runs through its own signed launcher and helper
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
passed postcondition. Esc stops runs whose helper connection already exists;
it does not stop jobs still waiting to connect. Use **all-run stop or Ctrl-C**
to stop the entire batch, including those waiting jobs. Individual run stops
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

## Tasks

A `parallel` run bound to a [task](tasks.md) (`--task` or `HAEJO_TASK`) passes
its already-validated task ID and its own invocation ID to every job's session,
so each job is recorded in the same task as a child invocation. An unbound
parent never forwards a raw inherited `HAEJO_TASK`.

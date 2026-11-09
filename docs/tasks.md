# Goal-scoped tasks

`haejo task` groups every Haejo invocation that an agent makes for one user
goal. The agent starts a task first, binds every following call to it, and ends
it with a declared result. Agent usage: [skill reference](../skill/references/task.md).

## Model

- A task is file-backed metadata under the product directory
  (`~/Library/Application Support/Haejo/Tasks/<task-id>/` on macOS): `task.json`
  (id, goal, state, result, timestamps) and `events.jsonl` (one start/end record
  per bound invocation, plus one `invocation_flow` record per flow it ran). Directories are 0700, files 0600, owner-checked and
  never followed through symlinks. Task IDs are `t-` + 24 hex digits and are
  validated before any path is built.
- No daemon, lease or authorization. Helper connections, approvals, foreground
  scope and KeepAwake remain per invocation; an open task holds nothing.
- Binding: `--task <id>` (wins) or `HAEJO_TASK`. Resolved in `cli.main` before
  the access receipt, driver, helper or KeepAwake. An invalid, unknown or ended
  task exits 2 with `effect: not_started` and no screen access. `haejo task …`
  itself is exempt so a closed inherited task can still be inspected or ended.
  Non-screen commands ignore an ambient `HAEJO_TASK` and refuse an explicit
  `--task` (`task_not_applicable`). Nested dispatch keeps the outer invocation.
- Admission: `invocation_start` is appended under a short exclusive lock on the
  task after re-checking that it is open, so `task end` and a new call cannot
  race. A failed admission write refuses the call. The lock is never held
  across UI work.
- Records are content-free like [access receipts](access-logging.md): command,
  invocation UUID, pid, parent invocation (for child invocations), access-receipt
  filename, target bundle IDs, exit code, closed error/stage codes, elapsed
  time, and the flows each invocation ran. Free text written by the agent stays
  in the task directory only: the goal sentence and optional `detail`
  (`task.json`), a one-line `why` on an `invocation_start` record (`--why`), and
  `note` records (`haejo task note`, `task end --note`). Access receipts stay
  content-free. Limits: goal 1000, detail 4000 (multi-line), why 500 (one line),
  note 1000 characters; control characters other than tab/newline are refused.
  `task describe` sets the description of an open task; notes are append-only
  and also accepted after the task ends (a closing summary). When a task starts
  without a description, or ends without notes, a `HAEJO_TASK_HINT` line after
  the marker names the command that adds what is missing.
- The Haejo app's **실행 기록** tab groups access receipts by their
  `command_start.task_id`: one row per task (goal, 진행 중/완료/실패/중단, call
  count, apps), whose detail shows the request description, then the latest 30
  calls newest first with their `--why` reason and steps, interleaved by time with
  decision notes (`판단 · …`). The reason is matched via the receipt's
  `command_start.invocation_id`. Calls made
  outside a task stay one row each. A receipt whose task directory is gone shows
  as `작업 t-…` with "기록만 있음".
  Task records are written whenever a call is bound, independent of the access
  logging setting; the access receipt's `command_start` carries `task_id` and
  `invocation_id` when logging is on.
- Flows: `flow.replay()` notes `flow.name` for the current invocation, so
  `do`, `run`, `replay`, `session` and `batch` are covered without per-command
  code (`parallel` children are separate invocations; the legacy in-process
  `run_parallel` notes on the caller thread). Source is `builtin` (a library
  builder), `library` (a saved flow file), `file` (`haejo run <path>`, noted
  after argument checks, so a refused run notes nothing) or `inline`. The name
  is copied only for `builtin`/`library` recipes (ASCII label, `base:recovery`
  for a recovery of one); `file` and `inline` flows — whose names a model or a
  file author chose and may echo the request — get `ref`, the first 12 hex of
  SHA-256 of the name, so repeats line up without copying it. At most 16 per
  invocation, first note per name wins. Recording a flow never fails the run.
- `task status --steps` adds each invocation's step receipts: `access_end` and
  `task_result` rows of the access receipt named in the task record, read only
  when its `command_start` carries the same invocation ID (otherwise
  `access_log_mismatch`; deleted receipts are `access_log_removed`). Only the
  receipt's closed fields are shown (operation, target, action, type, outcome,
  status, error, stage, elapsed). With access logging off there are no steps.
- Status derives `ok`/`failed` from end records. A start without an end is
  `in_flight` while its pid is alive, otherwise `uncertain`; neither is evidence
  of success or permission to resend input. Partial trailing records are
  counted as `damaged_records`.
- `task end --result done|failed|abandoned` is caller-declared, not a
  verification. It closes admission; invocations already admitted finish and
  record their end. Tasks do not expire automatically.

## Not in v1

- No task-wide dispatch journal: `--journal-dir` keeps its per-run semantics
  (its reservations restart at sequence 0 per invocation, so a shared default
  would refuse independent calls).
- `--trace`/`--receipt` paths are not relocated into the task directory.
- No task grouping in the app's history window and no goal text in the banner.

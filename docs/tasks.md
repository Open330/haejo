# Goal-scoped tasks

`tacto task` groups every Tacto invocation that an agent makes for one user
goal. The agent starts a task first, binds every following call to it, and ends
it with a declared result. Agent usage: [skill reference](../skill/references/task.md).

## Model

- A task is file-backed metadata under the product directory
  (`~/Library/Application Support/Tacto/Tasks/<task-id>/` on macOS): `task.json`
  (id, goal, state, result, timestamps) and `events.jsonl` (one start/end record
  per bound invocation). Directories are 0700, files 0600, owner-checked and
  never followed through symlinks. Task IDs are `t-` + 24 hex digits and are
  validated before any path is built.
- No daemon, lease or authorization. Helper connections, approvals, foreground
  scope and KeepAwake remain per invocation; an open task holds nothing.
- Binding: `--task <id>` (wins) or `TACTO_TASK`. Resolved in `cli.main` before
  the access receipt, driver, helper or KeepAwake. An invalid, unknown or ended
  task exits 2 with `effect: not_started` and no screen access. `tacto task …`
  itself is exempt so a closed inherited task can still be inspected or ended.
  Non-screen commands ignore an ambient `TACTO_TASK` and refuse an explicit
  `--task` (`task_not_applicable`). Nested dispatch keeps the outer invocation.
- Admission: `invocation_start` is appended under a short exclusive lock on the
  task after re-checking that it is open, so `task end` and a new call cannot
  race. A failed admission write refuses the call. The lock is never held
  across UI work.
- Records are content-free like [access receipts](access-logging.md): command,
  invocation UUID, pid, parent invocation (for child invocations), access-receipt
  filename, target bundle IDs, exit code, closed error/stage codes and elapsed
  time. The goal sentence is the only free text and stays in `task.json`.
  Task records are written whenever a call is bound, independent of the access
  logging setting; the access receipt's `command_start` carries `task_id` and
  `invocation_id` when logging is on.
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

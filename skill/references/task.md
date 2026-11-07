# Task: one goal, every call grouped

A task groups every Tacto invocation made for one user goal so the run can be
followed and reviewed as a unit.

```sh
tacto task start "계산기로 12×34 계산" --json
# {"type":"task","task_id":"t-…","state":"open"}
TACTO_TASK=t-… tacto observe com.apple.calculator --helper
TACTO_TASK=t-… tacto session com.apple.calculator --helper --guide
tacto task status t-…            # ordered calls, targets, outcome codes, timing
tacto task end t-… --result done # done | failed | abandoned
```

- Bound commands: every screen command (`doctor`, `apps`, `windows`, `launch`,
  `activate`, `open-url`, `keep-awake`, `first-run`, `observe`, `session`,
  `batch`, `capture`, `drag`, `resize`, `hover`,
  `document-attachments`, `run`, `replay`, `do`, `web-upload`, `auth`).
- `--task <id>` takes precedence over `TACTO_TASK`. Recipe commands (`list`,
  `show`, `compile`, …) need no task.
- Each call still opens and releases its own helper connection, approval and
  keep-awake; the task carries grouping only.
- `status` states: `ok`, `failed` (with a closed error/stage code), `in_flight`
  (still running), `uncertain` (no end record and the process is gone — read the
  target's current state before any retry).
- `task end` records the caller's declared result; verify the requested result
  on screen before declaring `done`. An ended task accepts no new calls; start a
  new task for new work. Calls already running finish and are recorded.
- Refusals before any screen access: `task_invalid`, `task_unknown`,
  `task_closed`, `task_storage_unavailable`, `task_not_applicable`.

# Task: one goal, every call grouped

A task groups every Tacto invocation made for one user goal so the run can be
followed and reviewed as a unit.

```sh
tacto session com.apple.calculator --helper --guide --task new --goal "계산기로 12×34 계산" \
  --detail "사용자 요청: 계산기 앱으로 12×34를 계산해 결과를 알려 줘" --why "계산기 화면 확인" --finish-task
# TACTO_TASK {"id":"t-…"} precedes the observation; send the Flow on this session.
# For multiple UI commands, omit --finish-task on the first, reuse --task t-…,
# and put --finish-task on the final command.
tacto task status t-… --steps  # ordered calls, flows, receipts and outcomes
```

`TACTO_TASK=<id>` also binds a call; `TACTO_TASK=new --goal "<goal>"` starts one.
Lifecycle markers go to stderr for `--json` commands, preserving stdout JSON.
`--finish-task` closes the group after recording the final invocation. Exit 0
records `done`; errors record `failed` without changing the command's exit code.
For a single pinned-document edit, verified requested text can record `done`
with `completion_scope=visible_document_text` while the Flow remains unverified;
this does not confirm Save or dispatch. A requested Flow save or remaining steps
prevent that exception. If the invocation journal cannot be written, closure is
uncertain and the group stays open. Status retains each invocation's outcome.

Prose for people reviewing the run (shown in `task status` and the Tacto app's
실행 기록 view, in time order with the calls):

- `--detail "<text>"` with `--goal` (or `task start "<goal>" --detail …`): the
  user's request and context, up to 4000 characters, several lines allowed.
- `--why "<reason>"` on any bound command: one line (≤500) saying why this call
  is made, e.g. "저장 대화상자가 떴는지 확인".
- `tacto task note [<id>] "<decision>"`: a decision and its reason (≤1000), e.g.
  "검색 결과가 0건이라 필터를 해제하고 다시 시도". `task end … --note "<summary>"`
  records the closing summary. Notes are accepted while the task is open.
- Write decisions and outcomes; field values such as passwords and codes stay
  out of this prose.

Manual controls remain available for inspection or interrupted work:
`tacto task start "<goal>" --json`, `tacto task end <id> --result done|failed|abandoned`.

- Bound commands: every screen command (`doctor`, `apps`, `windows`, `launch`,
  `activate`, `open-url`, `keep-awake`, `first-run`, `observe`, `session`,
  `batch`, `capture`, `drag`, `resize`, `hover`,
  `document-attachments`, `run`, `replay`, `do`, `web-upload`, `auth`).
- `--task <id>` takes precedence over `TACTO_TASK`. Recipe commands (`list`,
  `show`, `compile`, …) need no task.
- Each call still opens and releases its own helper connection, approval and
  keep-awake; the task carries grouping only.
- Each call lists the flows it ran as `flow=<name>[source]`; source is
  `builtin`, `library` (`tacto flows`), `file` (`tacto run <file>`) or `inline`
  (compiled, learned or walked in that call). `file`/`inline` flows show
  `flow=#<ref>` (a hash of the name) instead of the name. Child calls of `parallel` are
  marked `(child)` and carry their own flows.
- `status` states: `ok`, `failed` (with a closed error/stage code), `in_flight`
  (still running), `uncertain` (no end record and the process is gone — read the
  target's current state before any retry).
- `task end` records the caller's declared result; verify the requested result
  on screen before declaring `done`. An ended task accepts no new calls; start a
  new task for new work. Calls already running finish and are recorded.
- Refusals before any screen access: `task_invalid`, `task_unknown`,
  `task_closed`, `task_storage_unavailable`, `task_not_applicable`.

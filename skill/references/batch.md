# Repeat one saved Flow

`haejo batch <saved name | /absolute/template.json> --helper --max-jobs 10`
keeps one signed connection for a bounded batch; a saved name is the recipe
`haejo replay <name>` would run. Separate commands each open a new signed
connection: five runs of `calc_12x34` took 5.0 s as five replays and 2.0 s as
one batch (0.27 s per job after the first). It does not load the authoring guide or send
full Flow JSON each time. For interactive tools use tty:true; wait for
`HAEJO_BATCH_READY`, then send `{"params":{"amount":"17","result":"85"}}` plus
a newline with write_stdin. All values are text; defaults fill omitted params.
For interactive/dependent work, wait for `HAEJO_BATCH_RESULT` with exit:0 before starting the next job. EOF or the
job limit ends the batch. The default limit is10 jobs and idle deadline90s;
`--idle-timeout` allows1..600s. Records are bounded to64KiB.

Each job binds the immutable template and runs the ordinary replay engine with
fresh observations, authorization and completion checks. Each successful result
is separate; it does not authorize the next task. Requests cannot change the
Flow, target, contracts or checks. Interactive approval is not accepted. Model selection is disabled unless
`--auto-repair codex` or `--auto-repair claude` is explicitly enabled. Use run for document scope, approval, judgment or a dispatch journal.

A Flow with `"window": {"url": "...", "title": "...", "newest": true}` (saved by
`session --window-match ... --save`) runs each job in the window that selector
names at that job's start, on a fresh connection per job; use it when every
item opens its own popup. Each Flow runs in one window: a step that opens the
popup belongs to an app-wide Flow, and the work inside the popup to a Flow with
`"window"`.

Without automatic repair, failure stops the batch. Unknown completion, invalid
input or observed activation always stops it. Inspect state before deciding what to do next; do not resend completed
or uncertain jobs. This is connection reuse, not automatic journal resume or
exactly-once delivery. Pass --timings only when diagnosing timing; normal output
is completion/result markers, not repeated full observations.


When all parameter rows and transitions are already known, use one JSONL file
or deterministic caller instead of involving the model for every row:

```sh
haejo batch /absolute/template.json --helper --max-jobs 10 < /absolute/jobs.jsonl
```

Buffered requests are processed in order and stop at the first failure. Read
result markers to distinguish completed jobs from the stopped job; do not
restart the file after a failure. The Flow itself must prepare each new task.
Batch does not reset application state or synthesize a resume checkpoint.

After an action passes its result predicate, the next job still reads a fresh
tree but avoids repeating the helper's fixed post-action settle delay. Without
that verification, the ordinary delay remains. Observations are never reused.

For selector drift, opt in to `--repair-packet /absolute/new-packet.json`.
A stopped job's result points to the narrow packet; completed jobs do not
write it. Read `selector-repair.md` only at this failure. The batch closes at
failure; queued jobs never run. Keep the request rows outside model context
and use result ordinals to track which jobs completed.

For automatic intervention use:

```sh
haejo batch /absolute/template.json --helper --auto-repair codex < /absolute/jobs.jsonl
```

Read [automatic repair](auto-repair.md) only when enabling this mode. Successful
jobs use no model. A missing/ambiguous selector may invoke a text-only agent,
verify a stable checkpoint and replay only the failed suffix. The repaired
selector is reused for later jobs in this batch. The original file is unchanged.

A template can include `{"action":"wait_until","until":{"contains":"ready"},"timeout_s":1200}`
for a long transition inside each job. Polling defaults to every 10 seconds and
the active timeout allows up to 7200 seconds. Unavailable screens pause the
deadline and contribute to the step's `paused_seconds` and `pauses` diagnostics.
`--idle-timeout` measures the wait for a request line, so a running wait step
can outlast it. After the job, the next request receives a fresh idle deadline.
See [wait details](../../docs/flow-wait-until.md).

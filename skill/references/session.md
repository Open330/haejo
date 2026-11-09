# One-flow session

`haejo session <bundle-id> --helper [--document /absolute/path] [--guide] [--timings] [--idle-timeout 1..600]`
observes one app, reads one newline-terminated Flow JSON record from stdin,
replays it on the same signed connection, and exits. The default input wait is
90 seconds. The input record is bounded to 1 MiB. In an interactive terminal,
invalid JSON/schema, target or parameter defaults return a short error and
`HAEJO_SESSION_READY`: send the
corrected JSON on the same session. No input has been dispatched and the guide
and observation are not repeated. Corrections share the original input deadline.
Piped invalid JSON, EOF, cancellation, extra records in the input buffer, or a
changed target end the session.
A failed flow is never rerun by the session.

When `HAEJO_OBSERVATION_MORE` appears, the tree omitted candidates. Before
authoring the Flow, send `{"observe_next":true}` alone on this same session to
read the next page. Each page replaces the previous observation; do not combine
element indices across pages. Up to eight continuation pages share the original
input deadline. No app input occurs. The live cursor stays inside the runtime.
If the marker offers name lookup and the exact label is known, send
`{"find_in_observation":"exact label"}` instead to avoid reading intervening
pages. Lookup and continuation share the eight-request limit and deadline.

For agent tools, start with `exec_command`, `tty: true`, and
`yield_time_ms: 1000`. Wait for both the observation and `HAEJO_SESSION_READY`.
Send a minified JSON line with `write_stdin` using the exact returned session ID.
Use `yield_time_ms: 5000` when sending the flow to collect short replay completion
without an extra status round; if still running, poll the original session.
Never resend the flow to obtain status. Append an actual newline, not the two
literal characters backslash+n.
Use the original session for polling when initial observation takes longer.

The session temporarily disables canonical line limits and input echo on its
own terminal and restores its settings afterward. The initial observation does
not authorize actions. Replay observes again, resolves stable selectors, and
keeps all existing policy, binding and completion checks. Observation IDs are
not exported for use by another invocation; no daemon, shared socket, or
permission change is introduced.

This version accepts deterministic flows only; `decide` and `visual` are
refused. It does not read stdin as approval or accept `--yes`, provider flags
or a restart journal. Use the ordinary `run`/`replay` route for
those workflows. Existing user-intent authorization and host completion
receipts are still evaluated by the normal replay engine. Close or interrupt an
idle session if abandoning the task; it also expires on its input deadline.

If the user already approved a consent/form step, carry that approval through
`run <flow.json> --helper --yes` with the same task ID and current bindings;
do not hand it back solely because this session cannot approve. For a fresh
read without any action, use `observe --helper --json`, not a session with `{}`.


`--guide` returns trusted minimal Flow instructions together with the observation;
no separate authoring reference is needed for ordinary clicks. For compact steps,
`{"click":"<identifier>","equals":"<result>"}` expands before the normal parser.
`skip_equals` expands to skip_if. Checks require an explicit check_defaults.field;
shorthand cannot also specify action/selector or duplicate the corresponding check.
Contracts and checks are not inferred. Full Flow JSON remains supported.

`--timings` also reports monotonic offsets for observation ready, input ready,
flow received, replay done and session done. Input waiting includes model/client
and transport delays; it is not a measure of model inference alone.


Reusable save: read [reuse](reuse.md) only when a saved parameterized template
is needed. `--reuse-guide --save /absolute/new.json` executes once and saves
the unbound template after success; do not replay a completed task to save it.

For an exact TextEdit file, add `--document /absolute/path --guide`. The same
connection pins that file once before printing its scoped observation. All later
observations use the same native token; a lost/changed token ends the flow without
repinning or reading the rest of the app. The guide includes the text selector
and edit/read schema; implementation history is not needed for ordinary edits.
Text verification is not Save evidence. Saved Flow files do not store this read
scope: use the `HAEJO_FLOW_SCOPE` replay argv with `--document` on each invocation.


After `commit_unverified` for a pinned TextEdit body edit, the session may emit
`HAEJO_DOCUMENT_STATE`: one read on the same native token, no model call or input
retry. `matches_requested_text:true` means the authored text is currently visible;
`remaining_steps:0` means this failed step was last. For that visible-text task,
no extra read session is needed. False/null requires inspection, and remaining
steps are unfinished work. The result does not attribute the write, verify Save,
change the failed Flow's status, or save an unverified template. Existing text
could already match. Raw text and document tokens are not included in the marker.


With `--steps`, send `{"steps":[...]}` to omit the Flow header. The session fills
schema/name/target. Calculator supplies the concrete defaults shown by its guide;
a pinned TextEdit session supplies document selectors and read defaults. Other
apps require explicit step selectors, contracts and result fields. Checks and
write evidence remain explicit. A full Flow remains valid; use it for named
parameters, tables, other schemas or custom defaults. `--reuse-guide` keeps the
full template. Saved files expand the selected defaults into a complete Flow.

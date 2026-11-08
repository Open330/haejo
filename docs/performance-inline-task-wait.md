# Inline task lifecycle and document polling

The first UI command can create its audit group with `--task new --goal "..."`.
Reuse the returned `TACTO_TASK` ID on later commands and put `--finish-task` on
the final command. A single-command goal can combine these options. This removes
the separate `task start` and `task end` agent/tool round trips while retaining
the per-invocation journal. Manual lifecycle commands remain available.

Lifecycle markers use stderr when the UI command requests `--json`, preserving
the command's stdout JSON. The final invocation is recorded before task closure;
a missing journal record leaves closure uncertain. A failed command closes the
group as failed. The existing narrow, same-document visible-text witness can
close a single edit as done with `completion_scope=visible_document_text`, while
preserving the Flow's unverified exit code and receipt. It does not confirm Save,
and this exception is disabled when a Flow save was requested.

`DocumentScopedDriver.wait_until` now passes `_settle_after_action=False`, as the
underlying helper's own polling loop already did. Each predicate still receives
a fresh observation scoped to the same document token. Polling timeout and
changed-document refusal remain in place.

## Measurement, 2026-11-08

Five alternating before/after pairs isolated the actual host settle sleep using
`HelperDriver.observe`, a deterministic mocked transport and the document scope
wrapper. The before arm uses the prior wrapper call; the after arm uses the
patched `wait_until`. The action timestamp was reset immediately before each
sample; monotonic time and sleep were real. Every sample issued one observation
with the same document token.

| Isolated host segment | Median |
| --- | ---: |
| Prior document polling | 1.005707 s |
| Patched document polling | 0.000107 s |

This measures removal of the fixed sleep immediately after an action. It is not
an application end-to-end benchmark, a model latency result, or a comparison
against Sky. A task with two UI commands now needs two UI command launches
instead of those launches plus two separate lifecycle command launches. The
saved agent planning/transport time depends on the host and model.

Evidence: `reviews/perf-inline-task-evidence-20261108/measure_settle.py` and
`settle.json` (local artifacts). Focused regression tests cover lifecycle
creation/closure, JSON output, admission and journal failures, visible-text
limits, and pinned polling without fixed settle.

## End-to-end fresh-context comparison

On 2026-11-08, nine independent agent conversations ran the same two-app task:
compute 23 × 19 in Calculator and enter exactly `437` in an evaluator-owned
TextEdit document. The external receiving check and fixture cleanup passed in
all nine runs. Each condition ran three times, with order rotated across rounds.
No task-specific conversation or Flow was reused.

Requested model: `gpt-6.1-sol`, medium reasoning, Codex CLI 0.161.0, 180-second
per-run timeout. Both Tacto conditions used Python 3.11, equal-length runtime
paths and identical signed rc29 native binaries; Python/skill changed from
`a861027` to `8adc961`. Model/config hashes were stable across all cohorts.
Sky used the host-selected bundled Computer Use skill and the same task/model
request. Instructions, tool discovery and the final agent response count in
reported time and tokens; evaluator setup and cleanup do not.

| Metric | Before | After | Sky |
| --- | ---: | ---: | ---: |
| Task successes | 3/3 | 3/3 | 3/3 |
| Elapsed median (s) | 59.3 | 43.1 | 32.7 |
| Total input tokens (3 runs) | 583,233 | 403,388 | 426,741 |
| Input excluding cache reads (3 runs) | 40,897 | 41,276 | 35,957 |
| Output tokens (3 runs) | 2,907 | 2,497 | 1,882 |
| Completed tool items per run | 5, 5, 5 | 3, 3, 3 | 6, 6, 6 |

After versus before: median time -27.3%, total input
-30.8%, output -14.1%, but input
excluding cache reads +0.9%. These results do
not establish lower billed cost. The three paired time changes were
-27.9%, -40.8%, -16.4%.

Document replay/readback median changed from
1.425 s to
0.416 s. Both versions retained one closed
task with two UI invocations in every run; the candidate removed both standalone
lifecycle commands in every run. Its visible-document completion scope preserves
the underlying unverified Flow receipt and does not claim Save.

Sky remained faster by median and used less uncached input and output in this
sample. The candidate's lower total input and fewer tool items do not imply it
is faster or cheaper than Sky.

This is a three-run observational comparison per condition. Actual serving
model, server cache state and billing were not verified. The harness's strict
responsibility/TCC isolation eligibility check did not pass, so observed task
success is kept separate from strict permission-equivalence certification.
The common pinned native runtime isolates the Python/skill changes; this is not
a test of a newly packaged app release. No build or regression suite overlapped
these model measurements.

[Per-trial metrics and limits](benchmarks/2026-11-08-inline-task-comparison.json).
Private raw traces and before/after runtime hashes are retained under
`reviews/perf-inline-task-benchmark-20261108/`.

## Session-bound steps: next bottleneck and measured change

Profiling the previous candidate's three trials found 44.4% of host elapsed time
waiting for Flow authoring/delivery and 48.3% outside command spans. These include
model planning/generation, transport and scheduling; they are not pure inference
or CPU measurements. Replay/readback/close was 2.7%. This directed the next change
at repeated JSON authoring rather than native input checks.

`session --steps` accepts `{"steps":[...]}` and fills the connection's structural
header. Calculator reuses the concrete defaults already offered in its guide;
pinned TextEdit reuses its document selectors and read defaults. Generic apps
receive no inferred selectors/checks/effects. Write effects and evidence remain
explicit. Full Flows and single-edit messages remain compatible. Reusable
parameter/schema guides retain a full template; saved messages expand to complete
Flows. Peer review issues around these guide combinations were resolved, and
114 focused tests passed before measurements.

Twelve new independent conversations ran the same Calculator → TextEdit task,
including one replacement trio. The primary set has three matched trials per
condition with rotated order. Both Tacto conditions already contain
the prior inline task lifecycle and polling fixes; this measures only the next
steps-authoring change (`8adc961` → `f57e455`). They use equal-length paths,
Python 3.11 and identical signed rc29 native executables. Sky uses its bundled
Computer Use skill. All arms request gpt-6.1-sol/medium with a 180-second timeout.
All twelve receiving checks and cleanups passed. A System Settings foreground
transition was observed in baseline cycle 2; its origin was not established.
The whole original trio is retained, excluded from the primary set, and replaced
with a fresh trio (matched cycles 0, 1, 3). No foreground changes occurred in
the nine primary trials. Token sums below cover the matched set; campaign totals
and all original rows remain in the linked JSON, not erased.

| Metric | Before | Bound steps | Sky |
| --- | ---: | ---: | ---: |
| Elapsed median (s) | 44.0 | 33.0 | 31.3 |
| Input tokens, three-run sum | 397,664 | 344,054 | 431,204 |
| Input excluding cache reads, sum | 38,880 | 24,950 | 46,180 |
| Output tokens, sum | 2,547 | 2,073 | 1,869 |

Median elapsed change: -25.0%; total input
-13.5%; input excluding cache reads
-35.8%; output -18.6%.
Individual paired elapsed changes were
-25.9%, -13.1%, -33.6%.

Calculator submitted JSON byte median (including corrections, if any) fell from
746 to
406 UTF-8 bytes; authoring/delivery
wait median changed from 10.577
to 4.457 seconds. Both versions
recorded three completed tool items per run and one closed task containing two
UI invocations. Visible-text completion does not certify Save or convert the
unverified underlying write receipt into a verified dispatch.

Sky's observed median remains lower. Three samples, varying server cache/load,
and unverified serving model/billing do not establish universal speed or billed
cost savings. Strict responsibility/TCC isolation eligibility did not pass;
observed task success is reported separately. No build or regression suite ran
during these model cohorts. This is an isolated Python/skill experiment with
common native binaries, not a newly packaged app release test.

[Per-trial metrics and remaining time partition](benchmarks/2026-11-08-bound-steps-comparison.json).
Private traces and frozen-source hashes:
`reviews/perf-session-binding-evidence-20261108/`.

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

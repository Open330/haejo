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
| Prior document polling | 1.005090 s |
| Patched document polling | 0.000027 s |

This measures removal of the fixed sleep immediately after an action. It is not
an application end-to-end benchmark, a model latency result, or a comparison
against Sky. A task with two UI commands now needs two UI command launches
instead of those launches plus two separate lifecycle command launches. The
saved agent planning/transport time depends on the host and model.

Evidence: `reviews/perf-inline-task-evidence-20261108/measure_settle.py` and
`settle.json` (local artifacts). Focused regression tests cover lifecycle
creation/closure, JSON output, admission and journal failures, visible-text
limits, and pinned polling without fixed settle.

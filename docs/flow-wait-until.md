# Waiting for a screen condition

A `wait_until` step keeps a Flow on the same connection while a result takes
minutes to arrive. It works in `haejo session`, saved Flow files run with
`haejo run`, and each job of `haejo batch`.

```json
{
  "schema": 2,
  "name": "chapter-completion",
  "target": "com.apple.Safari",
  "steps": [
    {
      "action": "wait_until",
      "until": {"contains": "본 차시의 학습이 종료되었습니다."},
      "timeout_s": 1200,
      "poll_s": 10
    }
  ]
}
```

`timeout_s` is a positive number up to 7200 seconds of available-screen time.
`poll_s` defaults to 10 seconds and accepts 1–60 seconds. The first check runs
immediately. Each poll reads a fresh, capped accessibility observation; it uses
no model calls, screenshots, clicks or keyboard input. Local lock and display
sleep checks run before the accessibility read, so a locked or sleeping display
does not repeatedly trigger tree walks.

`until` uses the same fields as a postcondition: `contains`, `equals`, `field`,
`attribute`, `absent`, `absent_role` and `all_of`. A particular element's presence
is expressed with `{"field":{"identifier":"completion-alert"},"exists":true}`.
The field uses the usual stable selector and unique-match rules. Checks can use
Flow parameters and earlier captures, for example `{"contains":"{{message}}"}`.
`check_defaults` also applies to `until`. Compound checks serialize with schema 3.
The step has read effects; its JSON can omit `safety`, or supply a read contract.

The deadline pauses when the local macOS session is locked, all online displays
are asleep, or an observation reports that the window is offscreen/on another
Space. Counting resumes at the first readable poll. Detection is sampled at the
poll interval. The existing `window_offscreen` diagnosis also covers an
ordered-out or closed window, so that state pauses until a readable window
returns. The wait itself keeps the current scope and does not select another
window or change Spaces. A process interrupt still ends the wait normally.
Session and batch idle timeouts measure waiting for the next stdin message;
they do not run while a Flow step is executing.

The step's replay log includes `polls`, `active_seconds`, `elapsed_seconds`,
`paused_seconds` and `pauses` (total seconds grouped by reason). A condition
that remains false through its active timeout records
`{"status":"error","error":"wait_timeout","effect":"none"}` with those timings.
Other observation failures record `wait_observation_failed` with the backend's
diagnostic. Unreadable observations are never tested as empty trees. A wait can
remain paused beyond 7200 wall-clock seconds; the limit applies to active time.

An existing session can pause during replay. Opening a new interactive session
still performs its normal first observation before accepting the Flow, so it
starts from a readable screen. A saved Flow whose first step is `wait_until`
can start waiting while the screen is already unavailable. Remote/browser
targets use their own observation diagnoses rather than the local macOS lock.

The returned match is a fresh observation for the next Flow step. A successful
wait confirms the visible condition; for example, a course completion alert is
evidence of that alert, with the meaning defined by the authored Flow.

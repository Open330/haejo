# Menu approval for confirm steps (opt-in)

**설정 > 메뉴 승인** turns this on; it is off by default. When off, every
command behaves exactly as before (`--yes`, the terminal question, and the
non-terminal refusal are unchanged, and the CLI never opens the menu socket).

## What changes when it is on

Steps the policy classifies as `confirm` (payment, sending, deletion and the
other consequential effects) are decided in the Haejo menu app instead of by
`--yes` or a terminal answer:

- Before a `run`/`replay` starts, all of its confirm steps appear on one card.
  Values settled during the run (a decided message, a credential field) get a
  card of their own when they are known.
- The card offers **이번만 허용**, **이 작업 동안 허용(1시간)**, **항상 허용** and
  **거절**. A grant matches only the same app (bundle id and the signing team
  the menu app reads itself), effects, recipient and object type. A task grant
  also belongs to the task that asked (`HAEJO_TASK`); other tasks get their own
  card, and a run without a task is not offered one. Payments, transfers and
  credential entry (including a field found to be a password during the run)
  are confirmed every time; an irreversible deletion has no "always" choice. **항상 허용 모두 지우기** in settings clears
  stored grants.
- A request already covered by a grant runs at once, with no card.
- If the card is not answered within 45 seconds the command prints
  `{"type":"approval_pending","approval_id":"ap_…","effect":"not_started","resume":"--approval ap_…"}`
  and exits 4. Running the same command with `--approval ap_…` continues once
  the card is answered. One approval runs one command: before the first input
  the approval is claimed for that run, each step is spent once, and a second
  command with the same id ends with `approval_claimed` without touching the
  screen. `approval_claimed` means another run holds the approval; read that
  run's result rather than starting a new one. A resumed command must be the
  same request: steps, contracts, recipients, payloads, app, window and task. Answering after the timeout does not start anything by itself.
- During a run, a refused, expired or unanswered card (10 minutes) or a menu
  app that is not running stops only that step. Earlier steps are reported as
  done; the step's gate is `approval_denied`, `approval_timeout` or
  `approval_unavailable`, with `action_effect` set to `not_started`. A grant
  cleared in the menu while a run is going stops its next step, which is then
  not sent as approved.
- With the setting on and the menu app not running, the command reports
  `approval_unavailable`; it does not fall back to `--yes`.

`preapproved` steps (a consistent save the request itself names) run as before
and never reach the menu. `session` and `batch` keep having no approver.

## Coverage

This replaces the CLI's own yes for confirm steps on the `run`, `replay` and
`do` paths (`do` uses the same plan card, claim and `--approval` resume). The decision is made only in the menu app: its socket
(`~/Library/Application Support/Haejo/approval.sock`, mode 0600, same-user
peers only) can ask, claim and spend approvals but has no operation that
decides one. It does not cover a caller that edits Haejo's own files or that
drives the screen without Haejo; the helper stage below covers that case. The task a grant belongs to is the caller's
`HAEJO_TASK`; it separates ordinary tasks from each other, and its
authenticity is not verified at this stage. The app's signing team is read by
the menu app from the running copies (or, with none running, the copy
LaunchServices opens); when copies from different teams are running, or the
target is not a bundle id, only **이번만 허용** and **거절** are offered.

## Helper stage

Turning **메뉴에서 승인** on in the menu app's own window also turns on the
decision inside the signed Haejo Helper. The switch is the only way to turn it
on or off; editing `preferences.json` changes neither.

- Every input the helper is about to post is classified from what the helper
  reads on the screen (the button, the default button for Return, a secure
  text field, a menu item or popup option), not from the flow's declarations.
  Sending, payment, deletion and credential entry get one card in the menu app,
  built from what the helper read: the app, the window, the recipient, the
  first line of the body, the selected items, the amount and the site. Parts
  it could not read are named on the card.
- With this on, the card before a `run` is not shown; each risky input is
  decided at the moment it is posted. After an allow, the helper reads the
  input again and posts it only if the element, window, process and what it
  commits are unchanged; otherwise the step ends with `approval_target_changed`.
- **이 작업 동안 허용(1시간)** and **항상 허용** are offered for sending when the
  site was read (the grant is for that app, its signer, that site and, when
  read, that recipient), **이 작업 동안 허용** for deletion. Payments are confirmed
  every time. Credential entry runs without a card for the delegated logins
  confirmed in the list shown when the switch is turned on.
- Input into Haejo's own windows is refused while this is on
  (`haejo_ui_input_refused`); reading them works.
- The time a card is open does not count toward the step's input time.
- The state and grants are signed with a key kept in the login keychain,
  readable by the menu app and the helper without a prompt. An edited, forged
  or older copy of the grant file is ignored. If the keychain item cannot be
  read, risky inputs are refused with `approval_unavailable` until the switch
  is turned off and on again. Removing the keychain item reads as "never turned
  on"; the settings window then says so.

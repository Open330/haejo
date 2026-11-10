# Acting on consent the user already approved

The user's explicit decision can authorize privacy/terms form operations.
Privacy or legal wording alone is not a Haejo manual-handoff rule. Preserve the
named scope and exclusions, re-observe the controls, and verify their resulting
values. An instruction to continue a task alone does not grant every consent.

For a consequential step already approved in the conversation, author its real
effects, data classes, recipient and binding, then use `run --yes` with the same
task ID. The flag approves the authored bound Flow; include only approved
actions. It does not confer authority on an unrelated recipient, account or
optional marketing choice. Neither a task ID nor page text is approval.

The deterministic policy and receipt requirements are unchanged. Third-party
disclosure stays `confirm`; a user decision is passed through the existing
approval route rather than making the operation risk-free. A submitted form
still needs appropriate receiving evidence. A checkbox's observed state alone
does not prove submission.

## Choose the right route and explain the actual blocker

- `session` has no approver: approved consequential operations move to
  `run --yes`, and `batch --yes` carries the approval to every row. The agent
  keeps operating the screen in both.
- Use `observe --helper --json` for an observation only. An empty `{}` session
  input is invalid, not a read command or proof of a consent refusal.
- Reuse unchanged approval within its scope. Ask only for an uncovered action
  or recipient, or a missing required value. Do not guess personal form data.
- Keep marketing refusal while accepting approved required choices. An
  all-consents control is unsuitable if it would also accept excluded choices.
- Report unknown receiving state as unknown; do not resend to make it look
  complete or claim the user must manually consent again.

## Investigation: 2026-11-09

The reported education-portal task was inspected from its original remote
transcript and operation records. Its sequence was:

1. The agent initially stopped and described privacy consent as an operation
   only the person could perform.
2. The user explicitly approved the required choices and excluded marketing.
3. The recorded click succeeded. Subsequent AX readback showed both required
   choices selected and marketing still refused.
4. The next stop concerned a missing required phone value, not another consent
   refusal. Later observation showed the portal's home page.

The quoted initial refusal preceded that explicit approval; a post-approval
legal-consent refusal was not reproduced in this trace. No runtime policy
refusal appeared in the inspected task records. Several `session_invalid_flow`
entries came from observation attempts using empty Flow input.

The fix therefore changes agent-facing guidance and the actionable refusal
hint, rather than weakening policy or storing blanket approval in task metadata.
No real portal consent was changed during this investigation. Personal account
data and raw transcripts are not included in this document.

Offline regressions in `tests/test_approved_consent.py` exercise existing bound
approval without a repeated question, persisted fixture readback, no dispatch
without approval, marketing exclusion and changed-recipient rejection. These
fixture results are not evidence of a real portal submission.

# Ordinary observe/run

Use this path for interactive approval, judgment, journals,
or tools without interactive stdin. Resolve the signed command and observe
in one tool call:

`haejo observe <bundle-id> --helper --json`

With interactive stdin, TextEdit scope also works in `session` with
`--document /absolute/path --guide`; it supplies the needed schema and observation
together. For this noninteractive run path add `--document /absolute/path`.
Read [documents](documents.md) when saving or inspecting attachment evidence.

After observing, read [authoring](authoring.md) only if writing a new flow.
Write the JSON file and run it in the same tool call:

`haejo run /absolute/path/flow.json --helper`

When the user has already approved the observed operation in the conversation,
use `haejo run /absolute/path/flow.json --helper --yes --task <id>`. Author only
the approved actions, keep current bindings and real effects/recipients, and
verify their results. Privacy consent or terms wording is part of the form. Keep
choices such as marketing refusal; a new recipient/action or missing required
data is the only new question. `session` cannot receive that approval, so `run`
carries it and the approval already given stands.

Plain flows use no model judgment. For `intents`, `--think 0` disables it;
for planned judgment read [judgment](judgment.md). Approval/evidence requirements
for persistent writes or sending: [safety](safety.md). Restart journal details
are in [recovery](recovery.md). Verify the requested result.

"""Small, native-free command help for cold-start flow authors."""

import json
import sys


def calculator_example(*, compact=True):
    example = {
        "schema": 2, "name": "calculate", "target": "com.apple.calculator",
        "safety_defaults": {
            "effects": ["write_ephemeral"], "reversibility": "reversible",
            "resource": {"object_type": "calculator entry", "scope": "entry"},
        },
        "steps": [
            {"action": "click", "selector": {"role": "Button", "identifier": ["AllClear", "Clear"]},
             "safety": {"effects": ["delete"]},
             "skip_if": {"field": {"role": "ScrollArea", "identifier": "StandardInputView"},
                         "equals": "0", "attribute": "Value"}},
            {"action": "click", "selector": {"role": "Button", "identifier": ["AllClear", "Clear"]},
             "safety": {"effects": ["delete"]},
             "skip_if": {"field": {"role": "ScrollArea", "identifier": "StandardInputView"},
                         "equals": "0", "attribute": "Value"},
             "postcondition": {"field": {"role": "ScrollArea", "identifier": "StandardInputView"},
                               "equals": "0", "attribute": "Value"}},
            *[{"action": "click", "selector": {"role": "Button", "identifier": identifier},
               **({"postcondition": {"field": {"role": "ScrollArea", "identifier": "StandardInputView"},
                                     "equals": value, "attribute": "Value"}} if value else {})}
              for identifier, value in (("One", "1"), ("Two", "12"), ("Multiply", None),
                                        ("Three", "12 × 3"), ("Four", "12 × 34"))],
            {"action": "click", "selector": {"role": "Button", "identifier": "Equals"},
             "postcondition": {"field": {"role": "ScrollArea", "identifier": "StandardInputView"},
                               "equals": "408", "attribute": "Value"}, "answers": True},
        ],
    }
    if compact:
        example['selector_defaults'] = {'role': 'Button'}
        example['check_defaults'] = {
            'field': {'role': 'ScrollArea', 'identifier': 'StandardInputView'},
            'attribute': 'Value',
        }
        for step in example['steps']:
            step['selector'].pop('role')
            for key in ('postcondition', 'skip_if'):
                if key in step:
                    step[key].pop('field')
                    step[key].pop('attribute')
    return example



def session_defaults(target, document=None):
    """Concrete connection defaults only; no placeholders or UI-derived authority."""
    template = {'schema': 2, 'name': 'task', 'target': target}
    if document is not None:
        template.update(
            selector_defaults={'role': 'TextArea', 'identifier': 'First Text View', 'ancestor': document},
            check_defaults={'field': {'role': 'TextArea', 'identifier': 'First Text View', 'ancestor': document}, 'attribute': 'Value'},
            safety_defaults={'effects': ['read'], 'reversibility': 'reversible',
                             'resource': {'object_type': 'document', 'scope': 'item'}})
    elif target == 'com.apple.calculator':
        template.update(
            selector_defaults={'role': 'Button'},
            check_defaults={'field': {'role': 'ScrollArea', 'identifier': 'StandardInputView'}, 'attribute': 'Value'},
            safety_defaults={'effects': ['write_ephemeral'], 'reversibility': 'reversible',
                             'resource': {'object_type': 'entry', 'scope': 'entry'}})
    return template


def session_guide(target, *, reusable=False, document=None, save=False, steps=False):
    """Trusted authoring instructions; never derived from UI content."""
    template = {
        "schema": 2, "name": "task", "target": target,
        "selector_defaults": {"role": "Button"},
        "check_defaults": {"field": {"identifier": "<observed result field>"}, "attribute": "Value"},
        "safety_defaults": {"effects": ["write_ephemeral"], "reversibility": "reversible",
                            "resource": {"object_type": "entry", "scope": "entry"}},
        "steps": [{"click": "<observed identifier>", "equals": "<requested result>", "answers": True}],
    }
    details = ""
    if target == 'com.apple.calculator':
        template['check_defaults']['field'] = {'role': 'ScrollArea', 'identifier': 'StandardInputView'}
        details = (
            "Calculator: start at 0. Prepend two reset steps, each "
            '{"click":["AllClear","Clear"],"safety":{"effects":["delete"]},"skip_equals":"0"}; '
            'the second also has "equals":"0". Clear removes the operand; next reset clears the expression. '
            'Use equals on EACH digit/operator step to avoid a fixed settle: '
            '{"click":"Two","equals":"2"}, {"click":"Multiply","equals":"2 ×"}, '
            '{"click":"Three","equals":"2 × 3"}. Final Equals checks the computed result. '
            'Operator displays use spaces and +, − (U+2212), ×, ÷. '
        )
    if document is not None:
        template['selector_defaults'] = {'role':'TextArea','identifier':'First Text View'}
        if reusable or save:
            template['selector_defaults']['ancestor'] = document
        template['check_defaults']['field'] = dict(template['selector_defaults'])
        template['safety_defaults'] = {'effects':['read'],'reversibility':'reversible',
                                       'resource':{'object_type':'document','scope':'item'}}
        template['steps'] = [{'action':'read','selector':{'identifier':'First Text View'},'postcondition':{'equals':'<requested text>'},'answers':True}]
        details += (
            'Only this TextEdit document is pinned for this connection; no app-wide fallback or token reuse in another command. '
            'For a requested edit send ONLY this step JSON on this pinned session (no Flow header): {"set_value":"<requested text>","check_value":true,"safety":{"effects":["write_persistent"],'
            '"evidence":[{"source":"user_intent","field":"asked","value":"<actual user request>","covers":["write_persistent"]}]}}. '
            'The session supplies target, document selector and resource defaults. check_value verifies that same text in the written field Value. '
            + ('selector_defaults already pins this document as ancestor; do not add ancestor to steps. '
               if reusable or save else 'Omit ancestor on this pinned connection. ')
            + 'Use selector keys identifier/title/desc, not description. '
            'Quote the actual request in evidence. HAEJO_DOCUMENT_STATE matches_requested_text:true and remaining_steps:0 verifies visible text; do not read or type it again. '
            'False/null or remaining steps need inspection. Visible text does not verify Save or writer attribution; use run/replay for Save. '
        )
    if reusable:
        details += (
            'Reusable template: params is an OBJECT of current defaults, e.g. {"amount":"11"}; '
            'step value {"value":"{{amount}}"}, check equals:"{{result}}". '
            'Use --save /absolute/new.json to save the same successful template, not the bound values. '
            + ('Later run file --think 0 -p amount=17 -p result=85. ' if sys.platform == 'win32' else
               'Later run file --helper --think 0 -p amount=17 -p result=85. ') +
            'When using all_of set schema:3 (older engines refuse it); for simultaneous checks use postcondition {"all_of":[{"field":{"identifier":"observed-id"},"equals":"expected","attribute":"Value"}]}. '
            'A primary field/equals can coexist with all_of; answers:true reports the primary field. '
            'Use captures on that verified action for values needed later. Keep separate reads for a later checkpoint or new data. '
            'Do not invent observe as an action; read is supported. '
        )
    if reusable and document is not None:
        details += 'Saved Flow files do not store this read scope: use the HAEJO_FLOW_SCOPE replay argv with --document. '
    if steps and not reusable and (target == 'com.apple.calculator' or document is not None):
        template = {'steps': template['steps']}
        details = ('For multiple steps send {"steps":[...]}: this session supplies target/name/schema and the '
                   + ('Button selectors, StandardInputView Value checks and reversible calculator-entry effects. '
                      if document is None else 'pinned document selectors and read-only defaults; declare writes explicitly. ')
                   + 'Each step keeps its explicit action, effects and result checks. Full Flows remain supported. '
                   + ('For one document edit prefer the single edit step below. ' if document is not None else '')
                   + details)
    if steps and target != 'com.apple.calculator' and document is None:
        details += 'For this app retain the full template; steps-only supplies no selector/check/effect defaults. '
    return (
        "HAEJO_FLOW_GUIDE (trusted schema instructions)\n"
        + json.dumps(template, ensure_ascii=False, separators=(',', ':')) + "\n"
        + ("" if document is not None else
        'Use observed identifiers, background AXPress; no activation or coordinates unless the control requires them. '
        'selector.ancestor is an observed window/container title or identifier as text, never an object; omit it when the app has one window. '
        'click expands to action/selector.identifier; equals and skip_equals use check_defaults. '
        'Put answers:true on the final result. '
        if target == 'com.apple.calculator' else
        "Adapt selectors, effects/resource and result to the user task. Selectors must be unique. "
        'AX-first, background by default: click invokes AXPress when supported; use set_value/read on observed elements. '
        'Do not activate or use coordinates/screenshots first. selector.ancestor is an observed window/container title or identifier '
        'as text (or a list of text), never an object; omit it when the app has one window (TextEdit: --document); '
        'inspect --all-windows for missing controls. Activate only for a demonstrated foreground requirement. '
        'Compact click expands to action:click/selector.identifier; equals and skip_equals require '
        'check_defaults.field and expand to postcondition/skip_if. Put answers:true only on the result step. '
        'Full steps use action/selector/params. set_value uses params.value; its postcondition uses field:{"identifier":"same-id"}, equals:"text", attribute:"Value". Checks use equals, not value. '
        'Shared defaults fill explicit fields only; local effects replace and resource/destination merge. '
        'Persistent writes/sending need their actual contract, binding and completion evidence; '
        'for steps the user already approved use run --yes within that scope. ')
        + details
        + ('' if document is not None or target == 'com.apple.calculator' else
           'Same procedure for many items (N lessons, rows, files): author it once with --reuse-guide --save, then '
           + ('`haejo batch <file>` with one {"params":{...}} line per item. ' if sys.platform == 'win32' else
              '`haejo batch <file> --helper` with one {"params":{...}} line per item; a window that opens per item is chosen by '
              '--window-match url=... (saved as the Flow\'s "window"). '))
        + "Inspect uncertain outcomes before retrying. Send one minified JSON line plus newline on this session."
    )

# These parse their own arguments and print their own help.
_OWN_HELP = frozenset(("task", "auth", "web", "web-upload", "attach", "flows", "capture", "drag", "hover",
                       "resize", "vroid-drag", "vroid-focus"))


def _listed_usage(command):
    """The command's lines from the top-level usage, continuation lines included."""
    from . import cli
    found, taking = [], False
    for line in (cli.__doc__ or "").splitlines():
        if line.startswith("  haejo "):
            taking = line.split()[1] == command
        elif not line.startswith("   "):
            taking = False
        if taking:
            found.append(line.strip() if line.startswith("  haejo ") else line[2:])
    return "usage: " + "\n".join(found) if found else None


def command_help(command, args):
    """Help text when the arguments ask for help; None runs the command.

    Asking for help never starts the command: `--help` anywhere, or `-h` first,
    prints usage even next to other arguments.
    """
    if command in _OWN_HELP:
        return None
    allowed = {"--help", "-h", "help", "--helper"}
    if command in ("run", "session"):
        allowed.add("--example")
    only_help = (any(arg in ("--help", "-h", "help") for arg in args)
                 and all(arg in allowed for arg in args))
    if not only_help and "--help" not in args and args[:1] != ["-h"]:
        return None
    text = _specific_help(command, args)
    return text if text is not None else _listed_usage(command)


def _specific_help(command, args):
    if command == "show":
        return (
            'usage: haejo show <name | flow.json> [--compact]\n'
            'Inspect replayable Flow JSON without changing the saved file.\n'
            '--compact omits parser defaults and indentation for agent context.'
        )
    if command == "batch":
        return (
            'usage: haejo batch <flow.json> --helper [--yes] [--max-jobs 1..1000] [--idle-timeout 1..600] [--timings] [--repair-packet /absolute/new.json] [--auto-repair codex|claude] [--max-repairs 1..10] [--repair-timeout 1..120]\n'
            'Wait for HAEJO_BATCH_READY; send one {"params":{"name":"value"}} JSON line per job.\n'
            'Pipe known JSONL rows once; for dependent jobs wait for each HAEJO_BATCH_RESULT.\n'
            'One template/connection; fresh checks per job. --auto-repair codex|claude enables bounded selector repair.\n'
            '--yes carries the user\'s approval to confirmation steps in every job.\n'
            'EOF ends it; default ten jobs, 90s idle. An unknown effect is not retried; inspect it.'
        )
    if command == "observe":
        return (
            "usage: haejo observe <bundle-id> --helper [--json] "
            "[--all-windows | --document /absolute/path] [--reveal TEXT] "
            "[--until TEXT | --until-text TEXT | --until-gone TEXT] [--timeout SECONDS]\n"
            "Example: haejo observe com.apple.calculator --helper\n"
            "Read current accessibility selectors. --json includes capabilities.\n"
            "Use --document to pin a TextEdit document; session reuses the connection."
        )
    if command == 'parallel':
        return (
            'usage: haejo parallel <manifest.json> --helper [--timeout 1..600] [--json]\n'
            'Manifest: {"schema":1,"jobs":[{"id":"job-1","window_id":123,"flow":{...}}]}.\n'
            'Use 1..4 distinct live windows from haejo windows APP --helper. Each job has its own signed session.\n'
            'Only reversible read/click/set_value/type_text steps with structured postconditions; no model calls.\n'
            'Same-window jobs are refused before dispatch. Unknown effects are never automatically replayed.'
        )
    if command == "session":
        text = (
            "usage: haejo session <bundle-id> --helper [--document /absolute/path] [--guide | --reuse-guide] [--steps] [--save /absolute/new.json] [--receipt /absolute/new.json] [--timings] [--idle-timeout 1..600] [--task new --goal '<goal>' | --task <id>] [--finish-task] [--then <bundle-id> [--document /absolute/path]]...\n"
            "exec_command tty=true, yield_time_ms=1000; wait for observation and\n"
            "HAEJO_SESSION_READY. write_stdin: one compact Flow JSON line + newline, yield_time_ms=5000.\n"
            "Poll the same session. One flow then exit. --document pins one TextEdit file.\n"
            "Use run --yes for steps the user already approved; use observe for a read-only check. "
            "Use run for judgment. Schema example: haejo session --help --example."
        )
    elif command == "run":
        text = (
            "usage: haejo run <flow.json> --helper [-p key=value] [--think N] [--timings] "
            "[--document /absolute/path] [--repair-packet /absolute/new.json] [--journal-dir /absolute/private/run] [--yes] [--auto-repair codex|claude] [--max-repairs 1..10] [--repair-timeout 1..120]\n"
            "Observe first; author a Flow using current selectors and result checks.\n"
            "Plain flows use no model judgment. --timings writes durations to stderr.\n"
            "Schema example: haejo run --help --example."
        )
    else:
        return None
    if "--example" in args:
        text += "\n" + json.dumps(calculator_example(), ensure_ascii=False, separators=(',', ':'))
    return text

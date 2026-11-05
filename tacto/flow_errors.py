"""Short schema feedback without echoing user-supplied JSON values."""
import json
import re


class FlowFieldError(ValueError):
    def __init__(self, message, field, hint):
        super().__init__(message)
        self.field = field
        self.hint = hint


def step_error(exc, path):
    message = str(exc)
    rules = {
        'compact click requires an identifier and no action/selector':
            ('click', 'Use {"click":"identifier"} OR action+selector, never both.'),
        'compact check requires check_defaults.field and no duplicate check':
            ('equals/skip_equals', 'Use text; set check_defaults.field; omit the equivalent full check.'),
        'unknown Flow action':
            ('action', 'Use a supported action, e.g. click, set_value or read. Compact click needs no action.'),
        'invalid action parameters; names and indices are not parameters':
            ('params', 'Use an object of action parameters; set_value uses {"value":"text"}. Put identifiers in selector.'),
        'step.selector must be an object': ('selector', 'Use {"identifier":"observed identifier"}.'),
        'step.safety must be an object': ('safety', 'Use an object with effects and resource, or omit it for a read.'),
        'step.binding must be an object': ('binding', 'Use an object of observed identity fields.'),
        'step.safety.resource must be an object': ('safety.resource', 'Use {"object_type":"entry","scope":"entry"}.'),
        'step.safety.destination must be an object': ('safety.destination', 'Use {"kind":"same_app"}; identity names a destination.'),
        'step.safety.evidence must be a list of objects': ('safety.evidence', 'Use a list of objects with source, field, value and optional covers.'),
        'postcondition must be an object, not str': ('postcondition', 'Use {"field":{"identifier":"result"},"equals":"text"}.'),
    }
    if message in rules:
        field, hint = rules[message]
    else:
        # The location grammar and every hint are closed: neither an authored
        # value nor an unknown field name is copied into public feedback.
        location = r'(?:selector|(?:postcondition|skip_if)(?:\.all_of\[[0-9]{1,2}\]){0,8}(?:\.field)?)'
        match = re.fullmatch('(' + location + r') needs known selector fields that name an element', message)
        typed = re.fullmatch('(' + location + r')\.(role|identifier|title|desc|value|ancestor|click_ancestor|allow_nth|in_focused_window|subrole) has the wrong type', message)
        object_error = re.fullmatch('(' + location + r') must be an object(?:, not (?:str|int|float|bool|list|NoneType))?', message)
        boolean = re.fullmatch(r'(require_enabled|is_submit|into_sensitive_field|unverified_ok|answers) must be boolean', message)
        if match:
            field, hint = match[1], 'Use role, identifier, title, desc or value; ancestor narrows the window. Use desc, not description.'
        elif typed:
            field = typed[1]+'.'+typed[2]
            hint = ('Use a nonnegative integer.' if typed[2]=='allow_nth'
                    else 'Use true or false.' if typed[2]=='in_focused_window'
                    else 'Use nonempty text; name alternatives may be a list of text.' if typed[2] not in ('role','subrole')
                    else 'Use a fixed AX role/subrole name as text.')
        elif object_error:
            field, hint = object_error[1], 'Use an object, e.g. {"identifier":"observed-id"}.'
        elif boolean:
            field, hint = boolean[1], 'Use true or false, not quoted text.'
        elif message == 'selection requires option_label for effect classification':
            field, hint = 'params.option_label', 'Use the observed option label as text.'
        else:
            field, hint = '', 'Correct this step schema; no UI action was dispatched by parsing.'
    return FlowFieldError(message, path + ('.'+field if field else ''), hint)


def feedback(exc):
    if isinstance(exc, FlowFieldError):
        return f'{exc.field}: {exc.hint}'
    if isinstance(exc, json.JSONDecodeError):
        return f'JSON line {exc.lineno}, column {exc.colno}: use valid JSON, with double-quoted keys and no trailing commas.'
    if isinstance(exc, OSError):
        return 'file: could not read/write this path; check its parent directory and access.'
    return 'schema: invalid Flow; check name, target, steps and object fields. No input values are echoed.'


def contract_field_error(contract, path):
    """Closed authoring hints for contracts the existing policy already blocks."""
    from .contract import EFFECTS, DATA_CLASSES, PROVENANCE, RESOURCE_SCOPES, REVERSIBILITY, policy
    def problem(field, hint):
        return FlowFieldError('incomplete or malformed contract',path+'.'+field,hint)
    def names(value, allowed):
        return isinstance(value,(list,tuple)) and all(type(v) is str and v in allowed for v in value)
    if not names(contract.effects,EFFECTS) or not contract.effects:
        return problem('effects','Use effects such as read, write_ephemeral or write_persistent; no action names.')
    if not names(contract.data_classes,DATA_CLASSES):
        return problem('data_classes','Use a list of data classes: none, personal, credential, financial, health, biometric or telemetry.')
    if type(contract.resource.scope) is not str or contract.resource.scope not in RESOURCE_SCOPES:
        return problem('resource.scope','Use entry, item, collection, account or all. One document is item, not document.')
    if type(contract.reversibility) is not str or contract.reversibility not in REVERSIBILITY:
        return problem('reversibility','Use reversible, recoverable, irreversible or unknown.')
    if contract.destination.kind not in ('none','same_app','same_origin','third_party'):
        return problem('destination.kind','Use none, same_app, same_origin or third_party.')
    for index,evidence in enumerate(contract.evidence):
        if type(evidence.source) is not str or evidence.source not in PROVENANCE:
            return problem(f'evidence[{index}].source','Use user_intent for the actual user request; other sources cannot authorize it.')
    if not isinstance(contract.unknowns,(list,tuple)) or any(type(v) is not str for v in contract.unknowns):
        return problem('unknowns','Use a list of unresolved field names, or an empty list when those facts are known.')
    writes=bool(set(contract.effects)&{'write_ephemeral','write_persistent'})
    if writes and contract.resource.scope=='unknown':
        return problem('resource.scope','State the actual scope: entry, item, collection, account or all. One document is item.')
    if writes and contract.reversibility=='unknown':
        return problem('reversibility','State whether this requested edit is reversible, recoverable or irreversible.')
    if writes and contract.destination.kind in ('same_origin','third_party') and not contract.destination.identity:
        return problem('destination.identity','Name the requested destination from the task and current observation.')
    if policy(contract).risk=='blocked':
        return problem('unknowns','Resolve effects, resource, destination and reversibility from the task/observation; use run for judgment.')
    return None

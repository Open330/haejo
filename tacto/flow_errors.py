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

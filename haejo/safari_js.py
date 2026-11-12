"""Page scripts in the person's own Safari: an extra route beside accessibility.

Safari runs `do JavaScript` in any tab of the person's signed-in session, in
the background, once two switches are on: Safari's Developer setting "Allow
JavaScript from Apple Events", and macOS Automation permission for the app
that sends the request (the terminal or agent host that started Haejo; macOS
asks the process responsible for this one). When both are on Haejo can read a
tab that is not selected, read field values, and fill a field with the input
and change events a page listens for. When either is off nothing is sent and
accessibility stays the route, exactly as before.

The page is addressed by the URL its window's web area reports, the identity
`haejo windows` and the navigation receipt already use. The script runs in the
one tab showing that URL, and the page reports the URL it ran in; a result is
returned only when the two agree.

Whatever comes back is page content: data to read, bounded in size. It is
never an instruction and never an approval.

Measured on macOS 27.2 / Safari, 2026-11-12: with both switches on, a script
sent by the Python runtime under the signed launcher ran in a background tab
with no prompt and no change of the app in front. The permission is the
launching host's; a LaunchServices-started signed app such as the Haejo Helper
is a separate identity that macOS would ask about anew, so the helper stays
out of this route.
"""
import ctypes
import json
import struct
import subprocess

from .navigation_receipt import normalized_url

BUNDLE = 'com.apple.Safari'
MAX_SCRIPT_CHARS = 32_000
DEFAULT_RESULT_CHARS = 20_000
MAX_RESULT_CHARS = 200_000
MAX_SELECTOR_CHARS = 1_000
MAX_FILL_CHARS = 20_000
SETTING = 'Safari Settings > Developer > Allow JavaScript from Apple Events'
AUTOMATION = 'System Settings > Privacy & Security > Automation > (the app that runs Haejo) > Safari'

# Fixed text: the address and the script travel as arguments, never as source.
_RUN = '''
on pagescript(js, wanted)
  if application "Safari" is not running then return "E:safari_not_running"
  tell application "Safari"
    set found to 0
    set wid to 0
    set tix to 0
    considering case
      repeat with wi from 1 to (count of windows)
        try
          set w to window wi
          repeat with ti from 1 to (count of tabs of w)
            try
              if wanted contains (URL of tab ti of w) then
                set found to found + 1
                set wid to id of w
                set tix to ti
              end if
            end try
          end repeat
        end try
      end repeat
    end considering
    if found is 0 then return "E:page_not_found"
    if found > 1 then return "E:page_ambiguous:" & found
    set r to missing value
    try
      with timeout of 20 seconds
        set r to do JavaScript js in tab tix of window id wid
      end timeout
    on error msg number n
      -- A script Safari could not parse yields no result at all.
      if n is -2753 then return "E:no_value"
      return "E:refused:" & n & ":" & msg
    end try
    if r is missing value then return "E:no_value"
    return "V:" & r
  end tell
end pagescript
'''


def _send(script, wanted):
    """Run the fixed handler in this process: (reply text, None) or (None, error number).

    The request leaves from the same process whose permission was just read,
    so "already allowed" and "is sent" are one identity.
    """
    from Foundation import NSAppleEventDescriptor, NSAppleScript
    compiled = NSAppleScript.alloc().initWithSource_(_RUN)
    event = NSAppleEventDescriptor.appleEventWithEventClass_eventID_targetDescriptor_returnID_transactionID_(
        _four(b'ascr'), _four(b'psbr'), NSAppleEventDescriptor.nullDescriptor(), -1, 0)
    event.setParamDescriptor_forKeyword_(NSAppleEventDescriptor.descriptorWithString_('pagescript'), _four(b'snam'))
    pages = NSAppleEventDescriptor.listDescriptor()
    for index, value in enumerate(wanted, 1):
        pages.insertDescriptor_atIndex_(NSAppleEventDescriptor.descriptorWithString_(value), index)
    arguments = NSAppleEventDescriptor.listDescriptor()
    arguments.insertDescriptor_atIndex_(NSAppleEventDescriptor.descriptorWithString_(script), 1)
    arguments.insertDescriptor_atIndex_(pages, 2)
    event.setParamDescriptor_forKeyword_(arguments, _four(b'----'))
    reply, problem = compiled.executeAppleEvent_error_(event, None)
    if reply is None:
        number = (problem or {}).get('NSAppleScriptErrorNumber')
        return None, int(number) if number is not None else 0
    return reply.stringValue(), None



def _four(code):
    return struct.unpack('>I', code)[0]


class _AEDesc(ctypes.Structure):
    _fields_ = [('descriptorType', ctypes.c_uint32), ('dataHandle', ctypes.c_void_p)]


_STATUS = {0: 'granted', -1744: 'not_asked', -1743: 'declined', -600: 'not_running'}


def automation_status(bundle=BUNDLE, ask=False):
    """Whether macOS already lets this process's host send requests to the app.

    Asks the system without sending anything and without showing a prompt:
    'granted', 'not_asked', 'declined', 'not_running' or 'unknown'. `ask=True`
    is `haejo page allow`: the person asked for the route, so macOS may show
    its Automation question once and this waits for the answer.
    """
    try:
        services = ctypes.CDLL('/System/Library/Frameworks/CoreServices.framework/CoreServices')
        create, check, dispose = (services.AECreateDesc, services.AEDeterminePermissionToAutomateTarget,
                                  services.AEDisposeDesc)
        create.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_long, ctypes.POINTER(_AEDesc)]
        create.restype = ctypes.c_int16
        check.argtypes = [ctypes.POINTER(_AEDesc), ctypes.c_uint32, ctypes.c_uint32, ctypes.c_bool]
        check.restype = ctypes.c_int32
        dispose.argtypes = [ctypes.POINTER(_AEDesc)]
        target = _AEDesc()
        name = bundle.encode('ascii')
        if create(_four(b'bund'), name, len(name), ctypes.byref(target)) != 0:
            return 'unknown'
        try:
            # askUserIfNeeded=False: a status read, never a prompt.
            code = check(ctypes.byref(target), _four(b'****'), _four(b'****'), bool(ask))
        finally:
            dispose(ctypes.byref(target))
    except (OSError, AttributeError, ValueError):
        return 'unknown'
    return _STATUS.get(code, 'unknown')


def setting_state(run=subprocess.run):
    """Safari's "Allow JavaScript from Apple Events": 'on', 'off' or 'unconfirmed'.

    Safari keeps it in its own preferences; a host that cannot read them gets
    'unconfirmed', which the first script in a page settles.
    """
    try:
        out = run(['/usr/bin/defaults', 'read', BUNDLE, 'AllowJavaScriptFromAppleEvents'],
                  capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return 'unconfirmed'
    value = out.stdout.strip() if out.returncode == 0 else ''
    return {'1': 'on', '0': 'off'}.get(value, 'unconfirmed')


def _sender():
    """The app macOS lists under Automation for this process, when it can be read."""
    try:
        import os
        from .process_responsibility import observe_responsibility
        return observe_responsibility(os.getpid()).get('responsible_path')
    except Exception:
        return None


def probe(url=None, *, automation=automation_status, setting=setting_state, evaluate=None):
    """Is the page-script route usable right now? Sends nothing unless it is
    already permitted, and then only a constant to the page named by `url`."""
    result = {'type': 'page_script', 'browser': BUNDLE, 'available': False}
    allowed = automation()
    result['automation'] = allowed
    if allowed != 'granted':
        result['reason'] = {'not_running': 'safari_not_running'}.get(allowed, 'automation_' + allowed)
        result['setting'] = 'unconfirmed'
        if allowed != 'not_running':
            result['turn_on'] = [AUTOMATION, SETTING]
            sender = _sender()
            if sender:
                result['automation_asks_for'] = sender
        return result
    state = setting()
    if state == 'unconfirmed' and url is not None:
        tried = (evaluate or run_script)(url, '1')
        if tried.get('type') == 'page_value':
            state = 'on'
        elif tried.get('reason') == 'safari_setting_off':
            state = 'off'
        else:
            result['page'] = tried.get('error')
    result['setting'] = state
    if state == 'on':
        result['available'] = True
        result['can'] = ['page.evaluate', 'page.text', 'page.value', 'page.fill']
    else:
        result['reason'] = 'safari_setting_' + state
        result['turn_on'] = [SETTING]
    return result


def wrap(source, limit=DEFAULT_RESULT_CHARS):
    """The script Safari receives: the caller's expression inside a reporter.

    The reporter names the URL the expression ran in, turns the value into
    JSON, and bounds it in the page before anything crosses to Haejo.
    """
    return ('(function(){var u=String(location.href),L=%d,o;'
            'try{var v=(\n%s\n);'
            'if(typeof v==="string"&&v.length>L){o={ok:true,value:v.slice(0,L),truncated:true,length:v.length}}'
            'else{o={ok:true,value:v===undefined?null:v}}}'
            'catch(e){o={ok:false,error:String(e&&e.message||e).slice(0,300)}}'
            'var s;try{s=JSON.stringify(o)}catch(e){s=undefined}'
            'if(s===undefined){o={ok:false,error:"not_json"};s=JSON.stringify(o)}'
            'if(s.length>L+200){o={ok:false,error:"result_too_large",length:s.length}}'
            'o.url=u;o.url_after=String(location.href);return JSON.stringify(o)})()') % (limit, source)


def _error(code, url, effect='not_started', **extra):
    return {'type': 'error', 'error': code, 'url': url, 'effect': effect, **extra}


def run_script(url, source, *, max_chars=DEFAULT_RESULT_CHARS, automation=automation_status, send=None,
               changes_page=False):
    """Evaluate one synchronous JavaScript expression in the Safari tab showing `url`.

    Returns {'type': 'page_value', 'url', 'value', 'content': 'page_data'} or an
    error naming what to do next. A script that may have changed the page
    reports effect 'unknown' when its outcome was not read back.
    """
    target = normalized_url(url)
    if target is None:
        return _error('invalid_url', url, detail='an absolute http(s) URL without credentials')
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_SCRIPT_CHARS or '\x00' in source:
        return _error('invalid_script', target, detail=f'one expression of at most {MAX_SCRIPT_CHARS} characters')
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_RESULT_CHARS:
        return _error('invalid_limit', target, detail=f'1..{MAX_RESULT_CHARS} characters')
    allowed = automation()
    if allowed != 'granted':
        # Nothing is sent, so macOS has nothing to ask about.
        reason = 'safari_not_running' if allowed == 'not_running' else 'automation_' + allowed
        return _error('page_script_unavailable', target, reason=reason, route='accessibility',
                      hint='haejo page status')
    uncertain = 'unknown' if changes_page else 'not_started'
    wanted = sorted({target, url})
    send = send if send is not None else _send
    try:
        text, failed = send(wrap(source, max_chars), wanted)
    except Exception:
        return _error('page_script_unavailable', target, reason='apple_events_unavailable', route='accessibility')
    if failed == -1743:
        return _error('page_script_unavailable', target, reason='automation_declined', route='accessibility')
    if failed == -1712:
        return _error('page_script_timeout', target, uncertain)
    if failed == -2753:
        # Safari hands back nothing at all for a script it could not parse.
        return _error('script_error', target, detail='the script did not parse')
    if not isinstance(text, str) or not text.startswith(('V:', 'E:')):
        return _error('page_script_failed', target, uncertain, **({'apple_event_error': failed} if failed else {}))
    if text.startswith('E:'):
        return _refusal(text[2:], target, uncertain)
    if len(text) > max_chars * 6 + 4096:
        return _error('result_too_large', target, uncertain)
    try:
        reply = json.loads(text[2:])
    except ValueError:
        return _error('page_script_failed', target, uncertain, detail='the page returned no readable result')
    if not isinstance(reply, dict) or type(reply.get('ok')) is not bool:
        return _error('page_script_failed', target, uncertain, detail='the page returned no readable result')
    ran_in = normalized_url(reply.get('url'))
    if ran_in != target:
        # The tab moved on between the address match and the script.
        return _error('page_changed', target, uncertain, **({'ran_in': ran_in} if ran_in else {}))
    if not reply['ok']:
        code = reply.get('error')
        if code == 'result_too_large':
            return _error('result_too_large', target, uncertain,
                          **({'length': reply['length']} if type(reply.get('length')) is int else {}),
                          hint='read a smaller part, or raise --max-chars')
        if code == 'not_json':
            return _error('result_not_data', target, uncertain, detail='return text, numbers, lists or plain objects')
        return _error('script_error', target, uncertain, detail=str(code)[:300])
    result = {'type': 'page_value', 'url': target, 'value': reply.get('value'), 'content': 'page_data'}
    if reply.get('truncated') is True:
        result['truncated'] = True
        if type(reply.get('length')) is int:
            result['length'] = reply['length']
    after = normalized_url(reply.get('url_after'))
    if after is not None and after != target:
        result['url_after'] = after
    return result


def _refusal(text, target, uncertain):
    if text == 'safari_not_running':
        return _error('page_script_unavailable', target, reason='safari_not_running', route='accessibility')
    if text == 'page_not_found':
        return _error('page_not_found', target, hint='haejo windows com.apple.Safari --helper lists each page url')
    if text.startswith('page_ambiguous:'):
        count = text.split(':', 1)[1]
        return _error('page_ambiguous', target, **({'tabs': int(count)} if count.isdigit() else {}),
                      detail='several tabs show this address; work in the window accessibility observes')
    if text == 'no_value':
        return _error('script_error', target, uncertain, detail='the script did not parse, or returned nothing')
    if text.startswith('refused:'):
        number, _, message = text[len('refused:'):].partition(':')
        if number == '-1743':
            return _error('page_script_unavailable', target, reason='automation_declined', route='accessibility',
                          turn_on=[AUTOMATION])
        if number == '-1712':
            return _error('page_script_timeout', target, uncertain)
        if 'JavaScript' in message and 'Apple' in message:
            return _error('page_script_unavailable', target, reason='safari_setting_off', route='accessibility',
                          turn_on=[SETTING])
        return _error('page_script_failed', target, uncertain, **({'apple_event_error': int(number)} if number.lstrip('-').isdigit() else {}))
    return _error('page_script_failed', target, uncertain)


def _selector(selector):
    return isinstance(selector, str) and 0 < len(selector) <= MAX_SELECTOR_CHARS and '\x00' not in selector


def page_text(url, selector=None, *, max_chars=DEFAULT_RESULT_CHARS, **options):
    """The text a person reads on the page (or in one element), selected tab or not."""
    if selector is not None and not _selector(selector):
        return _error('invalid_selector', url)
    if selector is None:
        source = '(document.body?document.body.innerText:"")'
    else:
        source = ('(function(){var e=document.querySelector(%s);if(!e)throw new Error("no element matches");'
                  'return e.innerText!==undefined?e.innerText:e.textContent})()') % json.dumps(selector)
    result = run_script(url, source, max_chars=max_chars, **options)
    if result.get('type') == 'page_value':
        result = dict(result, type='page_text', text=result['value'])
        del result['value']
    return result


_VALUES = ('(function(){var all=document.querySelectorAll(%s);'
           'return {matched:all.length,values:Array.prototype.slice.call(all,0,50).map(function(e){'
           'var secure=e.type==="password";'
           'var v=e.type==="checkbox"||e.type==="radio"?e.checked:("value" in e?e.value:e.textContent);'
           'return {tag:e.tagName.toLowerCase(),name:e.name||e.id||null,'
           'value:secure?null:(typeof v==="string"?v.slice(0,2000):v),secure:secure||undefined}})}})()')


def page_values(url, selector, **options):
    """Current values of the form controls (or text of the elements) a CSS selector matches."""
    if not _selector(selector):
        return _error('invalid_selector', url)
    result = run_script(url, _VALUES % json.dumps(selector), **options)
    if result.get('type') == 'page_value' and isinstance(result.get('value'), dict):
        value = result.pop('value')
        result.update(type='page_values', matched=value.get('matched'), values=value.get('values'))
    return result


_FILL = ('(function(){var all=document.querySelectorAll(%s);'
         'if(all.length!==1)return {matched:all.length};'
         'var e=all[0],val=%s,T=window.HTMLTextAreaElement,S=window.HTMLSelectElement,I=window.HTMLInputElement;'
         'var p=e instanceof T?T.prototype:e instanceof S?S.prototype:e instanceof I?I.prototype:null;'
         'if(!p||e.disabled||e.readOnly)return {matched:1,editable:false};'
         # The element's own setter: frameworks that wrap `value` still see the change.
         'Object.getOwnPropertyDescriptor(p,"value").set.call(e,val);'
         'e.dispatchEvent(new Event("input",{bubbles:true}));'
         'e.dispatchEvent(new Event("change",{bubbles:true}));'
         'return {matched:1,editable:true,holds:e.value===val,secure:e.type==="password"}})()')


def page_fill(url, selector, value, **options):
    """Set one field's value and dispatch input and change, then read it back.

    For pages that ignore an accessibility value set: the page's own listeners
    run as they do for typing. `filled` is true only when the field holds the
    value afterwards.
    """
    if not _selector(selector):
        return _error('invalid_selector', url)
    if not isinstance(value, str) or len(value) > MAX_FILL_CHARS or '\x00' in value:
        return _error('invalid_value', url, detail=f'text of at most {MAX_FILL_CHARS} characters')
    result = run_script(url, _FILL % (json.dumps(selector), json.dumps(value)), changes_page=True, **options)
    if result.get('type') != 'page_value':
        return result
    seen = result.get('value') if isinstance(result.get('value'), dict) else {}
    if seen.get('matched') != 1:
        return _error('field_not_unique', result['url'], matched=seen.get('matched'),
                      detail='the selector must match exactly one field')
    if seen.get('editable') is not True:
        return _error('field_not_editable', result['url'])
    if seen.get('holds') is not True:
        return _error('fill_not_held', result['url'], 'unknown', detail='the page changed the value; read it back')
    return {'type': 'page_filled', 'url': result['url'], 'filled': True, 'events': ['input', 'change'],
            **({'url_after': result['url_after']} if 'url_after' in result else {})}


USAGE = ('usage: page status [<URL>]\n'
         '       page allow        (turn the route on: macOS asks once whether this app may control Safari)\n'
         '       page text <URL> [--selector CSS] [--max-chars N]\n'
         '       page value <URL> --selector CSS\n'
         '       page fill <URL> --selector CSS --value TEXT\n'
         '       page eval <URL> --js EXPRESSION [--max-chars N]\n'
         '  <URL> is the page address `haejo windows com.apple.Safari --helper` reports.')


def main(args, out=print):
    """`haejo page ...`: 0 with one JSON line of page data, 1 with an error line, 2 for usage."""
    args = [value for value in args if value != '--helper']
    options = {}
    for flag in ('--selector', '--value', '--js', '--max-chars'):
        if flag in args:
            at = args.index(flag)
            if args.count(flag) != 1 or at + 1 >= len(args):
                out(USAGE)
                return 2
            options[flag] = args[at + 1]
            args = args[:at] + args[at + 2:]
    verb = args[0] if args else None
    needs = {'status': set(), 'allow': set(), 'text': set(), 'value': {'--selector'}, 'fill': {'--selector', '--value'},
             'eval': {'--js'}}
    may = {'status': set(), 'allow': set(), 'text': {'--selector', '--max-chars'}, 'value': set(), 'fill': set(),
           'eval': {'--max-chars'}}
    count = {'status': (1, 2), 'allow': (1,)}.get(verb, (2,))
    if verb not in needs or len(args) not in count or not needs[verb] <= set(options) <= needs[verb] | may[verb]:
        out(USAGE)
        return 2
    limit = {}
    if '--max-chars' in options:
        if not options['--max-chars'].isdigit():
            out(USAGE)
            return 2
        limit = {'max_chars': int(options['--max-chars'])}
    if verb == 'status':
        result = probe(args[1] if len(args) == 2 else None)
    elif verb == 'allow':
        result = probe(automation=lambda: automation_status(ask=True))
    elif verb == 'text':
        result = page_text(args[1], options.get('--selector'), **limit)
    elif verb == 'value':
        result = page_values(args[1], options['--selector'])
    elif verb == 'fill':
        result = page_fill(args[1], options['--selector'], options['--value'])
    else:
        result = run_script(args[1], options['--js'], changes_page=True, **limit)
    try:
        from .access_log import current
        if current.get() is not None:
            # Which route ran and how it ended; never the page's content.
            current.get().task_result({key: value for key, value in result.items() if key in ('error', 'status')})
    except Exception:
        pass
    out(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('type') != 'error' else 1

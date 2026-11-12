"""Owned web fixture for the Safari capability matrix.

Every control reports what it RECEIVED (DOM events with `isTrusted`, the value
it holds, submitted form values) to this server, so a test judges an action by
the receiving page and not by the action's reply. Two listeners share one
record so a cross-origin iframe (same host, another port) reports to the same
place.

    python tests/fixtures/safari_matrix_server.py 8811 8812   # serve until killed
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LONG_ROWS = 1600

_SCRIPT = r'''
const ev = (kind, id, detail) => fetch('/ev', {method: 'POST', keepalive: true,
  body: JSON.stringify(Object.assign({kind, id}, detail || {}))}).catch(() => {});
const $ = id => document.getElementById(id);
function watch(id, kinds) {
  const el = $(id);
  for (const kind of kinds) el.addEventListener(kind, e => ev(kind, id, {
    trusted: e.isTrusted, value: 'value' in el ? el.value : el.textContent,
    checked: el.checked === undefined ? null : el.checked, key: e.key || null}));
}
'''

_BASIC = r'''<!doctype html><meta charset="utf-8"><title>Haejo matrix basic TOKEN</title>
<style>body{font:14px system-ui;margin:16px}label,div.row{display:block;margin:8px 0}
#hov{width:300px;height:140px;background:#e8eef8}#hov ul{display:none}#hov.open ul{display:block}
[role=listbox]{border:1px solid #888;margin:0;padding:0;list-style:none;width:160px}
[role=option]{padding:4px 8px}[role=combobox]{border:1px solid #888;width:160px;padding:4px 8px}
#rich{border:1px solid #888;min-height:24px;width:300px;padding:4px}</style>
<div id="hov" aria-label="Hover menu"><span id="hov-label">Hover here</span><ul><li><button id="hov-item" type="button">Hidden action</button></li></ul></div>
<h1>Haejo matrix basic</h1>
<p id="ready">matrix-ready-text</p>
<div class="row"><a id="lnk" href="/linked?from=basic">Go linked page</a></div>
<div class="row"><button id="btn" type="button">Press me</button> <span id="btn-out">presses:0</span></div>
<label>Plain <input id="plain" aria-label="Plain name"></label>
<label>Notes <textarea id="notes" aria-label="Notes area"></textarea></label>
<label>Controlled <input id="ctl" aria-label="Controlled field"></label><span id="ctl-out">state:</span>
<label>Keydown <input id="keyonly" aria-label="Keydown field"></label><span id="key-out">keys:</span>
<label><input type="checkbox" id="agree" aria-label="Agree box"> Agree</label>
<div class="row" role="radiogroup" aria-label="Color">
<label><input type="radio" name="color" id="red" value="red" aria-label="Color red"> red</label>
<label><input type="radio" name="color" id="green" value="green" aria-label="Color green"> green</label></div>
<label>Fruit <select id="fruit" aria-label="Fruit choice"><option>Apple</option><option>Banana</option><option>Cherry</option></select></label>
<div class="row"><div id="dd" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-label="City choice" tabindex="0">Pick a city</div>
<ul id="dd-list" role="listbox" aria-label="City options" hidden><li role="option" id="dd-seoul">Seoul</li><li role="option" id="dd-busan">Busan</li></ul></div>
<div class="row"><div id="pd" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-label="Size choice" tabindex="0">Pick a size</div>
<ul id="pd-list" role="listbox" aria-label="Size options" hidden><li role="option" id="pd-small">Small</li><li role="option" id="pd-large">Large</li></ul></div>
<label>Day <input type="date" id="day" aria-label="Day field"></label>
<div class="row"><div id="rich" contenteditable="true" role="textbox" aria-label="Rich editor"></div></div>
<div class="row"><button id="al" type="button">Show alert</button></div>
<div class="row"><a id="nw" href="/popup?by=link" target="_blank">Open new window</a>
<button id="wo" type="button">Open by script</button></div>
<div class="row"><button id="dl" type="button">Load later</button> <span id="dl-out">pending</span></div>
<div class="row"><button id="send" type="button">Collect values</button> <span id="send-out">uncollected</span></div>
<script>SCRIPT
let presses = 0;
$('btn').addEventListener('click', e => { $('btn-out').textContent = 'presses:' + (++presses); ev('click', 'btn', {trusted: e.isTrusted}); });
$('lnk').addEventListener('click', e => ev('click', 'lnk', {trusted: e.isTrusted}));
watch('plain', ['input', 'change', 'keydown']); watch('notes', ['input', 'change', 'keydown']);
// A framework-controlled field: its state follows `input` events only, and a
// value that arrived any other way is written back from state (a re-render).
let ctl = '';
$('ctl').addEventListener('input', e => { ctl = $('ctl').value; $('ctl-out').textContent = 'state:' + ctl; ev('input', 'ctl', {trusted: e.isTrusted, value: ctl}); });
setInterval(() => { if ($('ctl').value !== ctl) { ev('revert', 'ctl', {value: $('ctl').value}); $('ctl').value = ctl; } }, 150);
// A field whose state is built from key events alone.
let keys = '';
$('keyonly').addEventListener('keydown', e => { if (e.key.length === 1) keys += e.key; else if (e.key === 'Backspace') keys = keys.slice(0, -1);
  $('key-out').textContent = 'keys:' + keys; ev('keydown', 'keyonly', {trusted: e.isTrusted, value: keys, key: e.key}); });
watch('agree', ['change', 'click']); watch('red', ['change', 'click']); watch('green', ['change', 'click']);
watch('fruit', ['change', 'input']); watch('day', ['change', 'input']); watch('rich', ['input', 'keydown']);
function dropdown(id, openOn, pickOn) {
  const box = $(id), list = $(id + '-list');
  box.addEventListener(openOn, e => { list.hidden = !list.hidden; box.setAttribute('aria-expanded', String(!list.hidden)); ev('open:' + openOn, id, {trusted: e.isTrusted}); });
  for (const item of list.children) item.addEventListener(pickOn, e => { box.textContent = item.textContent; list.hidden = true;
    box.setAttribute('aria-expanded', 'false'); ev('pick:' + pickOn, id, {trusted: e.isTrusted, value: item.textContent}); });
}
dropdown('dd', 'click', 'click'); dropdown('pd', 'pointerdown', 'pointerdown');
$('hov').addEventListener('mouseenter', e => { $('hov').classList.add('open'); ev('mouseenter', 'hov', {trusted: e.isTrusted}); });
$('hov').addEventListener('mouseleave', e => { $('hov').classList.remove('open'); ev('mouseleave', 'hov', {trusted: e.isTrusted}); });
$('hov-item').addEventListener('click', e => ev('click', 'hov-item', {trusted: e.isTrusted}));
$('al').addEventListener('click', e => { ev('alert-open', 'al', {trusted: e.isTrusted}); alert('matrix alert text'); ev('alert-closed', 'al'); });
$('nw').addEventListener('click', e => ev('click', 'nw', {trusted: e.isTrusted}));
$('wo').addEventListener('click', e => { const w = window.open('/popup?by=script', '_blank', 'width=520,height=360'); ev('window-open', 'wo', {trusted: e.isTrusted, opened: !!w}); });
$('dl').addEventListener('click', e => { ev('click', 'dl', {trusted: e.isTrusted}); fetch('/delayed').then(r => r.text()).then(t => { $('dl-out').textContent = t; }); });
$('send').addEventListener('click', e => { const body = {plain: $('plain').value, notes: $('notes').value, ctl, keys,
    agree: $('agree').checked, color: (document.querySelector('input[name=color]:checked') || {}).value || null,
    fruit: $('fruit').value, city: $('dd').textContent, size: $('pd').textContent, day: $('day').value, rich: $('rich').textContent};
  fetch('/submit', {method: 'POST', body: JSON.stringify(body)}).then(() => { $('send-out').textContent = "collected"; }); });
</script>'''

_LONG = r'''<!doctype html><meta charset="utf-8"><title>Haejo matrix long TOKEN</title>
<h1>Haejo matrix long</h1><div id="rows"></div>
<p id="deep">deep-marker-text</p><button id="deep-btn" type="button">Deep button</button>
<script>SCRIPT
const rows = $('rows'); let html = '';
for (let i = 1; i <= ROWS; i++) html += '<p>Row ' + i + '</p>';
rows.innerHTML = html;
let last = 0;
addEventListener('scroll', e => { const now = Date.now(); if (now - last > 200) { last = now; ev('scroll', 'window', {trusted: e.isTrusted, y: Math.round(scrollY)}); } });
$('deep-btn').addEventListener('click', e => ev('click', 'deep-btn', {trusted: e.isTrusted, y: Math.round(scrollY)}));
</script>'''

_FRAMES = r'''<!doctype html><meta charset="utf-8"><title>Haejo matrix frames TOKEN</title>
<h1>Haejo matrix frames</h1>
<iframe id="same" title="Same origin frame" src="/frame?who=same" width="420" height="120"></iframe>
<iframe id="cross" title="Cross origin frame" src="http://127.0.0.1:CROSS/frame?who=cross" width="420" height="120"></iframe>'''

_FRAME = r'''<!doctype html><meta charset="utf-8"><title>frame WHO</title>
<p>frame-WHO-text</p><button id="fb" type="button">Frame button WHO</button>
<input id="ff" aria-label="Frame field WHO">
<script>SCRIPT
$('fb').addEventListener('click', e => ev('click', 'frame-WHO-button', {trusted: e.isTrusted}));
$('ff').addEventListener('input', e => ev('input', 'frame-WHO-field', {trusted: e.isTrusted, value: $('ff').value}));
</script>'''


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, kind='text/html; charset=utf-8', status=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        record = self.server.record
        url = urlparse(self.path)
        query = parse_qs(url.query)
        fill = lambda page: (page.replace('SCRIPT', _SCRIPT).replace('TOKEN', record.token)
                             .replace('CROSS', str(record.cross_port)).replace('ROWS', str(LONG_ROWS)))
        # `/p/<page>/<anything>` serves the same page, so each test can open
        # its own address and pick its window by that path.
        page = '/'.join(url.path.split('/')[:3])
        if url.path == '/state':
            return self._send(json.dumps(record.snapshot()), 'application/json')
        if url.path == '/reset':
            record.reset()
            return self._send('ok', 'text/plain')
        if page == '/p/basic':
            return self._send(fill(_BASIC))
        if page == '/p/long':
            return self._send(fill(_LONG))
        if page == '/p/frames':
            return self._send(fill(_FRAMES))
        if url.path == '/frame':
            who = 'cross' if query.get('who') == ['cross'] else 'same'
            return self._send(fill(_FRAME).replace('WHO', who))
        if url.path in ('/linked', '/popup'):
            record.add('get', {'path': url.path, 'query': url.query})
            name = url.path[1:]
            return self._send(f'<!doctype html><title>Haejo matrix {name} {record.token}</title>'
                              f'<h1>Haejo matrix {name}</h1><p>{name}-arrived-text</p>')
        if url.path == '/delayed':
            time.sleep(1.5)
            return self._send('late-text-arrived', 'text/plain')
        return self._send('not found', 'text/plain', 404)

    def do_POST(self):
        record = self.server.record
        raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        try:
            body = json.loads(raw or b'{}')
        except ValueError:
            body = {'raw': raw.decode('utf-8', 'replace')}
        if self.path == '/submit':
            record.add('submit', body)
        else:
            record.add('event', body)
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()


class Record:
    def __init__(self, token, cross_port):
        self.token, self.cross_port = token, cross_port
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self._items = []

    def add(self, kind, body):
        with self._lock:
            self._items.append({'type': kind, 'at': time.time(), **body})

    def snapshot(self):
        with self._lock:
            return list(self._items)

    def events(self, element=None, kind=None):
        return [item for item in self.snapshot() if item['type'] == 'event'
                and (element is None or item.get('id') == element)
                and (kind is None or item.get('kind') == kind)]

    def submitted(self):
        found = [item for item in self.snapshot() if item['type'] == 'submit']
        return found[-1] if found else None

    def visits(self, path):
        return [item for item in self.snapshot() if item['type'] == 'get' and item['path'] == path]


class MatrixServer:
    """Main and cross-origin listeners on 127.0.0.1 sharing one Record."""

    def __init__(self, port=0, cross_port=0, token='fixture'):
        self._servers = [ThreadingHTTPServer(('127.0.0.1', port), _Handler),
                         ThreadingHTTPServer(('127.0.0.1', cross_port), _Handler)]
        self.port, self.cross_port = (server.server_port for server in self._servers)
        self.record = Record(token, self.cross_port)
        self.origin = f'http://127.0.0.1:{self.port}'
        self._threads = []
        for server in self._servers:
            server.record = self.record
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._threads.append(thread)

    def close(self):
        for server in self._servers:
            server.shutdown()
            server.server_close()
        for thread in self._threads:
            thread.join(timeout=5)


if __name__ == '__main__':
    ports = [int(value) for value in sys.argv[1:3]] or [8811, 8812]
    served = MatrixServer(ports[0], ports[1] if len(ports) > 1 else 0, token='manual')
    print(f'serving {served.origin} (cross-origin frame on {served.cross_port})', flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        served.close()

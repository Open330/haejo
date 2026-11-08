"""Owned one-screen counter for physical AX/HID qualification.

Run with an explicit --bind IP on the device's reachable LAN. No installation,
external assets, persistence, credentials, or automatic phone navigation.
Server counts are receiving evidence, not attribution to the automation alone.
"""
import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Tacto owned counter</title>
<style>
body{font:24px system-ui;text-align:center;margin:0;background:#fff;color:#111}
main{padding:12vh 16px}button{display:block;margin:40px auto;width:280px;
height:100px;font:22px system-ui;background:#1747b0;color:white;border:0;border-radius:12px}
</style><main><h1>Tacto test</h1>
<p id="tacto-counter-value" role="status" aria-live="polite">Counter 0</p>
<button id="tacto-counter-increment">Increment test counter</button>
<p id="tacto-counter-receipt">No input received</p></main>
<script>
'use strict';
let pending=false,sequence=0;
const output=document.getElementById('tacto-counter-value');
const receipt=document.getElementById('tacto-counter-receipt');
document.getElementById('tacto-counter-increment').addEventListener('click',async event=>{
  if(!event.isTrusted){receipt.textContent='Untrusted event refused';return;}
  if(pending){receipt.textContent='Overlapping input detected';}
  pending=true;
  const request=++sequence;
  try{
    const response=await fetch(location.pathname+'event',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sequence:request,trusted:event.isTrusted,pointer_type:event.pointerType||'unknown'})});
    if(!response.ok)throw new Error('receiving failure');
    const result=await response.json();output.textContent='Counter '+result.count;
    receipt.textContent='Server received '+result.count+' input event(s)';
  }catch(error){receipt.textContent='Result unknown; do not tap again';}
  finally{pending=false;}
});
</script></html>'''


class CounterServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        self.token = secrets.token_urlsafe(24)
        self.events = []
        self.lock = threading.Lock()
        super().__init__(address, CounterHandler)

    @property
    def fixture_path(self):
        return '/' + self.token + '/'


class CounterHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Exclude device addresses, tokens and request bodies from logs.

    def respond(self, status, value, content_type='application/json'):
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        root = self.server.fixture_path
        if self.path == root:
            with self.server.lock:
                count = len(self.server.events)
            page = PAGE.replace('>Counter 0<', '>Counter '+str(count)+'<')
            page = page.replace('>Tacto test<', '>Tacto test '+self.server.token[:8]+'<')
            self.respond(200, page, 'text/html; charset=utf-8')
        elif self.path == root + 'state':
            with self.server.lock:
                count = len(self.server.events)
                sequences = [item['sequence'] for item in self.server.events]
                pointer_types = [item['pointer_type'] for item in self.server.events]
            self.respond(200, {'count': count, 'sequences': sequences,
                               'pointer_types': pointer_types,
                               'exactly_one_received': count == 1})
        else:
            self.respond(404, {'error': 'unknown_fixture'})

    def do_POST(self):
        if self.path != self.server.fixture_path + 'event':
            self.respond(404, {'error': 'unknown_fixture'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 512 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            self.connection.settimeout(2)
            event = json.loads(self.rfile.read(size))
            if (set(event) != {'sequence', 'trusted', 'pointer_type'}
                    or type(event['sequence']) is not int or not 1 <= event['sequence'] <= 100
                    or event['trusted'] is not True or event['pointer_type'] not in ('touch', 'mouse', 'pen', 'unknown')):
                raise ValueError()
        except (ValueError, TypeError, OSError):
            self.respond(400, {'error': 'invalid_event'})
            return
        with self.server.lock:
            # Never deduplicate: a duplicate request is evidence of an extra event.
            self.server.events.append(event)
            count = len(self.server.events)
        self.respond(200, {'count': count})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    with CounterServer((args.bind, args.port)) as server:
        print(json.dumps({'fixture_url': 'http://' + args.bind + ':' + str(server.server_port) + server.fixture_path,
                          'phone_navigation_performed': False}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

"""Process/protocol failures, without pretending to validate a physical phone."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from tacto.ios_ax_probe import IOSAXProbe, IOSAXProbeError

DEVICE = '00000000-0000000000000000'
BASE = '''
import json,sys,time
request=json.loads(input())
print(json.dumps({"ok":True,"connection_id":"epoch-1","transport":"coredevice-tunnel","input_enabled":False}),flush=True)
'''


class IOSAXProbeTests(unittest.TestCase):
    def command(self, body):
        return [sys.executable, '-u', '-c', BASE + body]

    def test_same_process_keeps_epoch_for_repeated_capability_reads_then_closes(self):
        command = self.command('''
for line in sys.stdin:
 assert json.loads(line)=={"command":"capabilities"}
 print(json.dumps({"ok":True,"selectors":["deviceCapabilities"],"input_enabled":False}),flush=True)
''')
        with IOSAXProbe(command, DEVICE) as probe:
            self.assertEqual(('deviceCapabilities',), probe.capabilities())
            self.assertEqual(('deviceCapabilities',), probe.capabilities())
            self.assertEqual('epoch-1', probe.connection_id)
        self.assertIsNotNone(probe.process.poll())
        with self.assertRaisesRegex(IOSAXProbeError, 'ios_ax_probe_closed'):
            probe.capabilities()

    def test_hung_native_call_is_killed_and_not_restarted(self):
        probe = IOSAXProbe(self.command('input();time.sleep(30)'), DEVICE, timeout=.1)
        with self.assertRaisesRegex(IOSAXProbeError, 'ios_ax_probe_timeout'):
            probe.capabilities()
        self.assertTrue(probe.closed)
        self.assertIsNotNone(probe.process.poll())

    def test_disconnect_invalidates_session(self):
        probe = IOSAXProbe(self.command('input();sys.exit(0)'), DEVICE)
        with self.assertRaisesRegex(IOSAXProbeError, 'ios_ax_probe_disconnected'):
            probe.capabilities()
        self.assertTrue(probe.closed)

    def test_untrusted_error_text_does_not_escape(self):
        probe = IOSAXProbe(self.command('''
input()
print(json.dumps({"ok":False,"error":"PRIVATE_DEVICE_DATA","stage":"ax_service_socket","reason":"PRIVATE_SCREEN_CONTENT"}),flush=True)
'''), DEVICE)
        with self.assertRaises(IOSAXProbeError) as caught:
            probe.capabilities()
        self.assertEqual('ios_ax_probe_failed', str(caught.exception))
        self.assertEqual('ax_service_socket', caught.exception.stage)
        self.assertIsNone(caught.exception.reason)
        self.assertTrue(probe.closed)

    def test_malformed_oversize_or_input_capable_reply_is_refused(self):
        for output in ['{"ok":true,"selectors":[],"input_enabled":true}',
                       '{"ok":true,"selectors":["devicePerformAction: injected"],"input_enabled":false}',
                       '{"ok":true,"selectors":"wrong type","input_enabled":false}',
                       '{"ok":1,"input_enabled":false}', 'not json', 'x'*66000]:
            with self.subTest(output=output[:40]):
                probe = IOSAXProbe(self.command('input();print('+repr(output)+',flush=True)'), DEVICE)
                with self.assertRaisesRegex(IOSAXProbeError, 'ios_ax_probe_protocol_invalid'):
                    probe.capabilities()
                self.assertTrue(probe.closed)

    def test_configuration_requires_explicit_device_and_transport(self):
        for device, transport in [('', 'coredevice-tunnel'), (DEVICE, 'auto'), (DEVICE, 'usb')]:
            with self.assertRaisesRegex(IOSAXProbeError, 'configuration_invalid'):
                IOSAXProbe(['this executable must never start'], device, transport=transport)

    def test_diagnostic_process_does_not_inherit_framework_overrides(self):
        command = [sys.executable, '-u', '-c', '''
import os,json,sys
assert 'DEVELOPER_DIR' not in os.environ
assert not any(key.startswith('DYLD_') for key in os.environ)
request=json.loads(input())
print(json.dumps({"ok":True,"connection_id":"epoch-1","transport":request['transport'],"input_enabled":False}),flush=True)
for line in sys.stdin:
 print(json.dumps({"ok":True,"selectors":[],"input_enabled":False}),flush=True)
''']
        with patch.dict(os.environ, {'DEVELOPER_DIR':'/PRIVATE/Xcode', 'DYLD_FRAMEWORK_PATH':'/PRIVATE'}):
            with IOSAXProbe(command, DEVICE, transport='mobiledevice-lockdown') as probe:
                self.assertEqual((), probe.capabilities())

    def test_vendored_mit_sources_match_pinned_manifest(self):
        base = Path(__file__).resolve().parents[1] / 'spike/ios-ax-bridge'
        manifest = json.loads((base/'upstream.json').read_text())
        self.assertEqual('MIT', manifest['license'])
        self.assertEqual('6bf94902f1c30aac712ae594a9a3a08136157a48', manifest['revision'])
        self.assertIn('Copyright (c) 2026 Sunghyun Kim', (base/'THIRD_PARTY_LICENSE.txt').read_text())
        for name, entry in manifest['files'].items():
            self.assertEqual(entry['sha256'], hashlib.sha256((base/name).read_bytes()).hexdigest(), name)

"""Run explicitly against a built spike. Invalid requests never select hardware."""
import json
import os
import subprocess
import unittest

BINARY = os.environ.get('TACTO_IOS_AX_PROBE')


@unittest.skipUnless(BINARY, 'set TACTO_IOS_AX_PROBE to the built development binary')
class IOSAXProbeNativeTests(unittest.TestCase):
    def run_probe(self, data):
        result = subprocess.run([BINARY], input=data, capture_output=True, timeout=3)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(b'PRIVATE', result.stdout + result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_arbitrary_selectors_and_input_requests_are_not_exposed(self):
        for request in [{'command':'invoke','selector':'devicePerformAction:','value':'PRIVATE'},
                        {'command':'tap','x':1,'y':2}, {'command':'capabilities'}]:
            with self.subTest(request=request['command']):
                replies = self.run_probe((json.dumps(request)+'\n{"command":"close"}\n').encode())
                self.assertFalse(replies[0]['ok'])
                self.assertFalse(replies[0]['input_enabled'])
                self.assertEqual('request', replies[0]['stage'])
                self.assertTrue(replies[-1]['closed'])

    def test_open_requires_explicit_valid_udid_and_single_transport(self):
        for device, transport in [('', 'coredevice-tunnel'), ('PRIVATE', 'coredevice-tunnel'),
                                  ('00000000-0000000000000000', 'auto')]:
            replies = self.run_probe((json.dumps({'command':'open','device_id':device,'transport':transport})+'\n').encode())
            self.assertEqual(1, len(replies))
            self.assertFalse(replies[0]['ok'])
            self.assertEqual('request', replies[0]['stage'])

    def test_oversize_record_is_terminal_and_suffix_is_not_reinterpreted(self):
        replies = self.run_probe(b'x'*4097 + b'\n{"command":"close"}\n')
        self.assertEqual(1, len(replies))
        self.assertFalse(replies[0]['ok'])

    def test_invalid_encoding_and_incomplete_record_are_rejected(self):
        for data in [b'\xff\n', b'{"command":"capabilities"}']:
            replies = self.run_probe(data)
            self.assertEqual(1, len(replies))
            self.assertFalse(replies[0]['ok'])

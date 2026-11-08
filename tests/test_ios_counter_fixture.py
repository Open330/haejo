"""HTTP receiving tests only, not physical AX/HID validation."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('ios_counter_fixture',
    Path(__file__).resolve().parents[1] / 'spike/ios-ax-bridge/counter_fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class IOSCounterFixtureTests(unittest.TestCase):
    def setUp(self):
        self.server = fixture.CounterServer(('127.0.0.1', 0))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.root = 'http://127.0.0.1:' + str(self.server.server_port) + self.server.fixture_path

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def state(self):
        with urlopen(self.root + 'state', timeout=2) as response:
            return json.load(response)

    def event(self, **overrides):
        data = dict(sequence=1, trusted=True, pointer_type='touch', **overrides)
        with urlopen(Request(self.root+'event', data=json.dumps(data).encode(),
                             headers={'Content-Type': 'application/json'}), timeout=2) as response:
            return json.load(response)

    def test_one_event_then_duplicate_is_visible_as_two(self):
        self.assertEqual(0, self.state()['count'])
        self.assertEqual(1, self.event()['count'])
        self.assertTrue(self.state()['exactly_one_received'])
        self.assertEqual(2, self.event()['count'])
        self.assertFalse(self.state()['exactly_one_received'])
        self.assertEqual([1, 1], self.state()['sequences'])
        self.assertEqual(['touch', 'touch'], self.state()['pointer_types'])
        with urlopen(self.root, timeout=2) as response:
            self.assertIn(b'>Counter 2<', response.read())

    def test_reading_and_loading_page_never_increments(self):
        for _ in range(2):
            with urlopen(self.root, timeout=2) as response:
                self.assertIn(b'tacto-counter-increment', response.read())
            self.assertEqual(0, self.state()['count'])

    def test_invalid_or_unknown_fixture_is_refused_without_increment(self):
        for body in [{'sequence':1, 'trusted':False, 'pointer_type':'touch'}, {}, []]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.root+'event', data=json.dumps(body).encode()), timeout=2)
            self.assertEqual(400, caught.exception.code)
            caught.exception.close()
        self.assertEqual(0, self.state()['count'])
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.root.replace(self.server.token, 'wrong-token')+'state', timeout=2)
        self.assertEqual(404, caught.exception.code)
        caught.exception.close()

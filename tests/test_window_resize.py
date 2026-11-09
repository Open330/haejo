"""Window resize chooses one observed target and reports receiving proof precisely."""
import contextlib
import io
import unittest
from haejo.window_resize import main


class Driver:
    capabilities = {'action.resize_window'}

    def __init__(self, reply=None, tree=None):
        self.calls = []
        self.tree = tree or '0 Window Title: "Now Playing Overlay"\n1 Window Title: "Main"'
        self.reply = reply if reply is not None else {'type': 'acted', 'size_verified': True}

    def observe(self, *args):
        return {'type': 'observation', 'obs_id': 'fresh', 'tree': self.tree}

    def act(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.reply


class WindowResizeTests(unittest.TestCase):
    def run_resize(self, driver, window=True):
        args = ['owned.app', '--helper', '--width', '600', '--height', '360']
        if window:
            args += ['--window', 'Now Playing Overlay']
        with contextlib.redirect_stdout(io.StringIO()):
            return main(args, driver)

    def test_exact_window_and_one_write(self):
        driver = Driver()
        self.assertEqual(0, self.run_resize(driver))
        self.assertEqual(1, len(driver.calls))
        args, kwargs = driver.calls[0]
        self.assertEqual(('fresh', 'owned.app', {'name': 'resize_window', 'element_index': 0,
                                               'width': 600, 'height': 360}), args)
        self.assertTrue(kwargs['approved'])

    def test_ambiguity_or_old_helper_sends_nothing(self):
        driver = Driver()
        self.assertEqual(1, self.run_resize(driver, window=False))
        self.assertFalse(driver.calls)
        driver.capabilities = set()
        self.assertEqual(1, self.run_resize(driver))
        self.assertFalse(driver.calls)

    def test_unsupported_or_uncertain_resize_is_never_retried_or_claimed_verified(self):
        for reply in ({'type': 'error', 'error': 'resize_unavailable', 'effect': 'not_started'},
                      {'type': 'error', 'error': 'resize_not_verified', 'effect': 'unknown'},
                      {'type': 'acted'}):
            driver = Driver(reply)
            self.assertEqual(1, self.run_resize(driver))
            self.assertEqual(1, len(driver.calls))

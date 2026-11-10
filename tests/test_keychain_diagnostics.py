"""Keychain failures name an actionable cause instead of one generic error."""
import ctypes
import unittest

from haejo.credential_diagnostics import recovery
from haejo.credential_vault import keychain_error, keychain_state


class KeychainErrorMappingTests(unittest.TestCase):
    def test_interaction_refused_in_screen_session_means_locked(self):
        error = keychain_error(-25308, 'keychain_write_failed', state=lambda: {'gui_session': True})
        self.assertEqual('keychain_locked', error.code)

    def test_interaction_refused_outside_screen_session_names_the_session(self):
        error = keychain_error(-25308, 'keychain_write_failed', state=lambda: {'gui_session': False})
        self.assertEqual('keychain_session_unavailable', error.code)

    def test_cancelled_or_denied_dialog_is_access_denied(self):
        for status in (-128, -25293):
            self.assertEqual('keychain_access_denied', keychain_error(status, 'keychain_write_failed').code)

    def test_missing_item_and_unknown_status_keep_their_codes(self):
        self.assertEqual('keychain_item_unavailable', keychain_error(-25300, 'keychain_delete_failed').code)
        self.assertEqual('keychain_write_failed', keychain_error(-1, 'keychain_write_failed').code)

    def test_every_new_code_has_a_specific_repair_hint(self):
        for code, reason in (('keychain_locked', 'keychain_locked'),
                             ('keychain_session_unavailable', 'keychain_needs_screen_session'),
                             ('keychain_access_denied', 'keychain_access_denied')):
            self.assertEqual(reason, recovery(code)['reason'])


class _FakeSecurity:
    """SessionGetInfo / SecKeychain* stand-ins; writes through ctypes byref."""
    def __init__(self, attributes, flags):
        self.attributes, self.flags = attributes, flags
        self.SessionGetInfo = self._session
        self.SecKeychainCopyDefault = self._copy
        self.SecKeychainGetStatus = self._status

    def _session(self, _caller, session, attributes):
        ctypes.cast(attributes, ctypes.POINTER(ctypes.c_uint32))[0] = self.attributes
        return 0

    def _copy(self, keychain):
        ctypes.cast(keychain, ctypes.POINTER(ctypes.c_void_p))[0] = 1
        return 0

    def _status(self, _keychain, flags):
        ctypes.cast(flags, ctypes.POINTER(ctypes.c_uint32))[0] = self.flags
        return 0


@unittest.skipUnless(__import__('sys').platform == 'darwin', 'macOS Security session flags')
class KeychainStateTests(unittest.TestCase):
    def test_shell_without_graphic_access_is_not_a_screen_session(self):
        state = keychain_state(release=lambda _ref: None, api=_FakeSecurity(0x5020, 0))
        self.assertEqual({'available': False, 'gui_session': False, 'unlocked': False}, state)

    def test_unlocked_keychain_outside_screen_session_is_usable(self):
        state = keychain_state(release=lambda _ref: None, api=_FakeSecurity(0x5020, 0x7))
        self.assertEqual({'available': True, 'gui_session': False, 'unlocked': True}, state)

    def test_screen_session_with_locked_default_keychain(self):
        state = keychain_state(release=lambda _ref: None, api=_FakeSecurity(0x6030, 0))
        self.assertTrue(state['gui_session'])
        self.assertFalse(state['available'])


if __name__ == '__main__':
    unittest.main()

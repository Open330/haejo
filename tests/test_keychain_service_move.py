"""A credential saved under the pre-1.0 Keychain service moves to the current one on first use."""
import ctypes
import unittest
from types import SimpleNamespace

from haejo.credential_vault import CredentialError, KeychainVault

NOT_FOUND = -25300


class FakeKeychain:
    def __init__(self, items):
        self.items = dict(items)
        self.refs = {}
        self.released = []

    def SecKeychainFindGenericPassword(self, _, service_length, service, key_length, key, length, data, ref):
        found = self.items.get((service, key))
        if found is None:
            return NOT_FOUND
        self.buffer = ctypes.create_string_buffer(found, len(found))
        length._obj.value = len(found)
        data._obj.value = ctypes.addressof(self.buffer)
        handle = len(self.refs) + 1
        self.refs[handle] = (service, key)
        ref._obj.value = handle
        return 0

    def SecKeychainAddGenericPassword(self, _, service_length, service, key_length, key, size, buffer, __):
        if (service, key) in self.items:
            return -25299
        self.items[(service, key)] = buffer.raw[:size]
        return 0

    def SecKeychainItemDelete(self, ref):
        self.items.pop(self.refs[getattr(ref, 'value', ref)], None)
        return 0

    def SecKeychainItemFreeContent(self, *_):
        return 0


def vault(items):
    made = KeychainVault.__new__(KeychainVault)
    made.api = FakeKeychain(items)
    made.cf = SimpleNamespace(CFRelease=lambda ref: made.api.released.append(getattr(ref, 'value', ref)))
    return made


class KeychainServiceMove(unittest.TestCase):
    def test_current_service_carries_no_former_owner_name(self):
        self.assertEqual(b'open330.haejo.credentials', KeychainVault.service)

    def test_an_item_under_the_old_service_is_read_and_moved(self):
        store = vault({(KeychainVault.legacy_service, b'mail'): '비밀'.encode()})
        self.assertEqual('비밀', store.get('mail'))
        self.assertEqual({(KeychainVault.service, b'mail'): '비밀'.encode()}, store.api.items)
        self.assertEqual('비밀', store.get('mail'))

    def test_the_current_item_wins_and_the_old_one_is_left_alone(self):
        store = vault({(KeychainVault.service, b'mail'): b'new', (KeychainVault.legacy_service, b'mail'): b'old'})
        self.assertEqual('new', store.get('mail'))
        self.assertEqual(2, len(store.api.items))

    def test_an_item_in_neither_place_is_unavailable(self):
        with self.assertRaises(CredentialError) as raised:
            vault({}).get('mail')
        self.assertEqual('keychain_item_unavailable', raised.exception.code)

    def test_new_items_are_written_only_under_the_current_service(self):
        store = vault({})
        store.put('mail', 'value')
        self.assertEqual([(KeychainVault.service, b'mail')], list(store.api.items))


if __name__ == '__main__':
    unittest.main()

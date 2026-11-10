"""Shared Keychain guards for the opt-in native credential tests."""
from haejo.credential_vault import CredentialError, keychain_state


def require_keychain(test):
    """Skip with the actual cause when this process cannot use the keychain.

    A shell outside the Mac's screen session keeps its own keychain lock state;
    a locked keychain is an environment state, not a product failure, and must
    not surface as keychain_write_failed.
    """
    state = keychain_state()
    if state['unlocked']:
        return
    test.skipTest('keychain_locked: unlock the login keychain' if state['gui_session'] else
                  'keychain_session_unavailable: run from a terminal in the Mac screen session '
                  'or run security unlock-keychain in this one')


def discard(vault, item):
    """Cleanup that never hides the test's own failure."""
    try:
        vault.delete(item)
    except CredentialError as error:
        if error.code != 'keychain_item_unavailable':
            raise

import unittest
from unittest.mock import patch
from haejo import onboard

class OnboardingSnapshotTests(unittest.TestCase):
    def test_denied_helper_is_checked_once_without_shared_python_advice(self):
        state={'built':True,'trusted':False,'bundled':True,'path':'/owned/Haejo Helper.app',
               'name':'Haejo Helper','why':'접근성 권한이 필요합니다'}
        lines=[]
        check=onboard.Check('accessibility',False,'accessibility','enable','x-test')
        with patch.object(onboard,'helper_status',side_effect=[state,OSError('Bad file descriptor')]) as status, \
             patch.object(onboard,'check_all',return_value=[check]):
            self.assertFalse(onboard.run(interactive=False,narrate=lines.append))
        status.assert_called_once()
        self.assertNotIn('Bad file descriptor','\n'.join(lines))
        self.assertNotIn('공유 파이썬','\n'.join(lines))
        self.assertIn('접근성 권한이 필요합니다','\n'.join(lines))


class LockedSessionReadinessTests(unittest.TestCase):
    def run_state(self, locked, *, interactive=False, apps=True):
        from types import SimpleNamespace
        state = {'built':True, 'trusted':True, 'bundled':True,
                 'path':'/owned/Haejo Helper.app', 'name':'Haejo Helper', 'screen_capture':True}
        lines = []
        workspace = SimpleNamespace(runningApplications=lambda:([SimpleNamespace(activationPolicy=lambda:0)] if apps else []))
        with patch.object(onboard, 'helper_status', return_value=state), \
             patch.object(onboard, 'check_all', return_value=[]), \
             patch('haejo.session.lock_state', return_value={'locked':locked}), \
             patch('AppKit.NSWorkspace', SimpleNamespace(sharedWorkspace=lambda:workspace)), \
             patch.object(onboard, 'open_settings') as settings, \
             patch.object(onboard, 'request_accessibility') as permission:
            ok = onboard.run(interactive=interactive, narrate=lines.append)
        settings.assert_not_called()
        permission.assert_not_called()
        return ok, '\n'.join(lines)

    def test_locked_desktop_with_visible_apps_is_not_ready_or_a_permission_failure(self):
        ok, text = self.run_state(True, interactive=True)
        self.assertFalse(ok)
        self.assertIn('잠겨', text)
        self.assertNotIn('준비 끝', text)
        self.assertNotIn('설정에서 권한을 켜신 뒤', text)

    def test_unlocked_session_stays_ready_and_unknown_does_not_add_a_blocker(self):
        for locked in (False, None):
            ok, text = self.run_state(locked)
            self.assertTrue(ok)
            self.assertIn('준비 끝', text)

    def test_absent_gui_is_not_reported_as_a_permission_fix(self):
        ok, text = self.run_state(False, apps=False)
        self.assertFalse(ok)
        self.assertIn('화면 세션에 연결한 뒤', text)
        self.assertNotIn('설정에서 권한을 켜신 뒤', text)

    def test_locked_missing_permission_does_not_open_settings_but_unlocked_does(self):
        from types import SimpleNamespace
        workspace = SimpleNamespace(runningApplications=lambda:[SimpleNamespace(activationPolicy=lambda:0)])
        missing = onboard.Check('accessibility',False,'앱 조작 권한','enable','x-owned-settings')
        for locked in (True,False):
            with self.subTest(locked=locked), \
                 patch.object(onboard,'helper_status',return_value={'built':False}), \
                 patch.object(onboard,'check_all',return_value=[missing]), \
                 patch('haejo.session.lock_state',return_value={'locked':locked}), \
                 patch('AppKit.NSWorkspace',SimpleNamespace(sharedWorkspace=lambda:workspace)), \
                 patch.object(onboard,'request_accessibility') as request, \
                 patch.object(onboard,'open_settings') as settings:
                self.assertFalse(onboard.run(interactive=True,narrate=lambda _:None))
                if locked:
                    request.assert_not_called();settings.assert_not_called()
                else:
                    request.assert_called_once_with(prompt=True)
                    settings.assert_called_once_with('x-owned-settings')

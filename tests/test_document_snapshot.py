import hashlib
import unittest
from unittest.mock import Mock

from tacto.document_snapshot import CAPABILITY, REQUIRED, SnapshotDriver, SnapshotUnavailable, TARGET


class Native:
    capabilities = REQUIRED
    def __init__(self):
        self.calls = []
        self.text = 'owned text'
        self.path = None
        self.editing_mode = 'rich_text'
        self.sheets = False
        self.attachments = []
        self.focused = '0 Window Title: "owned" [focused]\n  1 TextArea Value: owned text'
        self.panel = {'type': 'save_panel', 'document_token': 'pin', 'format': 'rtf',
            'directory': '/owned', 'filename': 'new.rtf', 'panel_token': 'panel',
            'authorizes_save': False, 'commit_control': {'obs_id': 'current', 'enabled': True,
                'action': {'name': 'click', 'element_index': 7}}}
        self.on_mode = lambda: None
        self.act = Mock(side_effect=AssertionError('snapshot must not send input'))
        self.document_rtf_export = Mock(side_effect=AssertionError('export is not original source-format evidence'))

    def document_text(self, target, **kwargs):
        self.calls.append(('body', kwargs))
        return {'type': 'document_text', 'document_token': 'pin', 'text': self.text,
                'document_path': self.path, 'text_complete': True}

    def document_attachment_metadata(self, target, token):
        return {'type': 'document_attachment_metadata', 'document_token': token,
                'text_sha256': hashlib.sha256(self.text.encode()).hexdigest(),
                'document_path': self.path, 'sampled_stable': True,
                'occurrences': self.attachments, 'attachment_completeness_verified': False}

    def observe(self, target, *args, **kwargs):
        self.calls.append(('observe', kwargs))
        tree = self.focused
        if self.sheets:
            tree += '\n  2 Sheet Title: Save'
        return {'type': 'observation', 'obs_id': 'current', 'document_token': kwargs.get('document_token'), 'tree': tree}

    def document_mode(self, target, **kwargs):
        self.calls.append(('mode', kwargs))
        self.on_mode()
        return {'type': 'document_mode', 'document_token': 'pin', 'editing_mode': self.editing_mode,
                'edited': True, 'witness': {'source': 'format_menu', 'path': ['Format', 'Make Plain Text']}}

    def save_panel(self, *args, **kwargs):
        self.calls.append(('panel', kwargs))
        return self.panel


class DocumentSnapshotTests(unittest.TestCase):
    def test_commit_snapshot_reads_original_observation_without_observe(self):
        inner = Native()
        result = SnapshotDriver(inner).document_snapshot_for_commit(TARGET,
            document_token='pin', event={'obs_id':'current', 'action':{'name':'click', 'element_index':7}})
        self.assertEqual(inner.panel, result['save_panel'])
        self.assertFalse(any(name == 'observe' for name, _ in inner.calls))
        request = next(kwargs for name, kwargs in inner.calls if name == 'panel')
        self.assertEqual(7, request['commit_element_index'])
        inner.act.assert_not_called()

    def test_explicit_window_pin_is_used_only_initially_then_same_token(self):
        inner = Native()
        driver = SnapshotDriver(inner, source_window=('selected', 9))
        result = driver.document_snapshot(TARGET)
        self.assertEqual({'obs_id': 'selected', 'window_element_index': 9}, inner.calls[0][1])
        self.assertEqual(('body', {'document_token': 'pin'}), inner.calls[-1])
        self.assertEqual('rich_text', result['editing_mode'])
        self.assertFalse(result['source_format_verified'])
        self.assertFalse(result['attachment_fidelity_verified'])
        self.assertNotIn('source_format', result)
        self.assertFalse(result['authorizes_save'])
        inner.act.assert_not_called()
        inner.document_rtf_export.assert_not_called()

    def test_default_source_selects_unique_focused_window_not_first_arbitrary_doc(self):
        inner = Native()
        inner.focused = '0 Window Title: "personal"\n  1 TextArea Value: personal\n4 Window Title: "owned" [focused]\n  5 TextArea Value: owned text'
        # The initial observation selects the explicit window. Scoped reads
        # thereafter must have only the backend-selected window.
        observe = inner.observe
        def scoped(target, *args, **kwargs):
            if kwargs.get('document_token'):
                inner.focused = '0 Window Title: "owned" [focused]\n  1 TextArea Value: owned text'
            return observe(target, *args, **kwargs)
        inner.observe = scoped
        result = SnapshotDriver(inner).document_snapshot(TARGET)
        self.assertEqual('pin', result['document_token'])
        first_body = next(kwargs for name, kwargs in inner.calls if name == 'body')
        self.assertEqual({'obs_id': 'current', 'window_element_index': 4}, first_body)

    def test_source_ambiguity_never_reads_a_body(self):
        inner = Native()
        inner.focused += '\n2 Window Title: "also" [focused]'
        with self.assertRaisesRegex(SnapshotUnavailable, 'snapshot_source_window_ambiguous'):
            SnapshotDriver(inner).document_snapshot(TARGET)
        self.assertFalse(any(kind == 'body' for kind, _ in inner.calls))

    def test_missing_backend_component_is_not_advertised_or_called(self):
        for missing in REQUIRED:
            inner = Native()
            inner.capabilities = REQUIRED - {missing}
            driver = SnapshotDriver(inner)
            self.assertNotIn(CAPABILITY, driver.capabilities)
            with self.assertRaises(SnapshotUnavailable):
                driver.document_snapshot(TARGET)
            self.assertEqual([], inner.calls)

    def test_save_panel_mode_is_labeled_as_ui_mode_not_disk_format(self):
        inner = Native()
        inner.sheets = True
        inner.document_mode = Mock(side_effect=AssertionError('menu need not be read through a modal'))
        result = SnapshotDriver(inner).document_snapshot(TARGET)
        self.assertEqual('save_panel_rtf', result['mode_witness']['source'])
        self.assertEqual(inner.panel, result['save_panel'])
        inner.panel['filename'] = 'changed.rtf'
        self.assertEqual('new.rtf', result['save_panel']['filename'])
        inner.document_mode.assert_not_called()
        inner.act.assert_not_called()

    def test_wrong_panel_token_format_or_authorization_does_not_become_snapshot(self):
        for change in ({'document_token': 'OTHER'}, {'format': 'plain'}, {'authorizes_save': True}):
            inner = Native()
            inner.sheets = True
            inner.panel.update(change)
            with self.assertRaisesRegex(SnapshotUnavailable, 'snapshot_save_panel_unavailable'):
                SnapshotDriver(inner).document_snapshot(TARGET)
            inner.act.assert_not_called()

    def test_document_change_during_mode_read_is_rejected_without_echoing_private_values(self):
        for change in ('text', 'path'):
            inner = Native()
            inner.on_mode = lambda: setattr(inner, change, 'PRIVATE_CHANGED')
            with self.assertRaises(SnapshotUnavailable) as raised:
                SnapshotDriver(inner).document_snapshot(TARGET)
            self.assertEqual('snapshot_document_changed', str(raised.exception))
            self.assertNotIn('PRIVATE', str(raised.exception))
            inner.act.assert_not_called()

    def test_observed_attachments_are_unsupported_not_silently_dropped(self):
        inner = Native()
        inner.attachments = [{'ax_attachment_present': True}]
        with self.assertRaisesRegex(SnapshotUnavailable, 'snapshot_attachment_not_supported'):
            SnapshotDriver(inner).document_snapshot(TARGET)
        inner.act.assert_not_called()

    def test_plain_editing_mode_is_reported_as_plain_even_if_an_rtf_export_would_exist(self):
        inner = Native()
        inner.editing_mode = 'plain_text'
        self.assertEqual('plain_text', SnapshotDriver(inner).document_snapshot(TARGET)['editing_mode'])
        inner.document_rtf_export.assert_not_called()


if __name__ == '__main__':
    unittest.main()

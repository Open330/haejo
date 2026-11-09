"""Host contract tests; these do not attribute kernel writes or launch TextEdit."""
from dataclasses import replace
import unittest

from haejo.commit_evidence import (ArtifactEvidence, CommitEvidence, DocumentSaveEvidence,
    SavedFileStateEvidence, evidence_error, make_event)


class DocumentSaveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.event = make_event({'name':'click', 'element_index':7}, ['write_persistent'],
                                'com.apple.TextEdit', obs_id='current')
        self.detail = DocumentSaveEvidence('receipt', '/owned/new.rtf', 'a'*64,
                                          None, 'b'*64, 'current')
        self.expected = {'artifact_evidence_scope':'document_save',
                         'source_document_path':None, 'document_identity_sha256':'b'*64,
                         '저장 위치':'/owned', '저장한 이름':'new.rtf'}

    def error(self, detail=None, expected=None, event=None):
        event = event or self.event
        return evidence_error({**event, 'commit_evidence':CommitEvidence(event['event_id'],
            event['action_digest'], detail or self.detail)},
            self.expected if expected is None else expected)

    def test_new_document_save_transition_is_bound_to_observation_and_destination(self):
        self.assertIsNone(self.error())
        for patch in ({'observation_id':'old'}, {'source_path':'/other/original.rtf'},
                      {'source_path':'/owned/new.rtf'}, {'document_identity_sha256':'c'*64},
                      {'document_identity_sha256':'not-a-digest'}):
            self.assertEqual('document_save_transition_mismatch', self.error(replace(self.detail, **patch)))
        self.assertEqual('artifact_location_mismatch', self.error(replace(self.detail, path='/other/new.rtf')))

    def test_existing_source_saved_to_a_new_path_is_a_transition(self):
        expected = {**self.expected, 'source_document_path':'/owned/original.rtf'}
        self.assertIsNone(self.error(replace(self.detail, source_path='/owned/original.rtf'), expected))

    def test_file_state_or_generic_artifact_cannot_replace_document_transition(self):
        for kind in (ArtifactEvidence, SavedFileStateEvidence):
            self.assertIsNotNone(self.error(kind('receipt','/owned/new.rtf','a'*64)))
        self.assertEqual('document_save_transition_mismatch', self.error(expected={}))

    def test_transition_cannot_confirm_another_application_or_effect(self):
        for target, action, effects in (
            ('another.editor', {'name':'click','element_index':7}, ['write_persistent']),
            ('com.apple.TextEdit', {'name':'menu','path':['File','Save']}, ['write_persistent']),
            ('com.apple.TextEdit', {'name':'click','element_index':7}, ['write_persistent','transmit'])):
            event = make_event(action, effects, target, obs_id='current')
            self.assertIsNotNone(self.error(event=event))


if __name__ == '__main__':
    unittest.main()

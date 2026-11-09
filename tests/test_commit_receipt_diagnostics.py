import unittest
from haejo.flow import replay
from haejo.library import textedit_save
from haejo.artifact_receipt import ArtifactReceiptError
from haejo.existing_file_receipt import _refuse
class ReceiptDiagnostics(unittest.TestCase):
    def test_snapshot_preparation_preserves_closed_stage_code_without_private_details(self):
        from haejo.document_snapshot import SnapshotUnavailable
        class App:
            capabilities={'action.menu.focused_document'}
            def observe(self,*a,**k):return {'type':'observation','obs_id':'o','tree':'0 Window  Title: note.txt [focused]'}
        flow=textedit_save().bind(document='/tmp/a/note.txt',name='note.txt')
        for code in ('snapshot_save_panel_unavailable','PRIVATE_SENTINEL'):
            def prepare(*args):raise SnapshotUnavailable(code)
            result=replay(App(),flow,approvals={0:True},prepare_commit=prepare)
            expected=code if code!='PRIVATE_SENTINEL' else 'snapshot_backend_unavailable'
            self.assertFalse(result.ok)
            self.assertIn(expected,str(result.log))
            self.assertNotIn('PRIVATE_SENTINEL',str(result.log))
            self.assertEqual([],result.events)

    def test_after_commit_discloses_only_closed_receipt_codes(self):
        class App:
            capabilities={'action.menu.focused_document'}
            def observe(self,*a,**k):return {'type':'observation','obs_id':'o','tree':'0 Window  Title: note.txt [focused]'}
            def act(self,*a,**k):return {'type':'acted'}
            def wait_until(self,*a,**k):return self.observe()
        flow=textedit_save().bind(document='/tmp/a/note.txt',name='note.txt')
        for code,expected in [('text_unavailable','text_unavailable'),([], 'host_commit_evidence_failed'),('PRIVATE_SENTINEL','host_commit_evidence_failed')]:
            def after(*a):
                error=ArtifactReceiptError('PRIVATE_SENTINEL')
                error.public_code=code
                raise error
            result=replay(App(),flow,approvals={0:True},after_commit=after)
            text=str(result.log)
            self.assertIn(expected,text)
            self.assertIn('commit_unverified',text)
            self.assertNotIn('PRIVATE_SENTINEL',text)

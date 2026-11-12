"""Real known-recipe/CLI wiring with a contract fake and temporary RTF files."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
from contextlib import nullcontext, redirect_stdout
import io
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from haejo.agent import Agent
from haejo.library import textedit_save_as
from haejo.trace import Trace, TraceDriver, TracingDriver
from test_replay_commit_evidence import TextEditFixture, MemoryStore


class SnapshotTextEdit(TextEditFixture):
    capabilities = {'evidence.document_snapshot', 'action.click.save_panel_guard'}
    def __init__(self, directory):
        super().__init__()
        self.directory=directory
        self.document_path=None
        self.snapshot_calls=[]
        self.body='hello'
        self.change_body_on_menu=False
        self.guarded_clicks=[]
    def document_snapshot(self, target, document_token=None):
        self.snapshot_calls.append((document_token,self.sheet,self.clicks))
        return dict(type='document_snapshot',document_token='document-1',
                    text=self.body,text_complete=True,document_path=self.document_path,
                    editing_mode='rich_text', save_panel=(dict(panel_token='panel-1', document_token='document-1',
                    directory=str(self.directory), filename=self.name, format='rtf',
                    commit_control={'obs_id': 'obs', 'enabled': True,
                                    'action': {'name': 'click', 'element_index': 5}})
                    if self.sheet else None))
    def act(self, obs_id, target, action, **kwargs):
        if action['name']=='click':
            if kwargs.get('save_panel_token')!='panel-1' or kwargs.get('approved') is not True:
                return {'type':'error','error':'save_panel_guard_unavailable','effect':'not_started'}
            self.guarded_clicks.append(kwargs['save_panel_token'])
        out=super().act(obs_id,target,action,**kwargs)
        if action['name']=='menu' and self.change_body_on_menu:self.body='changed'
        if action['name']=='click':
            path=self.directory/self.name
            path.write_bytes(b'{\\rtf1\\ansi hello}')
            self.document_path=str(path)
        return out


class AgentTextEditReceiptTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.home=Path(temp.name).resolve()
        self.directory=self.home/'Downloads';self.directory.mkdir(mode=0o700)
        self.d=SnapshotTextEdit(self.directory)
        self.patch=patch('pathlib.Path.home',return_value=self.home)
        self.patch.start();self.addCleanup(self.patch.stop)
    def test_agent_known_save_creates_receipt_before_ui_and_preserves_plain_text(self):
        turn=Agent(driver=self.d,store=MemoryStore()).handle('"보고서.rtf" 로 저장해줘',ask=lambda _:True)
        self.assertEqual('done',turn.status,turn)
        self.assertEqual(1,self.d.clicks)
        self.assertEqual(self.d.guarded_clicks,['panel-1'])
        self.assertEqual((None,False,0),self.d.snapshot_calls[0])
        self.assertTrue((self.directory/'보고서.rtf').exists())
    def test_traced_native_commit_snapshot_preserves_dynamic_observation_identity(self):
        from haejo.document_snapshot import REQUIRED
        class Primitives(SnapshotTextEdit):
            capabilities = REQUIRED
            document_snapshot = None
            def observe(self, *args, **kwargs):
                observation = super().observe(*args, **kwargs)
                self.observation_number = getattr(self, 'observation_number', 0) + 1
                observation['obs_id'] = f'obs-{self.observation_number}'
                observation['document_token'] = kwargs.get('document_token')
                return observation
            def document_text(self, target, **kwargs):
                self.body_reads = getattr(self, 'body_reads', 0) + 1
                return dict(type='document_text', document_token='document-1',
                    text=self.body, text_complete=True, document_path=self.document_path)
            def document_attachment_metadata(self, target, token, *, max_utf16_units=100000, timeout_seconds=3):
                self.attachment_reads = getattr(self, 'attachment_reads', 0) + 1
                return dict(type='document_attachment_metadata', document_token=token,
                    document_path=self.document_path, sampled_stable=True, occurrences=[],
                    text_sha256=hashlib.sha256(self.body.encode()).hexdigest())
            def document_mode(self, target, **kwargs):
                self.mode_reads = getattr(self, 'mode_reads', 0) + 1
                return dict(type='document_mode', document_token='document-1',
                    editing_mode='rich_text', witness={'source':'format_menu'}, edited=True)
            def save_panel(self, *args, **kwargs):
                if args[0] != f'obs-{self.observation_number}':
                    return {'type':'error', 'error':'observation_expired'}
                if kwargs.get('commit_element_index') != 5:
                    return {'type':'error', 'error':'wrong_commit_control'}
                return dict(type='save_panel', document_token='document-1', format='rtf',
                    directory=str(self.directory), filename=self.name, panel_token='panel-1',
                    authorizes_save=False, commit_control={'obs_id':f'obs-{self.observation_number}', 'enabled':True,
                        'action':{'name':'click', 'element_index':5}})
        native = Primitives(self.directory)
        trace = Trace()
        turn = Agent(driver=TracingDriver(native, trace), store=MemoryStore()).handle('"보고서.rtf" 로 저장해줘', ask=lambda _:True)
        self.assertEqual('done', turn.status, turn)
        self.assertEqual(['panel-1'], native.guarded_clicks)
        self.assertEqual(1, native.clicks)
        self.assertTrue((self.directory/'보고서.rtf').exists())
        self.assertEqual([], native.snapshot_calls)
        self.assertEqual(2, native.attachment_reads)  # initial + commit, never readback polling
        self.assertEqual(1, native.mode_reads)  # initial only; commit uses its existing panel
        self.assertEqual(5, native.body_reads)  # two snapshots + one post-save pin read
        self.assertFalse(any(event['kind'].startswith('document_') or event['kind']=='save_panel'
                             for event in trace.events))
    def test_existing_file_or_document_change_stops_before_save_click(self):
        path=self.directory/'보고서.rtf';path.write_bytes(b'original')
        agent=Agent(driver=self.d,store=MemoryStore())
        turn=agent.handle('"보고서.rtf" 로 저장해줘',ask=lambda _:True)
        self.assertEqual('failed',turn.status)
        self.assertEqual(0,self.d.clicks)
        self.assertFalse(self.d.sheet)
        self.assertEqual(b'original',path.read_bytes())
        path.unlink();self.d.change_body_on_menu=True
        turn=agent.handle('"보고서.rtf" 로 저장해줘',ask=lambda _:True)
        self.assertNotEqual('done',turn.status)
        self.assertEqual(0,self.d.clicks)
        self.assertFalse(path.exists())
    def test_matching_name_with_changed_recipe_cannot_get_builtin_receipt(self):
        f=textedit_save_as().bind(filename='보고서.rtf',folder='Downloads')
        f.steps[0].intent_text='changed recipe'
        self.assertIsNone(Agent(driver=self.d).commit_adapter_for(f))
        self.assertEqual([],self.d.snapshot_calls)
    def test_unsupported_automatic_receipt_does_not_block_existing_recipe_or_read_body(self):
        for name, folder in (('note.txt','Downloads'), ('보고서.rtf','Desktop')):
            with self.subTest(name=name, folder=folder):
                flow=textedit_save_as().bind(filename=name, folder=folder)
                self.assertIsNone(Agent(driver=self.d).commit_adapter_for(flow))
                self.assertEqual([],self.d.snapshot_calls)
    def test_cli_replay_and_live_trace_use_receipt_but_recording_cannot_issue_one(self):
        from haejo.cli import _run_flow
        d=TracingDriver(self.d,Trace())
        f=textedit_save_as().bind(filename='보고서.rtf',folder='Downloads')
        with patch('haejo.cli._make_driver',return_value=d), \
             patch('haejo.cli._indicator_for',return_value=nullcontext()), \
             patch('haejo.cli._confirmer',return_value=lambda _:True),redirect_stdout(io.StringIO()):
            self.assertEqual(0,_run_flow(f,[]))
        self.assertEqual(1,self.d.clicks)
        self.assertTrue(self.d.snapshot_calls)
        self.assertNotIn('evidence.document_snapshot',TraceDriver(d.trace).capabilities)
        self.assertNotIn('action.click.save_panel_guard',TraceDriver(d.trace).capabilities)
        self.assertFalse(any(e.get('kind')=='document_snapshot' for e in d.trace.events))
        self.assertFalse(any(e.get('request',{}).get('action',{}).get('name')=='click'
                             for e in d.trace.events))

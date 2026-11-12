"""Goal-scoped task grouping: lifecycle, binding, fail-closed admission."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from haejo import task as tasks
from haejo import cli


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)/'Haejo'/'Tasks'
        self.patch = patch.object(tasks, 'tasks_root', lambda root=None: Path(root) if root else self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def run_cli(self, *argv, env=None):
        out = io.StringIO()
        with patch.dict(os.environ, env or {}, clear=False), redirect_stdout(out):
            if 'HAEJO_TASK' not in (env or {}):
                os.environ.pop('HAEJO_TASK', None)
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_start_status_end_roundtrip_private(self):
        meta = tasks.start('계산기로 12×34 계산하기')
        self.assertRegex(meta['id'], tasks.TASK_ID)
        directory = self.root/meta['id']
        if os.name != 'nt':
            self.assertEqual(0o700, directory.stat().st_mode & 0o777)
            self.assertEqual(0o600, (directory/'task.json').stat().st_mode & 0o777)
            self.assertEqual(0o600, (directory/'events.jsonl').stat().st_mode & 0o777)
        report = tasks.status(meta['id'])
        self.assertEqual(('open', '계산기로 12×34 계산하기', []), (report['state'], report['goal'], report['invocations']))
        tasks.end(meta['id'], 'done')
        self.assertEqual(('closed', 'done'), (tasks.status(meta['id'])['state'], tasks.status(meta['id'])['result']))
        with self.assertRaises(tasks.TaskRefused) as cm:
            tasks.end(meta['id'], 'done')
        self.assertEqual('task_closed', cm.exception.code)

    def test_invalid_goal_and_ids(self):
        for goal in ('', '   ', 'a\nb', 'x' * 1001):
            with self.assertRaises(tasks.TaskRefused):
                tasks.start(goal)
        for bad in ('../x', 't-123', 't-' + 'g' * 24, 'T-' + 'a' * 24, '/etc'):
            with self.assertRaises(tasks.TaskRefused) as cm:
                tasks.bind(bad, 'observe')
            self.assertEqual('task_invalid', cm.exception.code)
        with self.assertRaises(tasks.TaskRefused) as cm:
            tasks.bind('t-' + 'a' * 24, 'observe')
        self.assertEqual('task_unknown', cm.exception.code)

    def test_two_independent_invocations_and_states(self):
        task_id = tasks.start('goal')['id']
        first = tasks.bind(task_id, 'observe'); first.admit('haejo-x.jsonl')
        second = tasks.bind(task_id, 'run'); second.admit()
        first.finish(0)
        class Log:
            targets = {'com.apple.calculator', 'not a bundle'}
            last_failure = {'error': 'target_missing', 'stage': 'resolve'}
        second.finish(1, Log())
        third = tasks.bind(task_id, 'run'); third.admit()   # never ends; this pid is alive
        report = tasks.status(task_id)
        self.assertEqual({'ok': 1, 'failed': 1, 'in_flight': 1, 'uncertain': 0}, report['counts'])
        inv = report['invocations']
        self.assertEqual(['observe', 'run', 'run'], [i['command'] for i in inv])
        self.assertEqual('haejo-x.jsonl', inv[0]['access_log'])
        self.assertEqual((['com.apple.calculator'], 'target_missing', 'resolve'),
                         (inv[1]['targets'], inv[1]['error'], inv[1]['stage']))

    def test_closed_task_refuses_admission_but_inflight_may_finish(self):
        task_id = tasks.start('goal')['id']
        running = tasks.bind(task_id, 'run'); running.admit()
        late = tasks.bind(task_id, 'observe')     # bound before end, admitted after: the race
        tasks.end(task_id, 'abandoned')
        with self.assertRaises(tasks.TaskRefused):
            tasks.bind(task_id, 'observe')
        with self.assertRaises(tasks.TaskRefused) as cm:
            late.admit()
        self.assertEqual('task_closed', cm.exception.code)
        running.finish(0)
        self.assertEqual(1, tasks.status(task_id)['counts']['ok'])

    def test_uncertain_and_damaged_records(self):
        task_id = tasks.start('goal')['id']
        b = tasks.bind(task_id, 'run'); b.admit()
        events = self.root/task_id/'events.jsonl'
        rows = [json.loads(l) for l in events.read_text().splitlines()]
        rows[-1]['pid'] = 2**31 - 2          # a process that is gone
        events.write_text(''.join(json.dumps(r) + '\n' for r in rows) + '{"event":"invoc')
        report = tasks.status(task_id)
        self.assertEqual(1, report['counts']['uncertain'])
        self.assertEqual(1, report['damaged_records'])
        # Admission after the torn tail must not be swallowed by it.
        after = tasks.bind(task_id, 'observe'); after.admit(); after.finish(0)
        report = tasks.status(task_id)
        self.assertEqual((1, 1, 1), (report['counts']['ok'], report['counts']['uncertain'], report['damaged_records']))
        self.assertEqual(['run', 'observe'], [i['command'] for i in report['invocations']])

    def test_symlinked_task_directory_refused(self):
        task_id = tasks.start('goal')['id']
        other = Path(self.tmp.name)/'elsewhere'; other.mkdir()
        fake = 't-' + 'b' * 24
        os.symlink(other, self.root/fake)
        with self.assertRaises(OSError):
            tasks.bind(fake, 'observe').admit()
        self.assertEqual([task_id], [r['id'] for r in tasks.list_tasks()])

    def test_concurrent_admission_keeps_every_record(self):
        task_id = tasks.start('goal')['id']
        def worker():
            for _ in range(20):
                b = tasks.bind(task_id, 'observe'); b.admit(); b.finish(0)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        report = tasks.status(task_id)
        self.assertEqual((80, 80, 0), (len(report['invocations']), report['counts']['ok'], report['damaged_records']))

    # ------------------------------------------------------------ CLI binding

    def test_bad_binding_refuses_before_any_screen_work(self):
        closed = tasks.start('goal')['id']; tasks.end(closed, 'done')
        cases = [(['observe', 'com.apple.calculator', '--task', 'nope'], {}, 'task_invalid'),
                 (['observe', 'com.apple.calculator'], {'HAEJO_TASK': 't-' + 'c' * 24}, 'task_unknown'),
                 (['observe', 'com.apple.calculator', '--task', closed], {}, 'task_closed'),
                 (['run', 'f.json', '--task'], {}, 'task_invalid')]
        for argv, env, code in cases:
            with patch.object(cli, '_main', side_effect=AssertionError('screen work started')), \
                 patch('haejo.access_log.AccessLog', side_effect=AssertionError('logged before refusal')):
                exit_code, out = self.run_cli(*argv, env=env)
            self.assertEqual(2, exit_code, argv)
            self.assertIn(code, out)

    def test_flag_wins_over_env_and_is_stripped(self):
        mine = tasks.start('mine')['id']; other = tasks.start('other')['id']
        seen = {}
        def fake_main(argv):
            seen['argv'] = argv; seen['task'] = tasks.current.get().task_id
            return 0
        with patch.object(cli, '_main', side_effect=fake_main), \
             patch('haejo.access_log.log_directory', lambda: Path(self.tmp.name)/'Logs'):
            code, _ = self.run_cli('observe', 'com.apple.calculator', '--task', mine, env={'HAEJO_TASK': other})
        self.assertEqual((0, ['observe', 'com.apple.calculator'], mine), (code, seen['argv'], seen['task']))
        self.assertEqual(1, len(tasks.status(mine)['invocations']))
        self.assertEqual(0, len(tasks.status(other)['invocations']))
        log = next((Path(self.tmp.name)/'Logs').glob('haejo-*.jsonl'))
        start = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(mine, start['task_id'])
        self.assertEqual(tasks.status(mine)['invocations'][0]['invocation'], start['invocation_id'])
        self.assertEqual(log.name, tasks.status(mine)['invocations'][0]['access_log'])

    def test_exception_records_failed_end(self):
        task_id = tasks.start('goal')['id']
        with patch.object(cli, '_main', side_effect=RuntimeError('boom')), \
             patch('haejo.access_log.log_directory', lambda: Path(self.tmp.name)/'Logs'):
            with self.assertRaises(RuntimeError):
                self.run_cli('run', 'x.json', env={'HAEJO_TASK': task_id})
        self.assertEqual(1, tasks.status(task_id)['counts']['failed'])

    def test_non_screen_commands(self):
        task_id = tasks.start('goal')['id']
        with patch.object(cli, '_main', return_value=0):
            code, out = self.run_cli('list', '--task', task_id)
            self.assertEqual(2, code); self.assertIn('task_not_applicable', out)
            code, _ = self.run_cli('list', env={'HAEJO_TASK': task_id})   # ambient env is ignored there
            self.assertEqual(0, code)
        self.assertEqual([], tasks.status(task_id)['invocations'])

    def test_task_cli_recovers_with_closed_env_and_never_guesses(self):
        code, out = self.run_cli('task', 'start', '파일 저장', '--json')
        task_id = json.loads(out)['task_id']
        code, out = self.run_cli('task', 'status')
        self.assertEqual(2, code); self.assertIn('never guesses', out)
        code, out = self.run_cli('task', 'end', '--result', 'done', env={'HAEJO_TASK': task_id})
        self.assertEqual(0, code)
        code, out = self.run_cli('task', 'status', '--json', env={'HAEJO_TASK': task_id})
        self.assertEqual((0, 'closed'), (code, json.loads(out)['state']))
        code, out = self.run_cli('task', 'list', '--all')
        self.assertIn(task_id, out)

    def test_help_token_as_argument_value_stays_bound(self):
        with patch.object(cli, '_main', side_effect=AssertionError('screen work started')):
            code, out = self.run_cli('activate', 'com.apple.TextEdit', '--window', 'help', '--helper',
                                     env={'HAEJO_TASK': 'invalid'})
        self.assertEqual(2, code); self.assertIn('task_invalid', out)
        with patch.object(cli, '_main', return_value=0) as fake:
            code, _ = self.run_cli('run', '--help', env={'HAEJO_TASK': 'invalid'})
        self.assertEqual(0, code); fake.assert_called_once()

    def test_parallel_children_get_validated_task(self):
        task_id = tasks.start('goal')['id']
        binding = tasks.bind(task_id, 'parallel')
        token = tasks.current.set(binding)
        try:
            self.assertEqual({'HAEJO_TASK': task_id, 'HAEJO_TASK_PARENT': binding.invocation}, binding.child_env())
            child = tasks.bind(task_id, 'session', environ=binding.child_env())
            self.assertEqual(binding.invocation, child.parent)
        finally:
            tasks.current.reset(token)
        self.assertIsNone(tasks.bind(task_id, 'session', environ={'HAEJO_TASK_PARENT': '../x'}).parent)

    # ------------------------------------------------------------ flows and steps

    def test_flow_runs_are_recorded_once_with_source(self):
        task_id = tasks.start('goal')['id']
        b = tasks.bind(task_id, 'session'); token = tasks.current.set(b)
        try:
            tasks.note_flow('ignored-before-admit')
            b.admit()
            tasks.note_flow('calc_multiply')              # a built-in recipe
            tasks.note_flow('calc_multiply')              # nested replay: once
            tasks.note_flow('my_saved', 'library')
            tasks.note_flow('from-file', 'file')
            tasks.note_flow('a b\n/../x')                 # not a recipe label
            tasks.note_flow('calc_multiply:clear_first')  # a recovery of a kept recipe
            for n in range(40):
                tasks.note_flow(f'f{n}', 'inline')
            b.finish(0)
            tasks.note_flow('after-end', 'inline')
        finally:
            tasks.current.reset(token)
        tasks.note_flow('unbound')                         # no task: no-op
        flows = tasks.status(task_id)['invocations'][0]['flows']
        self.assertEqual(tasks.MAX_FLOWS, len(flows))
        import hashlib
        ref = lambda n: hashlib.sha256(n.encode()).hexdigest()[:12]
        self.assertEqual([{'name': 'calc_multiply', 'ref': None, 'source': 'builtin'},
                          {'name': 'my_saved', 'ref': None, 'source': 'library'},
                          {'name': None, 'ref': ref('from-file'), 'source': 'file'},
                          {'name': None, 'ref': ref('a b\n/../x'), 'source': 'inline'},
                          {'name': 'calc_multiply:clear_first', 'ref': None, 'source': 'builtin'}], flows[:5])
        raw = (self.root/task_id/'events.jsonl').read_text()
        self.assertNotIn('from-file', raw); self.assertNotIn('../x', raw)
        text = tasks._format_status(tasks.status(task_id))
        self.assertIn('flow=calc_multiply[builtin]', text)
        self.assertIn(f"flow=#{ref('from-file')}[file]", text)
        # A damaged row must not take status down.
        with open(self.root/task_id/'events.jsonl', 'a') as fh:
            fh.write(json.dumps({'event': 'invocation_flow', 'invocation': ['x']}) + '\n')
            fh.write(json.dumps({'event': 'invocation_end', 'invocation': {'a': 1}}) + '\n')
        self.assertEqual(tasks.MAX_FLOWS, len(tasks.status(task_id)['invocations'][0]['flows']))

    def test_replay_engine_and_cli_run_note_the_flow(self):
        from haejo.flow import Flow
        task_id = tasks.start('goal')['id']
        path = Path(self.tmp.name)/'mine.json'
        path.write_text(Flow(name='typed_note', target='com.apple.TextEdit').to_json())
        seen = []
        def fake_run_flow(flow, argv, walked=False, **kw):
            from haejo import flow as engine
            class Nothing:
                def __getattr__(self, name): raise AttributeError(name)
            try:
                engine.replay(Nothing(), flow)      # the note comes before any driver use
            except AttributeError:
                pass
            seen.append(flow.name)
            return 0
        with patch.object(cli, '_run_flow', side_effect=fake_run_flow), \
             patch('haejo.access_log.log_directory', lambda: Path(self.tmp.name)/'Logs'):
            code, _ = self.run_cli('run', str(path), env={'HAEJO_TASK': task_id})
        import hashlib
        self.assertEqual((0, ['typed_note']), (code, seen))
        self.assertEqual([{'name': None, 'ref': hashlib.sha256(b'typed_note').hexdigest()[:12], 'source': 'file'}],
                         tasks.status(task_id)['invocations'][0]['flows'])
        # A flow refused at parameter binding never ran, so it is not noted.
        with patch.object(Flow, 'bind', side_effect=ValueError('missing')), \
             patch.object(cli, '_run_flow', side_effect=AssertionError('ran')), \
             patch('haejo.access_log.log_directory', lambda: Path(self.tmp.name)/'Logs'):
            code, _ = self.run_cli('run', str(path), '-p', 'n=1', env={'HAEJO_TASK': task_id})
        self.assertEqual(2, code)
        self.assertEqual([], tasks.status(task_id)['invocations'][1]['flows'])
        self.assertEqual(1, len(tasks.status(task_id)['invocations'][0]['flows']))

    def test_legacy_parallel_notes_flows_on_the_caller_thread(self):
        from haejo import parallel
        from haejo.flow import Flow
        task_id = tasks.start('goal')['id']
        b = tasks.bind(task_id, 'parallel'); b.admit(); token = tasks.current.set(b)
        class FakeDriver:
            def _resolve(self, target, launch=False): return target
        try:
            with patch.object(parallel, 'Driver', FakeDriver), \
                 patch.object(parallel, 'replay', lambda d, f, approvals=None: type('R', (), {'ok': True})()):
                parallel.run_parallel([Flow(name='left', target='a.b'), Flow(name='right', target='c.d')])
        finally:
            tasks.current.reset(token)
        import hashlib
        self.assertEqual({hashlib.sha256(n).hexdigest()[:12] for n in (b'left', b'right')},
                         {f['ref'] for f in tasks.status(task_id)['invocations'][0]['flows']})

    def test_status_steps_reads_only_the_matching_receipt(self):
        task_id = tasks.start('goal')['id']
        logs = Path(self.tmp.name)/'Logs'
        with patch('haejo.access_log.log_directory', lambda: logs):
            from haejo.access_log import AccessLog
            b = tasks.bind(task_id, 'observe')
            log = AccessLog('observe', root=logs, task=b)
            b.admit(log.path.name)
            log.event('access_start', operation='act', target='com.apple.calculator', action='click')
            log.event('access_end', operation='act', target='com.apple.calculator', action='click', type='acted')
            log.task_result({'status': 'failed', 'error': 'target_missing', 'stage': 'resolve'})
            log.finish(1); log.close(); b.finish(1, log)
            other = tasks.bind(task_id, 'run'); other.admit(log.path.name)   # names someone else's log
            other.finish(0)
            gone = tasks.bind(task_id, 'run'); gone.admit('haejo-20260101T000000000000Z-' + 'a' * 32 + '.jsonl')
            gone.finish(0)
            code, out = self.run_cli('task', 'status', task_id, '--steps', '--json')
            code2, text = self.run_cli('task', 'status', task_id, '--steps')
        self.assertEqual((0, 0), (code, code2))
        inv = json.loads(out)['invocations']
        self.assertEqual([{'event': 'access_end', 'operation': 'act', 'target': 'com.apple.calculator',
                           'action': 'click', 'type': 'acted'},
                          {'event': 'task_result', 'status': 'failed', 'error': 'target_missing', 'stage': 'resolve'}],
                         [{k: v for k, v in s.items() if k != 'elapsed_ms'} for s in inv[0]['steps']['steps']])
        self.assertEqual(['access_log_mismatch', 'access_log_removed'],
                         [inv[1]['steps']['reason'], inv[2]['steps']['reason']])
        self.assertIn('act:click com.apple.calculator acted', text)
        code, _ = self.run_cli('task', 'status', task_id, '--bogus')
        self.assertEqual(2, code)


if __name__ == '__main__':
    unittest.main()


class LauncherEnvironmentTests(unittest.TestCase):
    def test_signed_launcher_forwards_task_binding(self):
        # The launcher passes an allowlisted environment to Python; a task
        # binding that is not on it never reaches cli.main (found on rc.27).
        import re
        source = (Path(__file__).resolve().parent.parent/'launcher/haejo.swift').read_text()
        allowed = re.search(r'let allowedEnv = \[(.*?)\]', source, re.S).group(1)
        for name in ('HAEJO_TASK', 'HAEJO_TASK_PARENT'):
            self.assertIn(f'"{name}"', allowed)

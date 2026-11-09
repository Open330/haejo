"""Inline lifecycle removes bookkeeping calls without changing UI outcomes."""
import json,unittest
from unittest.mock import patch
from haejo import cli,task as tasks
from tests import test_task as fixture

class InlineTaskTests(unittest.TestCase):
    setUp=fixture.TaskStoreTests.setUp
    tearDown=fixture.TaskStoreTests.tearDown
    run_cli=fixture.TaskStoreTests.run_cli
    def setup_log(self):
        self.enterContext(patch('haejo.access_log.log_directory',return_value=self.root.parent/'Logs'))
    def task_id(self,text):
        return json.loads(next(x.split(' ',1)[1] for x in text.splitlines() if x.startswith('HAEJO_TASK ')))['id']
    def test_start_and_finish_in_one_ui_invocation(self):
        self.setup_log()
        with patch.object(cli,'_main',return_value=0) as operation:
            code,out=self.run_cli('observe','com.apple.calculator','--task','new','--goal','계산하기','--finish-task')
        self.assertEqual(0,code);operation.assert_called_once_with(['observe','com.apple.calculator'])
        report=tasks.status(self.task_id(out));self.assertEqual('done',report['result'])
        self.assertEqual(1,len(report['invocations']));self.assertIsNone(tasks.current.get())
    def test_start_first_call_and_finish_last_call_keep_same_group(self):
        self.setup_log()
        with patch.object(cli,'_main',return_value=0):
            code,out=self.run_cli('observe','com.apple.calculator','--goal','한 목표','--task=new')
            task_id=self.task_id(out)
            self.assertEqual('open',tasks.status(task_id)['state'])
            self.run_cli('observe','com.apple.TextEdit','--finish-task',env={'HAEJO_TASK':task_id})
        report=tasks.status(task_id);self.assertEqual('done',report['result'])
        self.assertEqual(2,len(report['invocations']))
    def test_ambient_new_marker_is_supported(self):
        self.setup_log()
        with patch.object(cli,'_main',return_value=0):
            code,out=self.run_cli('observe','com.apple.calculator','--goal=one goal',env={'HAEJO_TASK':'new'})
        self.assertEqual(0,code);self.assertEqual('open',tasks.status(self.task_id(out))['state'])
    def test_failure_is_not_declared_done(self):
        self.setup_log()
        for code in (1,2):
            with self.subTest(code=code),patch.object(cli,'_main',return_value=code):
                actual,out=self.run_cli('observe','app','--task','new','--goal','one goal','--finish-task')
            self.assertEqual(code,actual);self.assertEqual('failed',tasks.status(self.task_id(out))['result'])
    def test_unexpected_exit_closes_failed_and_restores_context(self):
        self.setup_log()
        with patch.object(cli,'_main',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):self.run_cli('observe','app','--task','new','--goal','one goal','--finish-task')
        self.assertIsNone(tasks.current.get());report=tasks.list_tasks(include_closed=True)[0]
        self.assertEqual('failed',report['result'])
    def test_visible_body_completion_preserves_unverified_command_code(self):
        self.setup_log()
        def operation(argv):
            tasks.note_visible_document_result({'scope':'visible_document_text','matches_requested_text':True,
              'remaining_steps':0,'save_verified':False,'dispatch_confirmed':False})
            return 1
        with patch.object(cli,'_main',side_effect=operation):
            code,out=self.run_cli('session','com.apple.TextEdit','--task','new','--goal','show requested body','--finish-task')
        task_id=self.task_id(out);self.assertEqual(1,code)
        meta=tasks._load_meta(self.root/task_id)
        self.assertEqual('done',meta['result']);self.assertEqual('visible_document_text',meta['completion_scope'])
        self.assertEqual(1,tasks.status(task_id)['invocations'][0]['exit_code'])
        self.assertEqual('visible_document_text',tasks.status(task_id)['completion_scope'])
    def test_partial_or_unknown_body_cannot_finish_done(self):
        self.setup_log()
        for update in ({'matches_requested_text':False},{'matches_requested_text':None},{'remaining_steps':1},{'save_verified':True}):
            report={'scope':'visible_document_text','matches_requested_text':True,'remaining_steps':0,
                    'save_verified':False,'dispatch_confirmed':False,**update}
            def operation(argv):tasks.note_visible_document_result(report);return 1
            with self.subTest(update=update),patch.object(cli,'_main',side_effect=operation):
                code,out=self.run_cli('session','app','--task','new','--goal','goal','--finish-task')
            self.assertEqual('failed',tasks.status(self.task_id(out))['result'])
    def test_bad_flags_refuse_before_ui_or_task_creation(self):
        self.setup_log()
        cases=[['--task','new'],['--goal','goal'],['--finish-task'],['--task','new','--goal'],
               ['--task','new','--goal','--helper'],['--task','new','--goal','goal','--goal','again'],
               ['--task','new','--goal','goal','--finish-task','--finish-task']]
        for flags in cases:
            with self.subTest(flags=flags),patch.object(cli,'_main') as operation:
                code,_=self.run_cli('observe','app',*flags)
                self.assertEqual(2,code);operation.assert_not_called()
        self.assertEqual([],tasks.list_tasks(include_closed=True))
    def test_help_does_not_create_a_goal(self):
        self.setup_log();code,_=self.run_cli('session','--help','--task','new','--goal','help','--finish-task')
        self.assertEqual(0,code);self.assertEqual([],tasks.list_tasks(include_closed=True))
    def test_failed_journal_does_not_falsely_close_goal(self):
        self.setup_log();meta=tasks.start('goal');binding=tasks.bind(meta['id'],'observe')
        binding.admit();binding.finish_requested=True
        with patch.object(tasks,'_append',side_effect=OSError('test')):
            binding.finish(0)
        binding.close_if_requested(0)
        self.assertEqual('open',tasks.status(meta['id'])['state'])

    def test_json_stdout_remains_one_command_document(self):
        import io,contextlib
        self.setup_log();stderr=io.StringIO()
        def operation(argv):
            print('{"type":"observation","tree":"owned"}')
            return 0
        with patch.object(cli,'_main',side_effect=operation),contextlib.redirect_stderr(stderr):
            code,out=self.run_cli('observe','app','--json','--task','new','--goal','goal','--finish-task')
        self.assertEqual(0,code);self.assertEqual('observation',json.loads(out)['type'])
        self.assertEqual('done',tasks.status(self.task_id(stderr.getvalue()))['result'])

    def test_admission_failure_closes_new_task_without_ui(self):
        self.setup_log()
        for error in (OSError('test'),tasks.TaskRefused('task_storage_unavailable','test')):
            with self.subTest(error=type(error)),patch.object(tasks.Binding,'admit',side_effect=error),patch.object(cli,'_main') as operation:
                code,_=self.run_cli('observe','app','--task','new','--goal','goal')
            self.assertEqual(2,code);operation.assert_not_called()
        for meta in tasks.list_tasks(include_closed=True):
            self.assertEqual('failed',meta['result']);self.assertEqual('closed',meta['state'])

    def test_option_terminator_preserves_literal_tokens(self):
        self.assertEqual((['--','--goal','text','--finish-task'],None,False),
                         tasks.inline_options(['--','--goal','text','--finish-task']))

    def test_broken_lifecycle_output_still_records_invocation_failure(self):
        import builtins
        self.setup_log();original_print=builtins.print
        def emit(*args,**kwargs):
            if args and str(args[0]).startswith('HAEJO_TASK '):
                raise BrokenPipeError('closed output')
            return original_print(*args,**kwargs)
        with patch('builtins.print',side_effect=emit),patch.object(cli,'_main') as operation:
            with self.assertRaises(BrokenPipeError):
                self.run_cli('observe','app','--task','new','--goal','goal','--finish-task')
        operation.assert_not_called()
        task_id=tasks.list_tasks(include_closed=True)[0]['id']
        report=tasks.status(task_id)
        self.assertEqual('failed',report['result'])
        self.assertIsNotNone(report['invocations'][0]['ended_at'])
        self.assertEqual('failed',report['invocations'][0]['state'])


class TaskProseTests(unittest.TestCase):
    """Goal description, per-call reasons and decision notes stay in the task record."""
    setUp=fixture.TaskStoreTests.setUp
    tearDown=fixture.TaskStoreTests.tearDown
    run_cli=fixture.TaskStoreTests.run_cli
    setup_log=InlineTaskTests.setup_log
    task_id=InlineTaskTests.task_id
    def test_detail_why_and_notes_are_recorded_in_order(self):
        self.setup_log()
        with patch.object(cli,'_main',return_value=0) as operation:
            code,out=self.run_cli('observe','com.apple.Safari','--task','new','--goal','교육 수강',
                                  '--detail','사용자 요청: 법정필수교육 3과목 수강\n진도율 100% 확인','--why','현재 화면 확인')
            task_id=self.task_id(out)
            self.assertEqual(0,code);operation.assert_called_once_with(['observe','com.apple.Safari'])
        self.assertEqual((0,f'note recorded on {task_id}\n'),self.run_cli('task','note','팝업이 떠서 닫기로 결정',env={'HAEJO_TASK':task_id}))
        with patch.object(cli,'_main',return_value=0):
            self.run_cli('observe','com.apple.Safari','--why=닫힘 확인',env={'HAEJO_TASK':task_id})
        self.assertEqual(0,self.run_cli('task','end',task_id,'--result','done','--note','3과목 완료')[0])
        report=tasks.status(task_id)
        self.assertEqual('사용자 요청: 법정필수교육 3과목 수강\n진도율 100% 확인',report['detail'])
        self.assertEqual(['현재 화면 확인','닫힘 확인'],[i['why'] for i in report['invocations']])
        self.assertEqual(['팝업이 떠서 닫기로 결정','3과목 완료'],[n['text'] for n in report['notes']])
        text=self.run_cli('task','status',task_id)[1]
        lines=text.splitlines()
        self.assertIn('detail: 사용자 요청: 법정필수교육 3과목 수강',lines)
        self.assertTrue(text.index('why: 현재 화면 확인')<text.index('팝업이 떠서')<text.index('why: 닫힘 확인')<text.index('3과목 완료'),text)
    def test_prose_validation_and_scope(self):
        self.setup_log()
        meta=tasks.start('goal')
        for bad in ('','  ','x'*1001,'a\x00b'):
            with self.assertRaises(tasks.TaskRefused):tasks.note(meta['id'],bad)
        with self.assertRaises(tasks.TaskRefused):tasks.start('goal',detail='x'*4001)
        with patch.object(cli,'_main',return_value=0) as operation:
            code,out=self.run_cli('observe','app','--why','reason')   # no task to record it in
            self.assertEqual(2,code);self.assertIn('task_required',out);operation.assert_not_called()
            code,out=self.run_cli('observe','app','--why','two\nlines',env={'HAEJO_TASK':meta['id']})
            self.assertEqual(2,code);self.assertIn('task_why_invalid',out)
            code,out=self.run_cli('list','--why','x')
            self.assertEqual(2,code);self.assertIn('task_not_applicable',out)
        tasks.end(meta['id'],'done')
        tasks.note(meta['id'],'closing summary after end')          # a summary may follow the end
        self.assertEqual('closing summary after end',tasks.status(meta['id'])['notes'][-1]['text'])
        with self.assertRaises(tasks.TaskRefused) as cm:tasks.describe(meta['id'],'late')
        self.assertEqual('task_closed',cm.exception.code)
    def test_hints_name_only_what_is_missing(self):
        self.setup_log()
        with patch.object(cli,'_main',return_value=0):
            code,out=self.run_cli('observe','app','--task','new','--goal','목표')
        task_id=self.task_id(out)
        hint=[l for l in out.splitlines() if l.startswith('HAEJO_TASK_HINT')]
        self.assertEqual(1,len(hint));self.assertIn(f'haejo task describe {task_id}',hint[0]);self.assertIn(f'haejo task note {task_id}',hint[0])
        self.assertEqual((0,f'description recorded on {task_id}\n'),self.run_cli('task','describe',task_id,'사용자 요청 전문'))
        self.assertEqual('사용자 요청 전문',tasks.status(task_id)['detail'])
        with patch.object(cli,'_main',return_value=0):
            code,out=self.run_cli('observe','app','--finish-task',env={'HAEJO_TASK':task_id})
        hint=[l for l in out.splitlines() if l.startswith('HAEJO_TASK_HINT')]
        self.assertEqual(1,len(hint),out);self.assertIn('결과 요약',hint[0]);self.assertNotIn('describe',hint[0])
        self.assertEqual(0,self.run_cli('task','note',task_id,'3개 확인 후 종료')[0])
        with patch.object(cli,'_main',return_value=0):
            code,out=self.run_cli('observe','app','--task','new','--goal','g','--detail','d','--finish-task')
        self.assertIn('결과 요약',out);self.assertNotIn('describe',out)   # detail given: only the summary is missing
        meta=tasks.start('g2',detail='d2');tasks.note(meta['id'],'n')
        self.assertNotIn('HAEJO_TASK_HINT',self.run_cli('task','end',meta['id'],'--result','done')[1])
        with patch.object(cli,'_main',return_value=0):
            code,out=self.run_cli('observe','app','--json','--task','new','--goal','g3')
        self.assertFalse(any(l.startswith('HAEJO_TASK_HINT') for l in out.splitlines()))  # --json keeps stdout clean

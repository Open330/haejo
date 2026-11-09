"""A comparison can select a candidate without silently using an old install."""
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr,redirect_stdout
from io import StringIO
from unittest.mock import Mock,patch
from tests.test_product_comparison_provenance import comparison


class SelectedRuntimeTests(unittest.TestCase):
    def runtime(self):
        return {'resolved_launcher':'/owned/Candidate.app/runtime/launcher/haejo',
                'skill':'/owned/Candidate.app/runtime/skill/SKILL.md',
                'files':{'launcher/haejo':'a'*64}}

    def test_candidate_instruction_changes_only_the_haejo_arm(self):
        with patch.object(comparison,'_HAEJO_RUNTIME',None):
            original_sky=comparison._arm_prompt('same task','sky')
        with patch.object(comparison,'_HAEJO_RUNTIME',self.runtime()):
            prompt=comparison._arm_prompt('same task','haejo')
            self.assertIn(self.runtime()['resolved_launcher'],prompt)
            self.assertIn(self.runtime()['skill'],prompt)
            self.assertIn('do not substitute an installed alias',prompt)
            self.assertEqual(original_sky,comparison._arm_prompt('same task','sky'))
            self.assertIn(comparison.BACKGROUND_CONSTRAINT,prompt)

    def test_selected_runtime_source_drift_is_part_of_both_arms_manifest(self):
        changed=self.runtime();changed['files']={'launcher/haejo':'b'*64}
        with patch.object(comparison,'_HAEJO_RUNTIME',self.runtime()), \
             patch('examples.benchmark_runtime.runtime_evidence',side_effect=[self.runtime(),changed]):
            before=comparison.source_manifest();after=comparison.source_manifest()
        self.assertNotEqual(before['sha256'],after['sha256'])
        self.assertEqual('a'*64,before['files']['selected_runtime/launcher/haejo'])

    def test_unavailable_candidate_cannot_appear_stable_and_run_a_task(self):
        with patch.object(comparison,'_HAEJO_RUNTIME',self.runtime()), \
             patch('examples.benchmark_runtime.runtime_evidence',side_effect=FileNotFoundError):
            before=comparison.source_manifest();after=comparison.source_manifest()
            evidence=comparison._source_evidence(before,after)
            self.assertFalse(evidence['source_changed'])
            self.assertTrue(evidence['selected_runtime_unavailable'])
            setup=Mock()
            task=comparison.Task('owned','ask',Mock(),setup=setup)
            with patch.object(comparison,'_run_agent') as agent:
                row=comparison.run_one(task,'haejo')
            self.assertEqual('not_run',row['status'])
            self.assertEqual('selected_runtime_unavailable',row['observed'])
            self.assertFalse(row['comparison_eligible'])
            setup.assert_not_called();agent.assert_not_called()

    def test_candidate_disappearing_at_end_is_explicitly_unavailable(self):
        with patch.object(comparison,'_HAEJO_RUNTIME',self.runtime()), \
             patch('examples.benchmark_runtime.runtime_evidence',side_effect=[self.runtime(),ValueError]):
            evidence=comparison._source_evidence(comparison.source_manifest(),comparison.source_manifest())
        self.assertTrue(evidence['source_changed'])
        self.assertTrue(evidence['selected_runtime_unavailable'])

    def test_default_and_selected_haejo_both_forbid_other_input_routes(self):
        for selected in (None,self.runtime()):
            with self.subTest(selected=selected),patch.object(comparison,'_HAEJO_RUNTIME',selected):
                prompt=comparison._arm_prompt('same task','haejo')
            self.assertIn('AppleScript',prompt)
            self.assertIn('direct native input',prompt)

    def test_missing_candidate_is_rejected_before_model_or_fixture(self):
        with patch.object(comparison,'run_one') as run, \
             redirect_stderr(StringIO()),self.assertRaises(SystemExit) as error:
            comparison.main(['--haejo-launcher','/nonexistent/runtime/launcher/haejo','--list'])
        self.assertEqual(2,error.exception.code)
        run.assert_not_called()

    def test_external_controller_forwards_the_selected_runtime(self):
        original=comparison.main
        worker=Mock();worker.request.return_value={'scope':'test'}
        with tempfile.TemporaryDirectory() as folder:
            launcher=Path(folder)/'haejo';launcher.write_text('owned fixture');launcher.chmod(0o700)
            with patch.dict(os.environ,{},clear=True), \
                 patch.object(comparison,'_HAEJO_RUNTIME',None), \
                 patch('examples.benchmark_runtime.runtime_evidence',return_value=self.runtime()), \
                 patch('comparison_fixture_worker.FixtureWorker',return_value=worker), \
                 patch('haejo.helper.InheritedHelperDriver.available',return_value=False), \
                 patch('haejo.process_responsibility.observe_responsibility',return_value={'status':'unobserved'}), \
                 patch.object(comparison,'main',return_value=123) as forwarded, \
                 redirect_stdout(StringIO()):
                self.assertEqual(123,original(['--external-owned-worker',str(launcher),
                    '--haejo-launcher',self.runtime()['resolved_launcher'],'--only','calc_to_textedit']))
            args=forwarded.call_args.args[0]
            self.assertEqual(self.runtime()['resolved_launcher'],args[args.index('--haejo-launcher')+1])
            worker.close.assert_called_once()

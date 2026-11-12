"""One stated macOS floor reaches every compiler call and bundle plist."""
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('standalone_builder_target', ROOT/'setup/build_standalone_preview.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DeploymentTarget(unittest.TestCase):
    def test_the_floor_is_stated_once_and_read_by_the_python_build(self):
        stated = re.findall(r'^HAEJO_MACOS_TARGET=(\S+)$', (ROOT/'signing.sh').read_text(), re.M)
        self.assertEqual(1, len(stated))
        self.assertEqual(stated[0], builder.deployment_target())
        self.assertTrue(builder.swift_target().endswith('-apple-macos'+stated[0]))

    def test_no_bundle_takes_its_minimum_from_the_build_host(self):
        source = (ROOT/'setup/build_standalone_preview.py').read_text()
        self.assertIn("'LSMinimumSystemVersion':deployment_target()", source)
        self.assertNotIn("'LSMinimumSystemVersion':platform.mac_ver()", source)
        self.assertEqual(2, source.count("'-target',swift_target()") + source.count("'-target', swift_target()"))
        bundle = (ROOT/'helper/bundle.sh').read_text()
        self.assertIn('<string>@HAEJO_MACOS_TARGET@</string>', bundle)
        self.assertIn('s/@HAEJO_MACOS_TARGET@/$HAEJO_MACOS_TARGET/', bundle)
        for script in ('helper/build.sh', 'launcher/build.sh'):
            self.assertIn('-target "$HAEJO_SWIFT_TARGET"', (ROOT/script).read_text(), script)

    def test_a_binary_built_for_another_macos_is_refused(self):
        def run(reply):
            return lambda *a, **k: SimpleNamespace(stdout=reply)
        floor = builder.deployment_target()
        good = f'Load command 10\n      cmd LC_BUILD_VERSION\n    minos {floor}\n      sdk 27.2\n'
        self.assertEqual(floor, builder.require_deployment_target(['HaejoSetup'], run=run(good)))
        with self.assertRaisesRegex(RuntimeError, 'targets macOS'):
            builder.require_deployment_target(['HaejoSetup'], run=run(good.replace(floor, '99.9')))
        with self.assertRaisesRegex(RuntimeError, 'targets macOS'):
            builder.require_deployment_target(['HaejoSetup'], run=run(''))

    def test_shipped_helper_has_no_unauthenticated_capture_mode(self):
        source = (ROOT/'helper/HaejoHelper.swift').read_text()
        guarded = source[source.index('#if HAEJO_PROBES'):]
        guarded = guarded[:guarded.index('#endif')]
        for flag in ('--indicator-menu-probe', '--hold-indicator', '--indicator-probe', '--recording-indicator-probe', '--probe-shot'):
            self.assertIn(flag, guarded)
            self.assertNotIn(f'"{flag}"', source.replace(guarded, ''))
        self.assertNotIn('HAEJO_PROBES', (ROOT/'helper/build.sh').read_text())


if __name__ == '__main__':
    unittest.main()

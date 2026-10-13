import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('runner', Path(__file__).parents[1] / 'mnova-nmr-processing/scripts/mnova_runner.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_mac_bundle_uses_plist_executable_with_spaces(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'Mnova 17.app'
            macos = app / 'Contents/MacOS'
            macos.mkdir(parents=True)
            binary = macos / 'custom-name'
            binary.write_bytes(b'fake')
            binary.chmod(0o755)
            with (app / 'Contents/Info.plist').open('wb') as stream:
                plistlib.dump({'CFBundleExecutable': binary.name}, stream)
            self.assertEqual(runner.executable_from_path(app), binary.resolve())
            self.assertIn(str(macos.resolve()), runner.resource_dirs(binary))

    def test_explicit_missing_path_does_not_silently_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                runner.discover(str(Path(temp) / 'missing.app'))

    def test_mac17_escaped_plist_is_read_without_modifying_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'MestReNova.app'
            binary = app / 'Contents/MacOS/MestReNova'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'fake')
            binary.chmod(0o755)
            plist = app / 'Contents/Info.plist'
            original = plistlib.dumps({'CFBundleExecutable': 'MestReNova', 'CFBundleVersion': '17.0.1.41952'}).replace(b'"', b'\\"')
            plist.write_bytes(original)
            self.assertEqual(runner.executable_from_path(app), binary.resolve())
            self.assertEqual(plist.read_bytes(), original)

    def test_invalid_bundle_metadata_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'MestReNova.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents/Info.plist').write_text('not a plist')
            with self.assertRaises(ValueError):
                runner.executable_from_path(app)

    def test_zero_exit_without_marker_is_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'script.qs'
            script.write_text('function task() {}')
            with patch.object(runner.subprocess, 'run', return_value=type('Result', (), {'returncode': 0})()):
                folder, result = runner.run_script(root / 'mnova', script, 'task', root, [], 1)
            self.assertEqual(result['status'], 'failed')
            self.assertTrue((folder / 'result.json').exists())

    def test_completion_and_expected_output_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / '中文 script.qs'
            script.write_text('function task() {}', encoding='utf-8')
            output = root / 'result.mnova'
            def execute(command, **kwargs):
                folder = Path(command[-1]).parent
                (folder / 'completed.txt').write_text('completed\n')
                output.write_bytes(b'new native output placeholder for launcher test')
                self.assertIsInstance(command, list)
                self.assertIn('--nogui', command)
                return type('Result', (), {'returncode': 0})()
            with patch.object(runner.subprocess, 'run', side_effect=execute):
                folder, result = runner.run_script(root / 'mnova', script, 'task', root, [output], 1)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(json.loads((folder / 'result.json').read_text(encoding='utf-8'))['status'], 'completed')
            with patch.object(runner.subprocess, 'run', side_effect=execute):
                _, result = runner.run_script(root / 'mnova', script, 'task', root, [root / 'missing.mnova'], 1)
            self.assertEqual(result['status'], 'failed')

    def test_timeout_records_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'script.qs'
            script.write_text('function task() {}')
            with patch.object(runner.subprocess, 'run', side_effect=runner.subprocess.TimeoutExpired('mnova', 1)):
                _, result = runner.run_script(root / 'mnova', script, 'task', root, [], 1)
            self.assertEqual(result['status'], 'failed')

    def test_old_output_cannot_pass_completion_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'script.qs'
            script.write_text('function task() {}')
            output = root / 'old.mnova'
            output.write_bytes(b'old output')
            def execute(command, **kwargs):
                (Path(command[-1]).parent / 'completed.txt').write_text('completed\n')
                return type('Result', (), {'returncode': 0})()
            with patch.object(runner.subprocess, 'run', side_effect=execute):
                _, result = runner.run_script(root / 'mnova', script, 'task', root, [output], 1)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('unchanged', result['error'])

    def test_rejects_function_call_expression(self):
        with self.assertRaises(ValueError):
            runner.wrapper('', 'task()', Path('marker.txt'))


if __name__ == '__main__':
    unittest.main()

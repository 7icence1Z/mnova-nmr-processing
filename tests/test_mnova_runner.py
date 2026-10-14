import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import plistlib
import struct
import tempfile
import threading
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

    def test_probe_abort_keeps_diagnostics_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            crash = type('Result', (), {'returncode': -6, 'stdout': b'', 'stderr': b'abort() called'})()
            with patch.object(runner.subprocess, 'run', return_value=crash) as call:
                with self.assertRaisesRegex(ValueError, 'diagnostics:'):
                    runner.probe(root / 'mnova', root)
            self.assertEqual(call.call_count, 1)
            record = json.loads(next(root.glob('probe-*/result.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['failure_kind'], 'native_crash')
            self.assertEqual(record['returncode'], -6)
            self.assertEqual(next(root.glob('probe-*/stderr.log')).read_bytes(), b'abort() called')

    def test_gui_preparation_never_discovers_or_launches_mnova(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'source.qs'
            script.write_text('function task() {}')
            with patch.object(runner.subprocess, 'run') as call:
                folder, record = runner.prepare_gui(script, 'task', root, [root / 'new.mnova'])
            call.assert_not_called()
            self.assertEqual(record['status'], 'prepared_not_executed')
            self.assertFalse((folder / 'completed.txt').exists())
            self.assertIn('function _mnovaRunnerEntry()', (folder / 'wrapped.qs').read_text(encoding='utf-8-sig'))

    def test_mac_qt_cleanup_is_child_only(self):
        overrides = {'QT_QPA_PLATFORM': 'offscreen', 'QT_PLUGIN_PATH': '/python/qt', 'SAMPLE_KEEP': 'yes'}
        with patch.dict(runner.os.environ, overrides), patch.object(runner.sys, 'platform', 'darwin'):
            env, removed = runner.child_environment()
            self.assertNotIn('QT_QPA_PLATFORM', env)
            self.assertNotIn('QT_PLUGIN_PATH', env)
            self.assertEqual(env['SAMPLE_KEEP'], 'yes')
            self.assertIn('QT_PLUGIN_PATH', removed)
            self.assertEqual(runner.os.environ['QT_QPA_PLATFORM'], 'offscreen')

    def test_run_abort_cannot_be_success_even_with_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'script.qs'
            script.write_text('function task() {}')
            def abort(command, **kwargs):
                (Path(command[-1]).parent / 'completed.txt').write_text('completed\n')
                return type('Result', (), {'returncode': -6})()
            with patch.object(runner.subprocess, 'run', side_effect=abort) as call:
                _, record = runner.run_script(root / 'mnova', script, 'task', root, [], 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['failure_kind'], 'native_crash')

    def test_probe_timeout_preserves_partial_stderr(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            timeout = runner.subprocess.TimeoutExpired('mnova', 30, output=b'initializing', stderr=b'plugin error before hang')
            with patch.object(runner.subprocess, 'run', side_effect=timeout):
                with self.assertRaisesRegex(ValueError, 'diagnostics:'):
                    runner.probe(root / 'mnova', root)
            self.assertEqual(next(root.glob('probe-*/stderr.log')).read_bytes(), timeout.stderr)
            record = json.loads(next(root.glob('probe-*/result.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['failure_kind'], 'timeout')

    def test_bad_run_inputs_never_start_mnova(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'task.qs'
            script.write_text('function task() {}')
            common = ['runner', 'run', '--script', str(script), '--function', 'task', '--run-dir', temp]
            cases = [common + ['--timeout', n] for n in ('0', '-1', 'nan', 'inf')]
            cases += [common + ['--expect', str(script)],
                      common + ['--function', 'bad()'],
                      common + ['--script', str(root / 'missing.qs')]]
            for argv in cases:
                with self.subTest(argv=argv), patch.object(runner.sys, 'argv', argv), patch.object(runner, 'probe') as probe, patch.object(runner, 'discover') as discover, redirect_stderr(io.StringIO()):
                    self.assertEqual(runner.main(), 1)
                    probe.assert_not_called()
                    discover.assert_not_called()

    def test_static_doctor_reads_real_format_without_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'MestReNova.app'
            binary = app / 'Contents/MacOS/MestReNova'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(struct.pack('>II', 0xcafebabe, 2) + struct.pack('>IIIII', 0x1000007, 3, 4096, 1024, 12) + struct.pack('>IIIII', 0x100000c, 0, 8192, 1024, 12))
            binary.chmod(0o755)
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'MestReNova', 'CFBundleVersion': '17.0.1.41952'}))
            out = io.StringIO()
            with patch.object(runner.sys, 'argv', ['runner', '--mnova', str(app), 'doctor', '--static']), patch.object(runner.subprocess, 'run') as call, redirect_stdout(out):
                self.assertEqual(runner.main(), 0)
            call.assert_not_called()
            record = json.loads(out.getvalue())
            self.assertEqual(record['status'], 'static_only_not_executed')
            self.assertEqual(record['runtime']['binary_architectures'], ['x86_64', 'arm64'])

    def test_finds_case_varied_app_in_vendor_subdirectory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root / 'Mestrelab' / 'MNOVA.app'
            app.mkdir(parents=True)
            (root / 'Unrelated.app').mkdir()
            with patch.object(runner.shutil, 'which', return_value=None):
                found = list(runner.candidates('darwin', [root]))
            self.assertEqual(found, [app])

    def test_bundle_metadata_types_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'MestReNova.app'
            (app / 'Contents').mkdir(parents=True)
            for data in ([], {'CFBundleExecutable': 123}, {'CFBundleExecutable': '../wrong'}):
                with self.subTest(data=data):
                    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(data))
                    with self.assertRaises(ValueError):
                        runner.executable_from_path(app)

    def test_forwarded_job_waits_for_existing_instance_without_relaunch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'task.qs'
            script.write_text('function task() {}')
            timers = []
            def forwarded(command, **kwargs):
                marker = Path(command[-1]).parent / 'completed.txt'
                # File creation happens before TextStream finishes writing it.
                marker.write_text('')
                kwargs['stderr'].write(b'started at previous instance')
                timer = threading.Timer(0.03, lambda: marker.write_text('completed\n'))
                timers.append(timer)
                timer.start()
                return type('Result', (), {'returncode': 0})()
            with patch.object(runner.subprocess, 'run', side_effect=forwarded) as call:
                _, record = runner.run_script(root / 'mnova', script, 'task', root, [], 1)
            for timer in timers:
                timer.join()
            call.assert_called_once()
            self.assertEqual(record['status'], 'completed')
            self.assertTrue(record['forwarded_to_existing_instance'])


if __name__ == '__main__':
    unittest.main()

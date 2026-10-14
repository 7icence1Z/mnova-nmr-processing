"""Portable launcher for existing Mnova scripts (Python 3.9+, standard library)."""
import argparse
import json
import math
import os
import platform
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import struct
import sys
import tempfile
import time
from xml.parsers.expat import ExpatError


def bundle_info(bundle):
    raw = (Path(bundle) / 'Contents' / 'Info.plist').read_bytes()
    try:
        info = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ExpatError):
        # Some bundles contain backslash-escaped XML markup quotes.
        # Normalize only this identified form in memory; never rewrite the bundle.
        if raw.startswith(b'<?xml version=\\"'):
            try:
                info = plistlib.loads(raw.replace(b'\\"', b'"'))
            except (plistlib.InvalidFileException, ExpatError):
                raise ValueError('Cannot parse bundle Info.plist: ' + str(bundle))
        else:
            raise ValueError('Cannot parse bundle Info.plist: ' + str(bundle))
    if not isinstance(info, dict):
        raise ValueError('Bundle Info.plist is not a dictionary: ' + str(bundle))
    return info


def absolute_path(path, strict=False):
    return Path(path).expanduser().resolve(strict=strict)


def executable_from_path(path):
    path = Path(path).expanduser().resolve()
    if path.is_dir() and path.suffix.lower() == '.app':
        name = bundle_info(path).get('CFBundleExecutable')
        if not isinstance(name, str) or not name or name in ('.', '..') or '/' in name or '\\' in name:
            raise ValueError('App bundle has no valid CFBundleExecutable')
        path = path / 'Contents' / 'MacOS' / name
    if not path.is_file():
        raise ValueError('Mnova executable not found: ' + str(path))
    if os.name != 'nt' and not os.access(path, os.X_OK):
        raise ValueError('Mnova executable is not executable: ' + str(path))
    return path


def candidates(system=None, app_roots=None):
    system = system or sys.platform
    if system == 'darwin':
        for root in app_roots if app_roots is not None else (Path('/Applications'), Path.home() / 'Applications'):
            # Case-sensitive volumes and a vendor subdirectory are both common.
            for pattern in ('*.app', '*/*.app'):
                for app in sorted(root.glob(pattern)):
                    if any(name in app.name.casefold() for name in ('mnova', 'mestrenova')):
                        yield app
    elif system == 'win32':
        try:
            import winreg
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 0, winreg.KEY_READ | view) as root:
                            for index in range(winreg.QueryInfoKey(root)[0]):
                                with winreg.OpenKey(root, winreg.EnumKey(root, index)) as entry:
                                    try:
                                        name = winreg.QueryValueEx(entry, 'DisplayName')[0]
                                        location = winreg.QueryValueEx(entry, 'InstallLocation')[0]
                                    except OSError:
                                        continue
                                    if 'mnova' in name.lower() or 'mestrenova' in name.lower():
                                        yield Path(location) / 'MestReNova.exe'
                    except OSError:
                        continue
        except ImportError:
            pass
        for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            root = os.environ.get(key)
            if root:
                yield Path(root) / 'Mestrelab Research S.L' / 'MestReNova' / 'MestReNova.exe'
    for name in ('MestReNova.exe', 'mestrenova', 'Mnova'):
        found = shutil.which(name)
        if found:
            yield Path(found)


def discover(explicit=None):
    explicit = explicit or os.environ.get('MNOVA_EXECUTABLE')
    if explicit:
        return executable_from_path(explicit)
    found = []
    for candidate in candidates():
        try:
            path = executable_from_path(candidate)
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        if path not in found:
            found.append(path)
    if len(found) != 1:
        raise ValueError('Specify --mnova or MNOVA_EXECUTABLE; discovered: ' + str(found))
    return found[0]


def resource_dirs(executable):
    roots = [executable.parent]
    if executable.parent.name == 'MacOS' and executable.parent.parent.name == 'Contents':
        roots += [executable.parent.parent / 'Resources', executable.parent.parent / 'SharedSupport']
    return [str(root.resolve()) for root in roots if root.is_dir()]


def child_environment():
    env = os.environ.copy()
    removed = []
    if sys.platform == 'darwin':
        # Use the app's own Qt deployment, not a Python/agent Qt plugin override.
        for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_QPA_PLATFORM'):
            if key in env:
                removed.append(key)
                env.pop(key)
    return env, removed


def runtime_info(executable):
    info = {'platform': sys.platform, 'launcher_machine': platform.machine()}
    if executable.parent.name == 'MacOS' and executable.parent.parent.name == 'Contents':
        try:
            meta = bundle_info(executable.parent.parent.parent)
            info.update({'bundle_version': meta.get('CFBundleVersion'),
                         'bundle_identifier': meta.get('CFBundleIdentifier')})
            info['binary_architectures'] = macho_architectures(executable)
        except (OSError, ValueError) as error:
            info['bundle_metadata_error'] = str(error)
    return info


def macho_architectures(executable):
    """Read Mach-O headers only; never execute a foreign/translated binary."""
    names = {0x01000007: 'x86_64', 0x0100000C: 'arm64', 7: 'i386', 12: 'arm'}
    with Path(executable).open('rb') as stream:
        header = stream.read(8)
        if len(header) != 8:
            return []
        magic = header[:4]
        if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'):
            endian = '>' if magic[:1] == b'\xca' else '<'
            count = struct.unpack(endian + 'I', header[4:])[0]
            if count > 32:
                raise ValueError('Invalid Mach-O architecture count')
            stride = 32 if magic in (b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca') else 20
            cpus = []
            for _ in range(count):
                entry = stream.read(stride)
                if len(entry) != stride:
                    raise ValueError('Truncated Mach-O architecture table')
                cpus.append(struct.unpack(endian + 'I', entry[:4])[0])
        elif magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'):
            cpus = [struct.unpack(('<' if magic[0] in (0xcf, 0xce) else '>') + 'I', header[4:])[0]]
        else:
            return []
    return list(dict.fromkeys(names.get(cpu, hex(cpu)) for cpu in cpus))


def probe(executable, run_dir=None):
    root = absolute_path(run_dir or Path(tempfile.gettempdir()) / 'mnova-diagnostics')
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='probe-', dir=root))
    env, removed = child_environment()
    report = {'command': [str(executable), '--help'], 'status': 'failed',
              'runtime': runtime_info(executable), 'removed_qt_variables': removed}
    try:
        result = subprocess.run(report['command'], cwd=executable.parent,
                                capture_output=True, timeout=30, env=env)
        (folder / 'stdout.log').write_bytes(result.stdout)
        (folder / 'stderr.log').write_bytes(result.stderr)
        report['returncode'] = result.returncode
        help_text = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        if result.returncode != 0:
            report['failure_kind'] = 'native_crash' if result.returncode < 0 else 'process_error'
            raise ValueError('Mnova --help exited with code ' + str(result.returncode))
        missing = [flag for flag in ('--nogui', '--wait', '--sf', '--logfile') if flag not in help_text]
        if missing:
            report['failure_kind'] = 'unsupported_interface'
            raise ValueError('Unsupported headless interface: ' + ', '.join(missing))
        report['status'] = 'completed'
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        if isinstance(error, subprocess.TimeoutExpired):
            report['failure_kind'] = 'timeout'
            (folder / 'stdout.log').write_bytes(error.output or b'')
            (folder / 'stderr.log').write_bytes(error.stderr or b'')
        report['error'] = str(error)
        raise ValueError(str(error) + '; diagnostics: ' + str(folder) +
                         '. Do not retry a crash automatically; use prepare-gui if GUI works.') from error
    finally:
        (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return help_text


def prepare_gui(script, function, run_dir, expected):
    """Prepare the same native script for a user/GUI session, without launching Mnova."""
    root = absolute_path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='gui-', dir=root))
    script = absolute_path(script, strict=True)
    generated = folder / 'wrapped.qs'
    generated.write_text(wrapper(script.read_text(encoding='utf-8-sig'), function, folder / 'completed.txt'), encoding='utf-8-sig')
    record = {'status': 'prepared_not_executed', 'script': str(script),
              'prepared_script': str(generated), 'entry_function': '_mnovaRunnerEntry',
              'expected_outputs': [str(Path(p).expanduser().resolve()) for p in expected],
              'instructions': 'Load wrapped.qs in the existing Mnova script editor and run _mnovaRunnerEntry. Then independently reopen and verify outputs and display style. Preparation is not processing success.'}
    (folder / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return folder, record


def wrapper(source, function, marker):
    if not re.fullmatch(r'[A-Za-z_$][\w$]*', function, flags=re.ASCII):
        raise ValueError('Function must be a plain zero-argument identifier, without ()')
    if '_mnovaRunnerEntry' in source:
        raise ValueError('Reserved function name _mnovaRunnerEntry in source')
    path = json.dumps(Path(marker).as_posix(), ensure_ascii=True)
    return source + '\nfunction _mnovaRunnerEntry() {\n' + (
        'if (File.exists(' + path + ') && !File.remove(' + path + '))\n'
        '    throw new Error("Cannot remove old completion marker");\n') + function + '();\n' + (
        'var f = new File(' + path + ');\n'
        'if (!f.open(File.WriteOnly)) throw new Error("Cannot write completion marker");\n'
        'var s = new TextStream(f); s.write("completed\\n"); s.flush(); f.close();\n}\n')


def marker_complete(marker):
    try:
        return marker.read_text(encoding='utf-8').strip() == 'completed'
    except OSError:
        return False


def wait_for_forwarded_marker(folder, marker, deadline):
    logs = '\n'.join((folder / name).read_text(encoding='utf-8', errors='replace')
                     for name in ('mnova.log', 'stdout.log', 'stderr.log') if (folder / name).is_file())
    if 'previous instance' not in logs.lower():
        return False
    while not marker_complete(marker) and time.monotonic() < deadline:
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    return True


def run_script(executable, script, function, run_dir, expected, timeout, cwd=None):
    run_dir = absolute_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    # A separate directory per invocation prevents old logs/markers passing validation.
    folder = Path(tempfile.mkdtemp(prefix='mnova-', dir=run_dir))
    marker = folder / 'completed.txt'
    script = absolute_path(script, strict=True)
    generated = folder / 'wrapped.qs'
    generated.write_text(wrapper(script.read_text(encoding='utf-8-sig'), function, marker), encoding='utf-8-sig')
    expected = [Path(path).expanduser().resolve() for path in expected]
    if script in expected:
        raise ValueError('Expected output cannot be the input script')
    before = {str(path): (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None for path in expected}
    command = [str(executable), '--nogui', '--wait', '--logfile', str(folder / 'mnova.log'),
               '--sf', '_mnovaRunnerEntry', str(generated)]
    env, removed = child_environment()
    record = {'executable': str(executable), 'script': str(script), 'function': function,
              'runtime': runtime_info(executable), 'removed_qt_variables': removed,
              'command': command, 'cwd': str(absolute_path(cwd) if cwd else executable.parent),
              'expected_outputs': [str(p) for p in expected], 'status': 'running'}
    try:
        deadline = time.monotonic() + timeout
        with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
            result = subprocess.run(command, cwd=record['cwd'], stdout=out, stderr=err, timeout=timeout, env=env)
        record['returncode'] = result.returncode
        if result.returncode != 0:
            record['failure_kind'] = 'native_crash' if result.returncode < 0 else 'process_error'
            raise ValueError('Mnova process failed: exit ' + str(result.returncode))
        if not marker_complete(marker):
            record['forwarded_to_existing_instance'] = wait_for_forwarded_marker(folder, marker, deadline)
            if record['forwarded_to_existing_instance'] and not marker_complete(marker):
                record['failure_kind'] = 'forwarded_incomplete'
        if not marker_complete(marker):
            raise ValueError('No completion marker: inspect logs for script errors or previous-instance forwarding')
        for path in expected:
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Expected output missing or empty: ' + str(path))
            after = (path.stat().st_mtime_ns, path.stat().st_size)
            if after == before[str(path)]:
                raise ValueError('Expected output unchanged: ' + str(path))
        record['status'] = 'completed'
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        if isinstance(error, subprocess.TimeoutExpired):
            record['failure_kind'] = 'timeout'
        record['status'] = 'failed'
        record['error'] = str(error)
        record['next_step'] = 'Inspect logs; do not retry native crashes automatically. If GUI works, prepare-gui creates a script for that session; it does not execute it.'
    (folder / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return folder, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mnova', help='Executable or macOS .app; alternatively MNOVA_EXECUTABLE')
    sub = parser.add_subparsers(dest='mode', required=True)
    doctor = sub.add_parser('doctor', help='Discover Mnova and check headless command-line flags')
    doctor.add_argument('--run-dir', help='Directory for probe diagnostics (defaults to system temp)')
    doctor.add_argument('--static', action='store_true', help='Read bundle/version/Mach-O only; never launch Mnova')
    gui = sub.add_parser('prepare-gui', help='Prepare native script for an existing GUI session; does not launch or execute')
    gui.add_argument('--script', required=True)
    gui.add_argument('--function', required=True)
    gui.add_argument('--run-dir', required=True)
    gui.add_argument('--expect', action='append', default=[])
    run = sub.add_parser('run', help='Run an existing zero-argument .qs function')
    run.add_argument('--script', required=True)
    run.add_argument('--function', required=True)
    run.add_argument('--run-dir', required=True, help='Writable directory for unique invocation logs')
    run.add_argument('--expect', action='append', default=[], help='Output file that must be new/updated (repeatable)')
    run.add_argument('--timeout', type=float, default=180)
    run.add_argument('--cwd', help='Override executable directory if current Mnova requires it')
    args = parser.parse_args()
    try:
        # Reject user input errors before any Mnova launch or risky --help probe.
        if args.mode in ('run', 'prepare-gui'):
            script = absolute_path(args.script, strict=True)
            wrapper(script.read_text(encoding='utf-8-sig'), args.function, Path('validation-marker'))
            if script in [absolute_path(p) for p in args.expect]:
                raise ValueError('Expected output cannot be the input script')
        if args.mode == 'run':
            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError('--timeout must be finite and positive')
            if args.cwd and not absolute_path(args.cwd).is_dir():
                raise ValueError('--cwd must be an existing directory')
        if args.mode == 'prepare-gui':
            folder, result = prepare_gui(args.script, args.function, args.run_dir, args.expect)
            print(json.dumps({'run_dir': str(folder), **result}, ensure_ascii=False, indent=2))
            return 0
        executable = discover(args.mnova)
        if args.mode == 'doctor' and args.static:
            print(json.dumps({'executable': str(executable), 'status': 'static_only_not_executed',
                              'runtime': runtime_info(executable), 'resource_dirs': resource_dirs(executable),
                              'note': 'Launcher architecture is not necessarily hardware or Mnova execution architecture'}, ensure_ascii=False, indent=2))
            return 0
        help_text = probe(executable, args.run_dir)
        if args.mode == 'doctor':
            print(json.dumps({'executable': str(executable), 'platform': sys.platform,
                              'resource_dirs': resource_dirs(executable), 'help': help_text,
                              'note': 'Flags detected; license, fonts and scripting runtime still require a smoke run'}, ensure_ascii=False, indent=2))
            return 0
        folder, result = run_script(executable, args.script, args.function, args.run_dir, args.expect, args.timeout, args.cwd)
        print(json.dumps({'run_dir': str(folder), **result}, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'completed' else 1
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

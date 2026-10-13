"""Portable launcher for existing Mnova scripts (Python 3.9+, standard library)."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from xml.parsers.expat import ExpatError


def bundle_info(bundle):
    raw = (Path(bundle) / 'Contents' / 'Info.plist').read_bytes()
    try:
        return plistlib.loads(raw)
    except (plistlib.InvalidFileException, ExpatError):
        # Observed in the 17.0.1-41952 DMG: XML markup quotes are backslash escaped.
        # Normalize only this identified form in memory; never rewrite the bundle.
        if raw.startswith(b'<?xml version=\\"'):
            try:
                return plistlib.loads(raw.replace(b'\\"', b'"'))
            except (plistlib.InvalidFileException, ExpatError):
                pass
        raise ValueError('Cannot parse bundle Info.plist: ' + str(bundle))


def executable_from_path(path):
    path = Path(path).expanduser().resolve()
    if path.is_dir() and path.suffix.lower() == '.app':
        name = bundle_info(path).get('CFBundleExecutable')
        if not name or Path(name).name != name:
            raise ValueError('App bundle has no valid CFBundleExecutable')
        path = path / 'Contents' / 'MacOS' / name
    if not path.is_file():
        raise ValueError('Mnova executable not found: ' + str(path))
    if os.name != 'nt' and not os.access(path, os.X_OK):
        raise ValueError('Mnova executable is not executable: ' + str(path))
    return path


def candidates(system=None):
    system = system or sys.platform
    if system == 'darwin':
        for root in (Path('/Applications'), Path.home() / 'Applications'):
            for pattern in ('*Mnova*.app', '*MestReNova*.app', '*mestrenova*.app'):
                yield from sorted(root.glob(pattern))
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


def probe(executable):
    result = subprocess.run([str(executable), '--help'], cwd=executable.parent,
                            capture_output=True, timeout=30)
    help_text = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    if result.returncode != 0:
        raise ValueError('Mnova --help failed: ' + help_text)
    missing = [flag for flag in ('--nogui', '--wait', '--sf', '--logfile') if flag not in help_text]
    if missing:
        raise ValueError('Unsupported headless interface: ' + ', '.join(missing))
    return help_text


def wrapper(source, function, marker):
    if not re.fullmatch(r'[A-Za-z_$][\w$]*', function, flags=re.ASCII):
        raise ValueError('Function must be a plain zero-argument identifier, without ()')
    if '_mnovaRunnerEntry' in source:
        raise ValueError('Reserved function name _mnovaRunnerEntry in source')
    path = json.dumps(Path(marker).as_posix(), ensure_ascii=True)
    return source + '\nfunction _mnovaRunnerEntry() {\n' + function + '();\n' + (
        'var f = new File(' + path + ');\n'
        'if (!f.open(File.WriteOnly)) throw new Error("Cannot write completion marker");\n'
        'var s = new TextStream(f); s.write("completed\\n"); s.flush(); f.close();\n}\n')


def run_script(executable, script, function, run_dir, expected, timeout, cwd=None):
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    # A separate directory per invocation prevents old logs/markers passing validation.
    folder = Path(tempfile.mkdtemp(prefix='mnova-', dir=run_dir))
    marker = folder / 'completed.txt'
    script = Path(script).resolve(strict=True)
    generated = folder / 'wrapped.qs'
    generated.write_text(wrapper(script.read_text(encoding='utf-8-sig'), function, marker), encoding='utf-8-sig')
    expected = [Path(path).expanduser().resolve() for path in expected]
    if script in expected:
        raise ValueError('Expected output cannot be the input script')
    before = {str(path): (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None for path in expected}
    command = [str(executable), '--nogui', '--wait', '--logfile', str(folder / 'mnova.log'),
               '--sf', '_mnovaRunnerEntry', str(generated)]
    record = {'executable': str(executable), 'script': str(script), 'function': function,
              'command': command, 'cwd': str(Path(cwd).resolve() if cwd else executable.parent),
              'expected_outputs': [str(p) for p in expected], 'status': 'running'}
    try:
        with (folder / 'stdout.log').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
            result = subprocess.run(command, cwd=record['cwd'], stdout=out, stderr=err, timeout=timeout)
        record['returncode'] = result.returncode
        if result.returncode != 0:
            raise ValueError('Mnova process failed: exit ' + str(result.returncode))
        if not marker.exists() or marker.read_text().strip() != 'completed':
            raise ValueError('No completion marker: inspect logs for script errors or previous-instance forwarding')
        for path in expected:
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Expected output missing or empty: ' + str(path))
            after = (path.stat().st_mtime_ns, path.stat().st_size)
            if after == before[str(path)]:
                raise ValueError('Expected output unchanged: ' + str(path))
        record['status'] = 'completed'
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        record['status'] = 'failed'
        record['error'] = str(error)
    (folder / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return folder, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mnova', help='Executable or macOS .app; alternatively MNOVA_EXECUTABLE')
    sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('doctor', help='Discover Mnova and check headless command-line flags')
    run = sub.add_parser('run', help='Run an existing zero-argument .qs function')
    run.add_argument('--script', required=True)
    run.add_argument('--function', required=True)
    run.add_argument('--run-dir', required=True, help='Writable directory for unique invocation logs')
    run.add_argument('--expect', action='append', default=[], help='Output file that must be new/updated (repeatable)')
    run.add_argument('--timeout', type=float, default=180)
    run.add_argument('--cwd', help='Override executable directory if current Mnova requires it')
    args = parser.parse_args()
    try:
        executable = discover(args.mnova)
        help_text = probe(executable)
        if args.mode == 'doctor':
            print(json.dumps({'executable': str(executable), 'platform': sys.platform,
                              'resource_dirs': resource_dirs(executable), 'help': help_text,
                              'note': 'Flags detected; license, fonts and scripting runtime still require a smoke run'}, ensure_ascii=False, indent=2))
            return 0
        if args.timeout <= 0:
            raise ValueError('--timeout must be positive')
        folder, result = run_script(executable, args.script, args.function, args.run_dir, args.expect, args.timeout, args.cwd)
        print(json.dumps({'run_dir': str(folder), **result}, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'completed' else 1
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

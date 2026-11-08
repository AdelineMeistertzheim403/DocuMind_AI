"""Network-free unit/ASGI preparation. Never starts Docker or an application server."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
TESTS = ('test_recovery_directory.py', 'test_fastapi_directory_transitions.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_directory(path):
    if not path.is_absolute() or path.exists():
        raise RuntimeError('Output must be an absolute, new path')
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.parent.is_dir():
        raise RuntimeError('Output parent must exist without symlinks')
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT) or any(
        p.lower() in {'releases', 'release', 'artifacts', 'fixtures', 'deliveries', 'source', 'roundtrip-restore'}
        for p in resolved.parts
    ):
        raise RuntimeError('Protected output location')
    return resolved


def verify_inputs():
    manifest = json.loads((ROOT / 'INPUTS.json').read_text(encoding='ascii'))
    actual = {
        p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()
        and p.name not in {'INPUTS.json', 'SHA256SUMS'}
    }
    if set(manifest) != actual:
        raise RuntimeError('Missing or unlisted candidate files')
    for name, expected in manifest.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise RuntimeError('Unsafe inventory path')
        path = ROOT / relative
        if any(p.is_symlink() for p in (path, *path.parents)) or sha(path) != expected:
            raise RuntimeError('Candidate checksum mismatch: ' + name)
        if name.endswith('.py'):
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=name, feature_version=(3, 11))
    return manifest


def audit_guard(writes, violations, inventory):
    def deny(label):
        violations.append(label)
        raise RuntimeError('Forbidden I/O: ' + label)

    def writable(value, directory=None):
        if isinstance(value, int) or directory not in (None, -1):
            deny('unresolved write descriptor')
        path = Path(os.fsdecode(value)).absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            deny('symlink write')
        path = path.resolve()
        if not any(path == root or path.is_relative_to(root) for root in writes):
            deny('write outside scratch/evidence')

    def audit(event, args):
        if event.startswith(('socket.', 'os.exec', 'os.spawn')) or event in {
            'subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
            'sqlite3.connect', 'smtplib.connect', 'http.client.connect', 'urllib.Request',
        }:
            deny(event)
        if event == 'open':
            value, mode, flags = args
            if not isinstance(value, int):
                name = Path(os.fsdecode(value)).name
                if name.startswith('.env') and not name.endswith('.example'):
                    deny('dotenv access')
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                writable(value)
        if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.chown', 'os.utime'}:
            writable(args[0], args[-1])
        if event in {'os.rename', 'os.link'}:
            writable(args[0], args[2])
            writable(args[1], args[3])
        if event in {'os.symlink', 'os.truncate'}:
            deny(event)
        if event == 'exec' and not args[0].co_filename.startswith('<'):
            path = Path(args[0].co_filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                if path.relative_to(ROOT).as_posix() not in inventory:
                    deny('uninventoried source')

    sys.addaudithook(audit)
    return deny


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--preparation', action='store_true')
    parser.add_argument('--mounted-profile', choices=('standard', 'beta_lite'))
    parser.add_argument('--reader-gid', type=int)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise RuntimeError('Use python -I -B')
    if os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') != '1' or any(
        os.environ.get(k) for k in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTHONPATH', 'PYTHONHOME')
    ):
        raise RuntimeError('Disable pytest plugin autoload and external Python/pytest options')
    if not args.preparation:
        if (sys.platform != 'linux' or sys.version_info[:3] != (3, 11, 18)
                or platform.machine() != 'x86_64' or sys.prefix == sys.base_prefix
                or platform.freedesktop_os_release().get('ID') != 'debian'
                or platform.freedesktop_os_release().get('VERSION_ID') != '13'):
            raise RuntimeError('Debian 13/x86_64/CPython 3.11.18 dedicated venv required')
    if args.mounted_profile:
        if (args.preparation or os.geteuid() == 0 or not Path('/.dockerenv').is_file()
                or not args.reader_gid or args.reader_gid not in {os.getegid(), *os.getgroups()}
                or not Path('/run/documind-control').is_dir()
                or Path('/run/documind-control').is_symlink()):
            raise RuntimeError('Mounted profile requires a non-root isolated Docker lab and verified reader group')
    inventory = verify_inputs()
    evidence, scratch = new_directory(args.evidence), new_directory(args.scratch)
    if not args.preparation:
        base = (Path('/evidence') if args.mounted_profile else Path(
            '/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence'))
        if not evidence.is_relative_to(base):
            raise RuntimeError('Debian evidence must be beneath the dedicated evidence base')
    if evidence.is_relative_to(scratch) or scratch.is_relative_to(evidence):
        raise RuntimeError('Separate evidence and scratch required')
    evidence.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    violations = []
    metadata = {'scope': 'unit/static/ASGI only; never Docker qualification',
                'preparation': args.preparation, 'platform': sys.platform, 'python': sys.version,
                'input_manifest_sha256': sha(ROOT / 'INPUTS.json'),
                'verdict': 'INCOMPLETE', 'forbidden_io_events': violations}
    active_tests = ([ROOT / 'lab' / 'test_mounted_latch.py'] if args.mounted_profile
                    else [ROOT / 'tests' / name for name in TESTS])
    if args.mounted_profile:
        metadata.update(mounted_profile=args.mounted_profile, uid=os.geteuid(), gid=os.getegid(),
                        groups=os.getgroups(), scope='mounted ASGI only; external Engine evidence mandatory')
        sys.path.insert(0, str(ROOT / 'tests'))
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    os.environ['PYTHONPYCACHEPREFIX'] = str(scratch / 'unused-pycache')
    os.environ['TMP'] = os.environ['TEMP'] = os.environ['TMPDIR'] = str(scratch)
    sys.path.insert(0, str(ROOT / 'source'))
    platform.node = lambda: 'synthetic-inprocess'
    platform.machine = lambda: 'synthetic-inprocess'
    deny = audit_guard((evidence, scratch), violations, inventory)
    try:
        dependencies = {}
        for dist in importlib.metadata.distributions():
            record = dist.read_text('RECORD')
            dependencies[dist.metadata['Name']] = {
                'version': dist.version,
                'RECORD_sha256': hashlib.sha256((record or '').encode()).hexdigest(),
            }
        (evidence / 'dependencies.json').write_text(json.dumps(dependencies, indent=2) + '\n')
        (evidence / 'inputs.json').write_text(json.dumps(inventory, indent=2) + '\n')
        import threading
        threading.Thread.start = lambda *a, **k: deny('real_thread')
        import sqlalchemy
        import psycopg
        import sqlite3
        import smtplib
        import openai
        for module, attribute in (
            (sqlalchemy, 'create_engine'), (psycopg, 'connect'), (sqlite3, 'connect'),
            (smtplib, 'SMTP'), (smtplib, 'SMTP_SSL'), (openai, 'OpenAI'), (openai, 'AsyncOpenAI'),
        ):
            setattr(module, attribute, lambda *a, _label=attribute, **k: deny(_label))
        import pytest

        class Strict:
            def __init__(self):
                self.index = 0
                self.count = 0
                self.results = Counter()
                self.cases = []

            @pytest.fixture
            def tmp_path(self):
                self.index += 1
                path = scratch / ('case-%03d' % self.index)
                path.mkdir(mode=0o700)
                return path

            def pytest_configure(self, config):
                config._mounted_profile = args.mounted_profile

            def pytest_collection_finish(self, session):
                self.count = len(session.items)
                paths = set(active_tests)
                if not self.count or {item.path.resolve() for item in session.items} != paths:
                    raise pytest.UsageError('Only the complete selected candidate profile is allowed')
                if any(any(item.iter_markers(mark)) for item in session.items for mark in ('skip', 'skipif', 'xfail')):
                    raise pytest.UsageError('skip/xfail forbidden')

            def pytest_runtest_logreport(self, report):
                if report.when == 'call':
                    self.results[report.outcome] += 1
                    self.cases.append({'nodeid': report.nodeid, 'outcome': report.outcome,
                                       'properties': dict(report.user_properties)})
                if report.skipped or hasattr(report, 'wasxfail'):
                    pytest.exit('skip/xfail forbidden', returncode=1)

        strict = Strict()
        status = pytest.main([
            '-c', str(ROOT / 'pytest.ini'), '--noconftest', '-p', 'no:cacheprovider',
            '-x', '-q', '--tb=short', '--capture=sys', '--log-file', str(evidence / 'pytest.log'),
            '--junitxml', str(evidence / 'junit.xml'),
            *map(str, active_tests),
        ], plugins=[strict])
        metadata.update(collected=strict.count, outcomes=dict(strict.results), pytest_exit_code=int(status))
        (evidence / 'cases.json').write_text(json.dumps(strict.cases, indent=2) + '\n')
        if status != 0 or strict.results != Counter(passed=strict.count) or violations:
            raise RuntimeError('Campaign failed')
        cases = list(ET.parse(evidence / 'junit.xml').getroot().iter('testcase'))
        if len(cases) != strict.count or any(list(case) for case in cases if any(
            list(case.iter(tag)) for tag in ('failure', 'error', 'skipped')
        )):
            raise RuntimeError('JUnit count/outcomes mismatch')
        verify_inputs()
        metadata['verdict'] = ('PASS_PREPARATION_ONLY' if args.preparation else
                               'PASS_MOUNTED_ASGI_REQUIRE_ENGINE_EVIDENCE' if args.mounted_profile
                               else 'PASS_DEBIAN_UNIT_ASGI_ONLY')
    except BaseException as error:
        metadata.update(verdict='FAILED', error=str(error))
        (evidence / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        (evidence / 'result.json').write_text(json.dumps(metadata, indent=2) + '\n')
        files = sorted(path for path in evidence.iterdir() if path.is_file() and path.name != 'SHA256SUMS')
        (evidence / 'SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in files), encoding='ascii')


if __name__ == '__main__':
    main()
